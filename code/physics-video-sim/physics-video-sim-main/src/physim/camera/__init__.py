"""Trajectory-aware camera policies."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from physim.physics import SimulationResult


@dataclass(frozen=True)
class CameraSpec:
    position: tuple[float, float, float]
    look_at: tuple[float, float, float]
    focal_length_mm: float
    framing: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def merge_camera_config(base: dict, overrides: dict | None) -> dict:
    """Merge region camera overrides while retaining shared framing defaults."""
    merged = dict(base)
    overrides = dict(overrides or {})
    if "framing" in overrides:
        merged["framing"] = {
            **dict(base.get("framing", {})),
            **dict(overrides.pop("framing")),
        }
    merged.update(overrides)
    return merged


def fixed_camera(result: SimulationResult, config: dict) -> CameraSpec:
    """Use an explicitly authored camera pose.

    Unlike the trajectory-aware policies this does NOT derive the pose from the
    motion.  It reproduces a pose that was reviewed and approved for a specific
    scene, so a re-render is guaranteed to be framed exactly like the version
    that was signed off -- independent of which actor, seed or spin rate the
    clip happens to use.  ``result`` is accepted only so the signature matches
    the other policies; it is deliberately not consulted.
    """
    position = config.get("position")
    look_at = config.get("look_at")
    if position is None or look_at is None:
        raise ValueError("Fixed camera policy requires 'position' and 'look_at'")
    if len(position) != 3 or len(look_at) != 3:
        raise ValueError("Fixed camera 'position' and 'look_at' must be 3-vectors")
    if tuple(float(v) for v in position) == tuple(float(v) for v in look_at):
        raise ValueError("Fixed camera 'position' and 'look_at' must differ")
    distance = float(
        np.linalg.norm(
            np.asarray(position, dtype=np.float64) - np.asarray(look_at, dtype=np.float64)
        )
    )
    framing = {
        **dict(config.get("framing") or {}),
        "mode": "fixed_authored_pose",
        "position": [float(v) for v in position],
        "look_at": [float(v) for v in look_at],
        "distance": distance,
    }
    return CameraSpec(
        position=tuple(float(v) for v in position),
        look_at=tuple(float(v) for v in look_at),
        focal_length_mm=float(config["focal_length_mm"]),
        framing=framing,
    )


def perpendicular_camera(
    result: SimulationResult,
    config: dict,
    *,
    max_object_extent: float | None = None,
) -> CameraSpec:
    positions = np.asarray([state.position for state in result.trajectory], dtype=np.float64)
    start = positions[0]
    end = positions[-1]
    direction = end[:2] - start[:2]
    norm = float(np.linalg.norm(direction))
    if norm < 1e-8:
        direction = np.asarray(result.trajectory[0].linear_velocity[:2])
        norm = float(np.linalg.norm(direction))
    if norm < 1e-8:
        raise ValueError("Cannot place a perpendicular camera for a stationary trajectory")
    direction /= norm
    side = np.asarray((-direction[1], direction[0]))
    if config.get("side", "right") == "right":
        side *= -1.0
    azimuth_offset_degrees = float(config.get("azimuth_offset_degrees", 0.0))
    if azimuth_offset_degrees:
        azimuth = np.radians(azimuth_offset_degrees)
        rotation = np.asarray(
            (
                (np.cos(azimuth), -np.sin(azimuth)),
                (np.sin(azimuth), np.cos(azimuth)),
            )
        )
        side = rotation @ side
    # Project against the actual image-horizontal axis after the optional
    # world-Z orbit, not merely against the motion direction.
    screen_horizontal = np.asarray((-side[1], side[0]))
    horizontal_projection = positions[:, :2] @ screen_horizontal
    horizontal_extent = float(horizontal_projection.max() - horizontal_projection.min())
    vertical_extent = float(positions[:, 2].max() - positions[:, 2].min())
    center = (positions.min(axis=0) + positions.max(axis=0)) / 2.0
    focal_length = float(config["focal_length_mm"])
    framing_config = config.get("framing")
    framing = None
    if framing_config is not None:
        if max_object_extent is None or max_object_extent <= 0:
            raise ValueError("Dynamic camera framing requires a positive max_object_extent")
        sensor_width = float(framing_config.get("sensor_width_mm", 36.0))
        tangent = sensor_width / (2.0 * focal_length)
        trajectory_frame_fraction = float(
            framing_config.get("trajectory_frame_fraction", 0.80)
        )
        min_object_fraction = float(
            framing_config.get("min_object_frame_fraction", 0.03)
        )
        max_object_fraction = float(
            framing_config.get("max_object_frame_fraction", 0.30)
        )
        object_padding = float(framing_config.get("object_padding", 0.25))
        if not 0 < min_object_fraction <= max_object_fraction < 1:
            raise ValueError("Camera object frame fractions must satisfy 0 < min <= max < 1")
        if not 0 < trajectory_frame_fraction < 1:
            raise ValueError("trajectory_frame_fraction must be between 0 and 1")

        content_width = horizontal_extent + max_object_extent * (
            1.0 + 2.0 * object_padding
        )
        content_height = vertical_extent + max_object_extent * (
            1.0 + 2.0 * object_padding
        )
        aspect_ratio = float(framing_config.get("aspect_ratio", 16.0 / 9.0))
        if aspect_ratio <= 0:
            raise ValueError("Camera framing aspect_ratio must be positive")
        min_area_fraction = float(
            framing_config.get("min_object_frame_area_fraction", 0.0)
        )
        max_area_fraction = float(
            framing_config.get("max_object_frame_area_fraction", 1.0)
        )
        if not 0.0 <= min_area_fraction <= max_area_fraction <= 1.0:
            raise ValueError(
                "Camera object area fractions must satisfy 0 <= min <= max <= 1"
            )
        if min_area_fraction:
            min_object_fraction = max(
                min_object_fraction,
                float(np.sqrt(min_area_fraction / aspect_ratio)),
            )
        if max_area_fraction < 1.0:
            max_object_fraction = min(
                max_object_fraction,
                float(np.sqrt(max_area_fraction / aspect_ratio)),
            )
        if min_object_fraction > max_object_fraction:
            raise ValueError(
                "Camera linear/area object-size constraints have no overlap"
            )
        horizontal_fit_distance = content_width / (
            2.0 * tangent * trajectory_frame_fraction
        )
        vertical_tangent = tangent / aspect_ratio
        vertical_fit_distance = content_height / (
            2.0 * vertical_tangent * trajectory_frame_fraction
        )
        fit_distance = max(horizontal_fit_distance, vertical_fit_distance)
        min_size_distance = max_object_extent / (2.0 * tangent * max_object_fraction)
        max_size_distance = max_object_extent / (2.0 * tangent * min_object_fraction)
        distance = max(
            fit_distance,
            min_size_distance,
            float(framing_config.get("min_distance", 0.25)),
        )
        configured_max_distance = float(framing_config.get("max_distance", 20.0))
        if distance > configured_max_distance:
            raise ValueError(
                f"Camera needs distance {distance:.3f} m to frame the trajectory, "
                f"above configured max_distance {configured_max_distance:.3f} m"
            )
        frame_width = 2.0 * distance * tangent
        object_frame_fraction = max_object_extent / frame_width
        object_frame_area_fraction = aspect_ratio * object_frame_fraction**2
        if distance > max_size_distance or object_frame_fraction < min_object_fraction:
            raise ValueError(
                "A static camera cannot fit the complete trajectory while keeping the "
                f"largest object visible: projected fraction {object_frame_fraction:.4f}, "
                f"minimum {min_object_fraction:.4f}"
            )
        elevation_degrees = float(framing_config.get("elevation_degrees", 12.0))
        vertical_offset = max(
            float(framing_config.get("min_height_above_trajectory", 0.45)),
            distance * np.tan(np.radians(elevation_degrees)),
        )
        look_at_offset = float(framing_config.get("look_at_offset", 0.0))
        framing = {
            "mode": "trajectory_and_max_object",
            "max_object_extent": max_object_extent,
            "trajectory_extent": float(
                np.linalg.norm(positions.max(axis=0) - positions.min(axis=0))
            ),
            "horizontal_trajectory_extent": horizontal_extent,
            "vertical_trajectory_extent": vertical_extent,
            "content_width": content_width,
            "content_height": content_height,
            "aspect_ratio": aspect_ratio,
            "distance": distance,
            "frame_width_at_target": frame_width,
            "object_frame_fraction": object_frame_fraction,
            "object_frame_area_fraction": object_frame_area_fraction,
            "min_object_frame_fraction": min_object_fraction,
            "max_object_frame_fraction": max_object_fraction,
            "min_object_frame_area_fraction": min_area_fraction,
            "max_object_frame_area_fraction": max_area_fraction,
            "trajectory_frame_fraction": trajectory_frame_fraction,
            "azimuth_offset_degrees": azimuth_offset_degrees,
        }
    else:
        distance = float(config["distance"])
        vertical_offset = float(config["height"])
        look_at_offset = float(config["look_at_height"])

    vertical_origin = float(center[2]) if config.get("relative_to_trajectory", False) else 0.0
    position = np.asarray(
        (
            center[0] + side[0] * distance,
            center[1] + side[1] * distance,
            vertical_origin + vertical_offset,
        )
    )
    look_at = np.asarray(
        (center[0], center[1], vertical_origin + look_at_offset)
    )
    return CameraSpec(
        position=tuple(float(v) for v in position),
        look_at=tuple(float(v) for v in look_at),
        focal_length_mm=focal_length,
        framing=framing,
    )
