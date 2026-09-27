"""Shared deterministic sampling helpers for rigid-body scenarios."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from physim.assets import AssetSpec
from physim.maps import MapSpec, SurfaceSpec
from physim.maps.surface_sampler import SurfaceSampler
from physim.scenarios import ControlVariant


def uniform(rng: np.random.Generator, bounds: Sequence[float]) -> float:
    return float(rng.uniform(float(bounds[0]), float(bounds[1])))


def object_extent(asset: AssetSpec) -> float:
    return max(
        float(size) * float(scale)
        for size, scale in zip(
            asset.size or (asset.radius * 2.0,) * 3,
            asset.scale,
        )
    )


def base_physics(
    rng: np.random.Generator,
    asset: AssetSpec,
    physics: dict[str, Any] | None = None,
) -> tuple[float, float, float]:
    """Sample mass, friction and restitution for one actor.

    The scenario config may override any of the three ranges under its
    ``physics`` block.  This exists because the surface a demo is filmed on is a
    scene decision: the mentor's ball scenarios rely on rolling contact (where
    lateral friction does not brake the body), while our convex-hull actors slide
    and would otherwise stop within a single frame on a high-friction floor.
    The sampled value still goes to the solver unchanged -- no trajectory is
    prescribed.
    """
    overrides = physics or {}
    return (
        uniform(rng, overrides.get("mass_range", asset.mass_range)),
        uniform(rng, overrides.get("friction_range", asset.friction_range)),
        uniform(rng, overrides.get("restitution_range", asset.restitution_range)),
    )


def select_surface(
    config: dict[str, Any],
    asset: AssetSpec,
    map_spec: MapSpec,
    rng: np.random.Generator,
    sampler: SurfaceSampler,
) -> SurfaceSpec:
    allowed = tuple(
        str(value)
        for value in config["surface"].get(
            "allowed_types", tuple(item.surface_type for item in map_spec.surfaces)
        )
    )
    return sampler.select_surface(map_spec.surfaces, object_extent(asset), allowed, rng)


def planar_direction(
    rng: np.random.Generator,
    physics: dict[str, Any],
    surface: SurfaceSpec,
) -> np.ndarray:
    angle_range = surface.metadata.get(
        "direction_degrees_range", physics["direction_degrees_range"]
    )
    angle = math.radians(uniform(rng, angle_range))
    return np.asarray((math.cos(angle), math.sin(angle)), dtype=np.float64)


def edge_margin(config: dict[str, Any], surface: SurfaceSpec) -> float:
    return float(
        surface.metadata.get("edge_margin", config["surface"].get("edge_margin", 0.0))
    )


def default_variant(variant: ControlVariant | None) -> ControlVariant:
    return variant or ControlVariant("baseline")


def timing_parameters(timing: dict[str, Any]) -> tuple[float, int, int, int]:
    """Return duration, video FPS, physics FPS, and exact output frame count."""
    video_fps = int(timing["video_fps"])
    physics_fps = int(timing["physics_fps"])
    if video_fps <= 0 or physics_fps <= 0:
        raise ValueError("video_fps and physics_fps must be positive")
    if physics_fps % video_fps != 0:
        raise ValueError("physics_fps must be divisible by video_fps")
    configured_duration = float(timing["duration_seconds"])
    frame_count = int(timing.get("frame_count", round(configured_duration * video_fps)))
    if frame_count < 2:
        raise ValueError("frame_count must be at least 2")
    if "frame_count" in timing and round(configured_duration * video_fps) != frame_count:
        raise ValueError("duration_seconds * video_fps must equal frame_count")
    return frame_count / video_fps, video_fps, physics_fps, frame_count


def scale_vector(
    vector: Sequence[float], multiplier: float
) -> tuple[float, float, float]:
    return tuple(float(value) * multiplier for value in vector)


# ---------------------------------------------------------------------------
# Per-scenario initial orientation (additive; absent key == manifest pose)
# ---------------------------------------------------------------------------
# An asset manifest declares ONE resting orientation, shared by every scenario
# that uses the asset.  A scenario may need a different one: a body meant to
# ROLL has to lie on its side, because an upright container cannot roll and a
# container sliding across a floor at constant velocity has no physical
# motivation.  Rather than mutate the shared manifest (which would silently
# re-orient the asset in every other scenario), the pose is selected by an
# optional per-scenario ``orientation`` block:
#
#     orientation:
#       policy: side
#       asset_ids: [some_asset]          # optional; default = every asset
#       friction_range: [0.30, 0.60]     # optional; rolling needs real friction
#
# Everything here is opt-in: when the key is absent (or names a policy other
# than ``side``, or the asset is not listed) the resolved pose, support height,
# footprint radius and physics ranges are exactly the manifest's own values, so
# existing samples stay bit-identical.

#: Manifest pose -- the object rests the way it was authored.
ORIENTATION_UPRIGHT = "upright"
#: Long axis laid down along the rolling spin axis.
ORIENTATION_SIDE = "side"


def orientation_entry(config: dict[str, Any]) -> dict[str, Any]:
    entry = config.get("orientation")
    return dict(entry) if isinstance(entry, dict) else {}


def side_orientation_requested(entry: dict[str, Any], asset: AssetSpec) -> bool:
    if str(entry.get("policy", ORIENTATION_UPRIGHT)) != ORIENTATION_SIDE:
        return False
    asset_ids = entry.get("asset_ids")
    if asset_ids is None:
        return True
    return asset.asset_id in tuple(str(value) for value in asset_ids)


def _rotation_x(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.asarray(((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c)))


def _rotation_z(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.asarray(((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0)))


def collision_hull_vertices(asset: AssetSpec, path: Any | None = None) -> np.ndarray | None:
    """Vertices of a collision OBJ, or None if there is no readable hull.

    The manifest's own support_height / footprint_radius describe the UPRIGHT
    pose only, so a rotated pose cannot reuse them -- the height and radius have
    to be re-measured from the rotated geometry.  ``path`` selects an
    alternative hull (the refined side collision mesh); by default the asset's
    own collision mesh is used.
    """
    if path is None:
        path = asset.collision.mesh_path
    if path is None:
        return None
    path = Path(path)
    if path.suffix.lower() != ".obj":
        return None
    rows: list[tuple[float, float, float]] = []
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.startswith("v "):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            rows.append((float(parts[1]), float(parts[2]), float(parts[3])))
    if not rows:
        return None
    return np.asarray(rows, dtype=np.float64)


def side_collision_geometry(asset: AssetSpec) -> dict[str, Any]:
    """The asset's optional refined side-collision block, resolved to paths.

    Read straight from the manifest (``AssetSpec.metadata`` is the raw entry) so
    that the asset loader needs no new field and every asset without the block
    is untouched.  Relative paths resolve against the asset directory, exactly
    like ``collision.mesh`` / ``collision.simulation``.
    """
    entry = asset.metadata.get("side_collision")
    if not isinstance(entry, dict):
        return {}
    resolved: dict[str, Any] = {}
    for key in ("mesh", "simulation"):
        value = entry.get(key)
        if value:
            resolved[key] = (asset.asset_dir / str(value)).resolve()
    for key in ("support_height", "footprint_radius"):
        if entry.get(key) is not None:
            resolved[key] = float(entry[key])
    return resolved


def matrix_to_quaternion_wxyz(matrix: np.ndarray) -> tuple[float, float, float, float]:
    """Rotation matrix -> normalised (w, x, y, z) quaternion.

    Kubric stores quaternions as WXYZ and converts to PyBullet's XYZW itself, so
    this must emit WXYZ or the object would be rotated by the conjugate.
    """
    m = np.asarray(matrix, dtype=np.float64)
    trace = float(m[0, 0] + m[1, 1] + m[2, 2])
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm <= 1e-12:
        return (1.0, 0.0, 0.0, 0.0)
    return (w / norm, x / norm, y / norm, z / norm)


def side_pose(
    asset: AssetSpec, direction_xy: np.ndarray, *, refined: bool = False
) -> tuple[tuple[float, float, float, float], float, float]:
    """Lay the asset's LONG axis down, perpendicular to the travel direction.

    Returns ``(quaternion_wxyz, support_height, footprint_radius)``.

    The long axis is placed along ``normal x direction``, which is exactly the
    spin axis the rolling scenario's ``cross(normal, linear_velocity)`` produces.
    Aligning the two is what makes the object a rolling cylinder rather than a
    tumbling box: the contact line is then parallel to the spin axis, so every
    cross-section rotates at the same rate and the surface velocity at the
    contact is ``omega * r``, i.e. rolling without slipping.

    ``support_height`` and ``footprint_radius`` are re-measured from the rotated
    collision hull.  Reusing the manifest's upright ``support_height`` here would
    spawn the object 2 cm inside the floor and collapse ``supported_fraction``.

    ``refined`` selects the asset's optional ``side_collision`` hull.  A coarse
    convex hull (64 vertices here) models a smooth can as a ~16-gon, so it rocks
    facet-to-facet and stops; measured decay +0.674 /s versus -0.055 /s for the
    refined hull.  See ``tools/_t1b_rigorous.sh`` for the measurement.
    """
    if asset.size is None:
        raise ValueError(
            f"Asset {asset.asset_id!r} needs visual.size to resolve a side pose"
        )
    scaled = np.asarray(asset.size, dtype=np.float64) * np.asarray(
        asset.scale, dtype=np.float64
    )
    long_axis = int(np.argmax(scaled))
    if long_axis != 2:
        raise ValueError(
            f"Asset {asset.asset_id!r} has its long axis on index {long_axis}; "
            "the 'side' orientation is only defined for a Z-long object"
        )
    direction = np.asarray(direction_xy, dtype=np.float64)[:2]
    norm = float(np.linalg.norm(direction))
    if norm < 1e-12:
        raise ValueError("A side pose needs a non-zero travel direction")
    direction = direction / norm
    # Spin axis for forward rolling: n x d with n = +Z.
    axis_x, axis_y = -float(direction[1]), float(direction[0])
    # Rz(phi) . Rx(+90deg) sends local +Z to (sin phi, -cos phi); solve for the
    # spin axis, then the local +Y (a cylinder's radial direction) lands on +Z.
    phi = math.atan2(axis_x, -axis_y)
    rotation = _rotation_z(phi) @ _rotation_x(math.pi / 2.0)
    quaternion = matrix_to_quaternion_wxyz(rotation)

    side = side_collision_geometry(asset) if refined else {}
    hull = collision_hull_vertices(asset, side.get("mesh"))
    if hull is None:
        # No measurable hull: fall back to the manifest's own cross-section
        # radius, which is the correct side-on height for a circular object.
        radius = float(side.get("footprint_radius", asset.radius))
        return quaternion, float(side.get("support_height", asset.radius)), radius
    rotated = (rotation @ hull.T).T
    # The manifest may carry the pre-computed values (computed once at asset
    # preparation time) so the runtime does not depend on re-deriving them.
    support_height = float(
        side.get("support_height", float((-rotated[:, 2]).max()))
    )
    footprint_radius = float(
        side.get("footprint_radius", float(np.hypot(rotated[:, 0], rotated[:, 1]).max()))
    )
    if support_height <= 0.0 or footprint_radius <= 0.0:
        raise ValueError(f"Degenerate side pose for asset {asset.asset_id!r}")
    return quaternion, support_height, footprint_radius


def resolve_initial_orientation(
    config: dict[str, Any],
    asset: AssetSpec,
    direction_xy: np.ndarray | None = None,
) -> tuple[tuple[float, float, float, float], float, float, dict[str, Any]]:
    """Resolve the pose the sample should start in.

    Returns ``(quaternion_wxyz, support_height, footprint_radius, info)``.  When
    the scenario does not ask for the side pose, the three geometry values are
    the manifest's own, so behaviour is unchanged.
    """
    entry = orientation_entry(config)
    if not side_orientation_requested(entry, asset):
        return (
            asset.initial_quaternion,
            asset.support_height,
            asset.radius,
            {"policy": str(entry.get("policy", ORIENTATION_UPRIGHT)), "applied": False},
        )
    if direction_xy is None:
        raise ValueError("The 'side' orientation requires the travel direction")
    refined = bool(entry.get("refined_collision", False))
    quaternion, support_height, footprint_radius = side_pose(
        asset, direction_xy, refined=refined
    )
    info: dict[str, Any] = {
        "policy": ORIENTATION_SIDE,
        "applied": True,
        "asset_id": asset.asset_id,
        "support_height": support_height,
        "footprint_radius": footprint_radius,
        "quaternion_wxyz": list(quaternion),
        "refined_collision": refined,
        "friction_range": (
            None
            if entry.get("friction_range") is None
            else [float(v) for v in entry["friction_range"]]
        ),
    }
    if refined:
        side = side_collision_geometry(asset)
        info["collision_simulation"] = (
            None if side.get("simulation") is None else str(side["simulation"])
        )
    return quaternion, support_height, footprint_radius, info
