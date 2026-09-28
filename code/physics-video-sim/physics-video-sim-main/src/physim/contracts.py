"""V5.5 multi-body data contract.

Why a separate module
---------------------
The existing pipeline models exactly ONE actor: ``SimulationResult`` carries a
``trajectory`` plus an optional ``support_trajectory`` for the turntable disc.  A
domino chain needs N independently-identified bodies, per-substep contact records,
and per-substep motion so a contact can be attributed causally.  Stuffing those into
``support_trajectory`` would make "which body is this?" unanswerable.

This module defines the contract only.  It performs no simulation, no rendering and
no asset loading, so every later stage can depend on it without cycles.

Frozen conventions (stage 02 decisions, recorded in
``log/V5.5_execution/contract_decisions.md``)
-------------------------------------------------------------------------------
Units
    metres, seconds, kilograms, newtons; **Z up**; gravity ``[0, 0, -9.81]``.

Frames
    ``W`` world, ``B`` the physics rigid-body frame (PyBullet base frame), ``V`` the
    visual mesh frame.  Column vectors, ``T_WV = T_WB @ T_BV``.  Serialization is
    row-major for both the 4x4 matrix and its flattened 16-element form.

Quaternions
    **``quaternion_xyzw`` everywhere in the new JSON contract.**  PyBullet is natively
    xyzw, so the physics side needs no reordering.  ``physim.physics.BodyState`` and
    the Kubric/Blender ``wxyz`` interfaces are converted explicitly at the boundary by
    :func:`to_body_state` / :func:`to_wxyz` -- never implicitly, and ``q`` and ``-q``
    are treated as the same rotation wherever equality matters.

Time
    ``frame`` starts at 0.  ``time_s = frame / video_fps``.  The **Blender frame number
    is ``frame + 1``**.  Physics advances in substeps of ``dt = 1 / physics_fps``;
    substep ``k`` (1-based) covers the half-open interval ``((k-1)*dt, k*dt]`` and is
    reported with ``step=k`` and ``time_s = k * dt``.

    This is deliberately different from the earlier V5 demo, whose substep contact log
    recorded contacts after stepping but numbered them as if before, shifting every
    event one ``dt`` early.  :func:`substep_time_s` is the single place that computes
    it, and a test pins the convention.

Identity
    ``asset_id`` names a reusable asset (one scan); ``instance_id`` names one placed
    body (``box_001``).  The same ``asset_id`` may appear many times.  Persistent
    identity is the ``instance_id`` string -- never a Python object address and never a
    load-order-dependent name.

Roles
    ``trigger`` initiates, ``target`` is meant to be moved by the chain, ``passive``
    is scenery that may be contacted but has no role in propagation.  Only the masses
    and roles in the config determine which bodies are dynamic; static scenery is a
    separate ``StaticCollider`` list, not a mass-zero body.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

#: Contract schema version. Bump when a consumer-visible field changes meaning.
SCHEMA_VERSION = "v55.contract.1"

#: Version of the on-disk run-output layout.
OUTPUT_SCHEMA_VERSION = "v55.outputs.1"

ROLE_TRIGGER = "trigger"
ROLE_TARGET = "target"
ROLE_PASSIVE = "passive"
VALID_ROLES = (ROLE_TRIGGER, ROLE_TARGET, ROLE_PASSIVE)


def box_inertia_diagonal(
    mass_kg: float, dimensions_m: Sequence[float]
) -> tuple[float, float, float]:
    """Solid-cuboid principal inertia: ``Ixx = m*(h^2 + d^2)/12`` and its two analogues.

    Stage 03 requires boxes to use this form and explicitly forbids the old backend's
    ``m*a^2/5`` half-axis approximation, which overstates a flat box's inertia several-fold
    and would make it resist toppling.  This is the single shared implementation, so no
    stage can quietly reintroduce the old formula.
    """
    x, y, z = (float(v) for v in dimensions_m[:3])
    return (
        mass_kg * (y * y + z * z) / 12.0,
        mass_kg * (x * x + z * z) / 12.0,
        mass_kg * (x * x + y * y) / 12.0,
    )

Z_UP_GRAVITY = (0.0, 0.0, -9.81)


class ContractError(ValueError):
    """Raised when data violates the frozen contract."""


# ---------------------------------------------------------------------------
# linear algebra helpers (kept dependency-free and exactly testable)
# ---------------------------------------------------------------------------


def quat_multiply(
    a: Sequence[float], b: Sequence[float]
) -> tuple[float, float, float, float]:
    """Hamilton product of two ``xyzw`` quaternions."""
    ax, ay, az, aw = (float(v) for v in a)
    bx, by, bz, bw = (float(v) for v in b)
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quat_conjugate(q: Sequence[float]) -> tuple[float, float, float, float]:
    """Conjugate (inverse for a unit quaternion) of an ``xyzw`` quaternion."""
    x, y, z, w = (float(v) for v in q)
    return (-x, -y, -z, w)


def quat_normalize(q: Sequence[float]) -> tuple[float, float, float, float]:
    x, y, z, w = (float(v) for v in q)
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm == 0.0:
        raise ContractError(f"cannot normalize a zero quaternion: {tuple(q)}")
    return (x / norm, y / norm, z / norm, w / norm)


def quat_angle(q: Sequence[float]) -> float:
    """Rotation angle in radians, in ``[0, pi]``.

    Normalising ``w`` to be non-negative first makes ``q`` and ``-q`` report the same
    angle, which is what the contract requires.
    """
    x, y, z, w = quat_normalize(q)
    if w < 0.0:
        x, y, z, w = -x, -y, -z, -w
    return 2.0 * math.acos(max(-1.0, min(1.0, w)))


def quat_close(
    a: Sequence[float], b: Sequence[float], tol: float = 1e-9
) -> bool:
    """True when two quaternions describe the same rotation (``q`` and ``-q`` equal)."""
    qa = quat_normalize(a)
    qb = quat_normalize(b)
    same = all(abs(x - y) <= tol for x, y in zip(qa, qb))
    negated = all(abs(x + y) <= tol for x, y in zip(qa, qb))
    return same or negated


def quat_to_wxyz(q_xyzw: Sequence[float]) -> tuple[float, float, float, float]:
    """``xyzw`` -> ``wxyz`` for ``mathutils.Quaternion`` and Kubric."""
    x, y, z, w = (float(v) for v in q_xyzw)
    return (w, x, y, z)


def quat_from_wxyz(q_wxyz: Sequence[float]) -> tuple[float, float, float, float]:
    """``wxyz`` -> ``xyzw``."""
    w, x, y, z = (float(v) for v in q_wxyz)
    return (x, y, z, w)


def quat_rotate(q_xyzw: Sequence[float], v: Sequence[float]) -> tuple[float, float, float]:
    """Rotate vector ``v`` by quaternion ``q`` (``xyzw``)."""
    q = quat_normalize(q_xyzw)
    # v' = v + 2 * cross(q_vec, cross(q_vec, v) + w*v)
    qx, qy, qz, qw = q
    vx, vy, vz = (float(c) for c in v)
    # t = 2 * cross(q_vec, v)
    tx = 2.0 * (qy * vz - qz * vy)
    ty = 2.0 * (qz * vx - qx * vz)
    tz = 2.0 * (qx * vy - qy * vx)
    return (
        vx + qw * tx + (qy * tz - qz * ty),
        vy + qw * ty + (qz * tx - qx * tz),
        vz + qw * tz + (qx * ty - qy * tx),
    )


def mat4_identity() -> list[list[float]]:
    return [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]


def mat4_from_trs(
    translation: Sequence[float],
    rotation_xyzw: Sequence[float],
    scale: Sequence[float] = (1.0, 1.0, 1.0),
) -> list[list[float]]:
    """Row-major 4x4 from translation, ``xyzw`` rotation and (optionally) scale."""
    x, y, z, w = quat_normalize(rotation_xyzw)
    sx, sy, sz = (float(s) for s in scale)
    tx, ty, tz = (float(t) for t in translation)

    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z

    r = [
        [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
        [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
        [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
    ]
    return [
        [r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx],
        [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
        [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz],
        [0.0, 0.0, 0.0, 1.0],
    ]


def mat4_multiply(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> list[list[float]]:
    """``a @ b`` for row-major 4x4 matrices."""
    return [
        [sum(float(a[r][k]) * float(b[k][c]) for k in range(4)) for c in range(4)]
        for r in range(4)
    ]


def mat4_flatten(m: Sequence[Sequence[float]]) -> list[float]:
    """Row-major flattening -- the contract's serialization order."""
    return [float(m[r][c]) for r in range(4) for c in range(4)]


def mat4_unflatten(values: Sequence[float]) -> list[list[float]]:
    if len(values) != 16:
        raise ContractError(f"expected 16 values, got {len(values)}")
    v = [float(x) for x in values]
    return [v[r * 4 : r * 4 + 4] for r in range(4)]


def mat4_transform_point(m: Sequence[Sequence[float]], p: Sequence[float]) -> tuple[float, float, float]:
    """Apply a row-major 4x4 to a point (implicit ``w = 1``)."""
    x, y, z = (float(c) for c in p)
    return (
        m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
        m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
        m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3],
    )


# ---------------------------------------------------------------------------
# time
# ---------------------------------------------------------------------------


def substep_time_s(step: int, physics_fps: float) -> float:
    """Substep ``k`` (1-based) covers ``((k-1)dt, k*dt]`` and reports ``k*dt``.

    The V5 demo instead numbered a post-step measurement as if it preceded the step,
    shifting every contact one ``dt`` early.  Every V5.5 consumer must use this helper.
    """
    if step < 1:
        raise ContractError(f"substep index is 1-based; got {step}")
    if physics_fps <= 0:
        raise ContractError(f"physics_fps must be positive; got {physics_fps}")
    return step / float(physics_fps)


def frame_time_s(frame: int, video_fps: float) -> float:
    """``time_s = frame / video_fps`` with ``frame`` starting at 0."""
    if frame < 0:
        raise ContractError(f"frame must be >= 0; got {frame}")
    if video_fps <= 0:
        raise ContractError(f"video_fps must be positive; got {video_fps}")
    return frame / float(video_fps)


def blender_frame_number(frame: int) -> int:
    """Blender renders ``frame + 1`` because its timeline is 1-based."""
    if frame < 0:
        raise ContractError(f"frame must be >= 0; got {frame}")
    return frame + 1


def playback_duration_s(frame_count: int, video_fps: float) -> float:
    """How long the encoded video runs: ``N / fps`` (the frame count is N)."""
    return frame_count / float(video_fps)


def sampled_span_s(frame_count: int, video_fps: float) -> float:
    """Time from the first to the last sample: ``(N - 1) / fps``.

    Reported separately from :func:`playback_duration_s` because the two are
    legitimately different and conflating them is a common error.
    """
    return (frame_count - 1) / float(video_fps)


def substeps_per_frame(physics_fps: float, video_fps: float) -> int:
    """Substeps advanced per rendered frame.  Must divide exactly."""
    if video_fps <= 0:
        raise ContractError("video_fps must be positive")
    ratio = float(physics_fps) / float(video_fps)
    if abs(ratio - round(ratio)) > 1e-9:
        raise ContractError(
            f"physics_fps ({physics_fps}) must be an integer multiple of "
            f"video_fps ({video_fps})"
        )
    return int(round(ratio))


# ---------------------------------------------------------------------------
# contract records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubstepState:
    """One dynamic body's state at one physics substep (before/after contact)."""

    instance_id: str
    step: int
    time_s: float
    position_m: tuple[float, float, float]
    quaternion_xyzw: tuple[float, float, float, float]
    linear_velocity_m_s: tuple[float, float, float]
    angular_velocity_rad_s: tuple[float, float, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "step": self.step,
            "time_s": self.time_s,
            "position_m": list(self.position_m),
            "quaternion_xyzw": list(self.quaternion_xyzw),
            "linear_velocity_m_s": list(self.linear_velocity_m_s),
            "angular_velocity_rad_s": list(self.angular_velocity_rad_s),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubstepState":
        return cls(
            instance_id=str(data["instance_id"]),
            step=int(data["step"]),
            time_s=float(data["time_s"]),
            position_m=tuple(float(v) for v in data["position_m"]),
            quaternion_xyzw=tuple(float(v) for v in data["quaternion_xyzw"]),
            linear_velocity_m_s=tuple(float(v) for v in data["linear_velocity_m_s"]),
            angular_velocity_rad_s=tuple(float(v) for v in data["angular_velocity_rad_s"]),
        )


@dataclass(frozen=True)
class ContactRecord:
    """One valid contact at one substep.

    ``normal_on_b`` points from A towards B.  The raw PyBullet ``contact A/B`` order
    carries no causal meaning, so consumers must use the force direction, not the
    ``(a, b)`` ordering, to decide who pushed whom.
    """

    step: int
    time_s: float
    instance_a: str
    instance_b: str
    link_a: int
    link_b: int
    position_on_a_m: tuple[float, float, float]
    position_on_b_m: tuple[float, float, float]
    normal_on_b: tuple[float, float, float]
    signed_distance_m: float
    normal_force_n: float
    lateral_force_1_n: float
    lateral_force_2_n: float
    lateral_dir_1: tuple[float, float, float]
    lateral_dir_2: tuple[float, float, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "time_s": self.time_s,
            "instance_a": self.instance_a,
            "instance_b": self.instance_b,
            "link_a": self.link_a,
            "link_b": self.link_b,
            "position_on_a_m": list(self.position_on_a_m),
            "position_on_b_m": list(self.position_on_b_m),
            "normal_on_b": list(self.normal_on_b),
            "signed_distance_m": self.signed_distance_m,
            "normal_force_n": self.normal_force_n,
            "lateral_force_1_n": self.lateral_force_1_n,
            "lateral_force_2_n": self.lateral_force_2_n,
            "lateral_dir_1": list(self.lateral_dir_1),
            "lateral_dir_2": list(self.lateral_dir_2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContactRecord":
        return cls(
            step=int(data["step"]),
            time_s=float(data["time_s"]),
            instance_a=str(data["instance_a"]),
            instance_b=str(data["instance_b"]),
            link_a=int(data.get("link_a", -1)),
            link_b=int(data.get("link_b", -1)),
            position_on_a_m=tuple(float(v) for v in data["position_on_a_m"]),
            position_on_b_m=tuple(float(v) for v in data["position_on_b_m"]),
            normal_on_b=tuple(float(v) for v in data["normal_on_b"]),
            signed_distance_m=float(data["signed_distance_m"]),
            normal_force_n=float(data["normal_force_n"]),
            lateral_force_1_n=float(data.get("lateral_force_1_n", 0.0)),
            lateral_force_2_n=float(data.get("lateral_force_2_n", 0.0)),
            lateral_dir_1=tuple(float(v) for v in data.get("lateral_dir_1", (0.0, 0.0, 0.0))),
            lateral_dir_2=tuple(float(v) for v in data.get("lateral_dir_2", (0.0, 0.0, 0.0))),
        )

    @property
    def pair(self) -> frozenset[str]:
        """Unordered pair, so A-B and B-A aggregate together."""
        return frozenset((self.instance_a, self.instance_b))

    @property
    def involves_static(self) -> bool:
        """True when either side is static scenery (a non-body name)."""
        return self.instance_a.startswith("static:") or self.instance_b.startswith("static:")


@dataclass
class ContactEpisode:
    """A run of adjacent substeps with the same body pair in contact.

    ``gap_tolerance`` records how many empty substeps were bridged, so a consumer can
    re-derive the raw sequence rather than trusting the aggregate.
    """

    instance_a: str
    instance_b: str
    step_start: int
    step_end: int
    time_start_s: float
    time_end_s: float
    substeps: int
    gap_tolerance: int = 0
    peak_normal_force_n: float = 0.0
    impulse_proxy_n_s: float = 0.0
    contact_kind: str = "dynamic"  # "dynamic" | "static_support" | "ground"

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_a": self.instance_a,
            "instance_b": self.instance_b,
            "step_start": self.step_start,
            "step_end": self.step_end,
            "time_start_s": self.time_start_s,
            "time_end_s": self.time_end_s,
            "substeps": self.substeps,
            "gap_tolerance": self.gap_tolerance,
            "peak_normal_force_n": self.peak_normal_force_n,
            # Discrete estimate, NOT a true impulse: sum(F_normal * dt).  The name says so.
            "impulse_proxy_n_s": self.impulse_proxy_n_s,
            "impulse_proxy_is_estimate": True,
            "contact_kind": self.contact_kind,
        }


@dataclass(frozen=True)
class BodySpec:
    """One placed body: persistent identity, role, mass, collider and initial state.

    ``mass_kg`` and ``mass_basis`` are separate so an estimated mass is never mistaken
    for a measured one.  ``reason`` records WHY this body is dynamic (its role), which
    is what makes the "all objects passive" failure impossible to reach by accident.
    """

    instance_id: str
    asset_id: str
    role: str
    mass_kg: float
    mass_basis: str  # "measured" | "manufacturer" | "estimated"
    collider_type: str
    position_m: tuple[float, float, float]
    quaternion_xyzw: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    linear_velocity_m_s: tuple[float, float, float] = (0.0, 0.0, 0.0)
    angular_velocity_rad_s: tuple[float, float, float] = (0.0, 0.0, 0.0)
    friction: float = 0.5
    restitution: float = 0.1
    linear_damping: float = 0.0
    angular_damping: float = 0.0
    com_local_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    inertia_diagonal_kg_m2: tuple[float, float, float] | None = None
    source_object_id: str | None = None
    collision_uri: str | None = None
    visual_to_body_4x4: list[list[float]] | None = None
    collision_to_body_4x4: list[list[float]] | None = None
    mass_range_kg: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ContractError(
                f"{self.instance_id}: role must be one of {VALID_ROLES}, got {self.role!r}"
            )
        if not self.instance_id:
            raise ContractError("instance_id must be non-empty")
        if not self.asset_id:
            raise ContractError("asset_id must be non-empty")
        if self.mass_kg < 0.0:
            raise ContractError(f"{self.instance_id}: mass must be >= 0, got {self.mass_kg}")
        if self.mass_basis not in ("measured", "manufacturer", "estimated", "derived"):
            raise ContractError(
                f"{self.instance_id}: mass_basis must be measured/manufacturer/"
                f"estimated/derived, got {self.mass_basis!r}"
            )

    @property
    def is_dynamic(self) -> bool:
        """A body participates in the solve only if it can move."""
        return self.mass_kg > 0.0

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "instance_id": self.instance_id,
            "asset_id": self.asset_id,
            "role": self.role,
            "mass_kg": self.mass_kg,
            "mass_basis": self.mass_basis,
            "collider_type": self.collider_type,
            "position_m": list(self.position_m),
            "quaternion_xyzw": list(self.quaternion_xyzw),
            "linear_velocity_m_s": list(self.linear_velocity_m_s),
            "angular_velocity_rad_s": list(self.angular_velocity_rad_s),
            "friction": self.friction,
            "restitution": self.restitution,
            "linear_damping": self.linear_damping,
            "angular_damping": self.angular_damping,
            "com_local_m": list(self.com_local_m),
            "is_dynamic": self.is_dynamic,
        }
        if self.inertia_diagonal_kg_m2 is not None:
            out["inertia_diagonal_kg_m2"] = list(self.inertia_diagonal_kg_m2)
        if self.source_object_id is not None:
            out["source_object_id"] = self.source_object_id
        if self.collision_uri is not None:
            out["collision_uri"] = self.collision_uri
        if self.visual_to_body_4x4 is not None:
            out["visual_to_body_4x4"] = mat4_flatten(self.visual_to_body_4x4)
        if self.collision_to_body_4x4 is not None:
            out["collision_to_body_4x4"] = mat4_flatten(self.collision_to_body_4x4)
        if self.mass_range_kg is not None:
            out["mass_range_kg"] = list(self.mass_range_kg)
        return out


@dataclass(frozen=True)
class StaticCollider:
    """Passive scenery collision.  Not a body: no mass, no trajectory."""

    collider_id: str
    collider_type: str
    uri: str | None = None
    source_object_id: str | None = None
    position_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    quaternion_xyzw: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    half_extents_m: tuple[float, float, float] | None = None
    triangles: int | None = None
    # Concave scenery MUST set this, and the reason is measured rather than stylistic: a
    # static GEOM_MESH without `GEOM_FORCE_CONCAVE_TRIMESH` is silently CONVEX-HULLED by
    # PyBullet. The Italian Flat tray is a shallow open dish (floor z = 0.510600, rim
    # z = 0.522260); handed over unflagged, a probe box came to rest at z = 0.523247 -- the
    # RIM plane -- floating 12.65 mm above the real floor, while flagging it reproduces the
    # floor to within 0.0104 mm. So the flag is part of the collider's identity: without it
    # the recorded geometry is not the geometry that collides.
    concave: bool = False
    # Effective support height measured for this collider, when a stage has measured it. This
    # is where a body may legally be placed so that it starts in contact without penetrating.
    support_z_m: float | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "collider_id": self.collider_id,
            "collider_type": self.collider_type,
            "position_m": list(self.position_m),
            "quaternion_xyzw": list(self.quaternion_xyzw),
            "concave": self.concave,
        }
        for key, value in (
            ("uri", self.uri),
            ("source_object_id", self.source_object_id),
            ("triangles", self.triangles),
            ("support_z_m", self.support_z_m),
        ):
            if value is not None:
                out[key] = value
        if self.half_extents_m is not None:
            out["half_extents_m"] = list(self.half_extents_m)
        return out


@dataclass
class MultibodyResult:
    """The N-body analogue of ``SimulationResult``.

    ``trajectory`` is keyed by ``instance_id``; substeps and contacts are stored as
    ordered lists so raw causal evidence is never collapsed.
    """

    bodies: list[BodySpec]
    trajectories: dict[str, list[BodyState]]  # noqa: F821 - forward ref, see below
    substeps: list[SubstepState] = field(default_factory=list)
    contacts: list[ContactRecord] = field(default_factory=list)
    events: list[ContactEpisode] = field(default_factory=list)
    static_colliders: list[StaticCollider] = field(default_factory=list)
    physics_fps: float = 480.0
    video_fps: float = 24.0
    frame_count: int = 0
    seed: int | None = None
    run_id: str | None = None

    def instance_ids(self) -> list[str]:
        return [b.instance_id for b in self.bodies]

    def body(self, instance_id: str) -> BodySpec:
        for b in self.bodies:
            if b.instance_id == instance_id:
                return b
        raise ContractError(f"unknown instance_id: {instance_id!r}")

    def dynamic_bodies(self) -> list[BodySpec]:
        return [b for b in self.bodies if b.is_dynamic]

    def validate_identity(self) -> None:
        """Duplicate or missing identity is a hard error, not a warning.

        Two bodies sharing an ``instance_id`` would silently merge in every dict keyed
        by it, so the contract refuses them up front.
        """
        seen: set[str] = set()
        for b in self.bodies:
            if b.instance_id in seen:
                raise ContractError(f"duplicate instance_id: {b.instance_id!r}")
            seen.add(b.instance_id)
        for c in self.static_colliders:
            if c.collider_id in seen:
                raise ContractError(
                    f"static collider id collides with a body: {c.collider_id!r}"
                )
            seen.add(c.collider_id)
        for iid in self.trajectories:
            if iid not in seen:
                raise ContractError(f"trajectory for unknown instance_id: {iid!r}")

    def validate_time(self) -> None:
        """Frame/time monotonicity and 0-based agreement across all records."""
        for iid, states in self.trajectories.items():
            frames = [s.frame for s in states]
            if frames and frames[0] != 0:
                raise ContractError(f"{iid}: first frame must be 0, got {frames[0]}")
            if frames != sorted(frames):
                raise ContractError(f"{iid}: frames are not monotonically increasing")
            for s in states:
                expected = frame_time_s(s.frame, self.video_fps)
                if abs(s.time_seconds - expected) > 1e-9:
                    raise ContractError(
                        f"{iid} frame {s.frame}: time_seconds={s.time_seconds} "
                        f"but frame/video_fps={expected}"
                    )
        steps = [r.step for r in self.contacts]
        if steps != sorted(steps):
            raise ContractError("contacts are not ordered by substep")
        for r in self.contacts:
            expected = substep_time_s(r.step, self.physics_fps)
            if abs(r.time_s - expected) > 1e-9:
                raise ContractError(
                    f"contact step {r.step}: time_s={r.time_s} but step/physics_fps={expected}"
                )

    def validate_quaternions(self) -> None:
        """Every stored quaternion must be a usable unit xyzw rotation.

        A non-unit quaternion silently scales the body when applied, which would make a
        replay disagree with the solve it came from.  Stage 04's counterexample suite
        requires the contract to reject this rather than carry it into a render.
        """
        for spec in self.bodies:
            q = tuple(float(v) for v in spec.quaternion_xyzw)
            if len(q) != 4:
                raise ContractError(
                    f"{spec.instance_id}: quaternion must have 4 components, got {len(q)}"
                )
            norm = math.sqrt(sum(v * v for v in q))
            if abs(norm - 1.0) > 1e-6:
                raise ContractError(
                    f"{spec.instance_id}: quaternion_xyzw is not unit length "
                    f"(norm={norm!r}); a non-unit quaternion silently scales the body"
                )
        for iid, states in self.trajectories.items():
            for state in states:
                q = tuple(float(v) for v in state.quaternion)
                if len(q) != 4:
                    raise ContractError(
                        f"{iid} frame {state.frame}: quaternion must have 4 components"
                    )
                norm = math.sqrt(sum(v * v for v in q))
                if abs(norm - 1.0) > 1e-6:
                    raise ContractError(
                        f"{iid} frame {state.frame}: quaternion is not unit length "
                        f"(norm={norm!r})"
                    )
        for record in self.substeps:
            q = tuple(float(v) for v in record.quaternion_xyzw)
            norm = math.sqrt(sum(v * v for v in q))
            if abs(norm - 1.0) > 1e-6:
                raise ContractError(
                    f"{record.instance_id} step {record.step}: quaternion_xyzw is not unit "
                    f"length (norm={norm!r})"
                )

    def validate_no_passive_actors(self) -> None:
        """Refuse a 'chain' in which nothing can move.

        Stage 01 established that every object being passive produces no chain at all,
        so a result with zero dynamic bodies is rejected rather than reported as a
        successful (but static) simulation.
        """
        if not self.dynamic_bodies():
            raise ContractError(
                "no dynamic bodies: a chain requires at least one body with mass > 0"
            )

    def validate(self) -> None:
        self.validate_identity()
        self.validate_time()
        self.validate_quaternions()
        self.validate_no_passive_actors()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "seed": self.seed,
            "physics_fps": self.physics_fps,
            "video_fps": self.video_fps,
            "frame_count": self.frame_count,
            "substeps_per_frame": substeps_per_frame(self.physics_fps, self.video_fps),
            "time_convention": {
                "frame_is_zero_based": True,
                "blender_frame_number": "frame + 1",
                "substep_interval": "((k-1)*dt, k*dt]",
                "substep_time_s": "k * dt",
                "quaternion_order": "xyzw",
                "matrix_serialization": "row-major",
            },
            "bodies": [b.to_dict() for b in self.bodies],
            "static_colliders": [c.to_dict() for c in self.static_colliders],
            "trajectories": {
                iid: [s.to_dict() for s in states]
                for iid, states in self.trajectories.items()
            },
            "substeps": [s.to_dict() for s in self.substeps],
            "contacts": [c.to_dict() for c in self.contacts],
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MultibodyResult":
        from physim.physics import BodyState  # local import avoids a cycle

        bodies = []
        for raw in data.get("bodies", []):
            item = dict(raw)
            # Drop derived/frozen-format keys that are not constructor parameters.
            # ``is_dynamic`` is a computed property and the *_4x4 keys arrive flattened,
            # so both must be handled explicitly rather than passed through.
            item.pop("is_dynamic", None)
            for key in ("visual_to_body_4x4", "collision_to_body_4x4"):
                if key in item and item[key] is not None and len(item[key]) == 16:
                    item[key] = mat4_unflatten(item[key])
            item.setdefault("mass_range_kg", None)
            if item.get("mass_range_kg") is not None:
                item["mass_range_kg"] = tuple(item["mass_range_kg"])
            for key in (
                "position_m",
                "quaternion_xyzw",
                "linear_velocity_m_s",
                "angular_velocity_rad_s",
                "com_local_m",
                "inertia_diagonal_kg_m2",
            ):
                if item.get(key) is not None:
                    item[key] = tuple(item[key])
            bodies.append(BodySpec(**item))

        trajectories: dict[str, list[Any]] = {}
        for iid, states in data.get("trajectories", {}).items():
            trajectories[iid] = [
                BodyState(
                    frame=int(s["frame"]),
                    time_seconds=float(s["time_seconds"]),
                    position=tuple(float(v) for v in s["position"]),
                    quaternion=tuple(float(v) for v in s["quaternion"]),
                    linear_velocity=tuple(float(v) for v in s["linear_velocity"]),
                    angular_velocity=tuple(float(v) for v in s["angular_velocity"]),
                )
                for s in states
            ]

        colliders = []
        for raw in data.get("static_colliders", []):
            item = dict(raw)
            item["position_m"] = tuple(item.get("position_m", (0.0, 0.0, 0.0)))
            item["quaternion_xyzw"] = tuple(item.get("quaternion_xyzw", (0.0, 0.0, 0.0, 1.0)))
            if item.get("half_extents_m") is not None:
                item["half_extents_m"] = tuple(item["half_extents_m"])
            item.setdefault("concave", False)
            colliders.append(StaticCollider(**item))

        events = []
        for raw in data.get("events", []):
            item = dict(raw)
            item.pop("impulse_proxy_is_estimate", None)
            events.append(ContactEpisode(**item))

        return cls(
            bodies=bodies,
            trajectories=trajectories,
            substeps=[SubstepState.from_dict(s) for s in data.get("substeps", [])],
            contacts=[ContactRecord.from_dict(c) for c in data.get("contacts", [])],
            events=events,
            static_colliders=colliders,
            physics_fps=float(data.get("physics_fps", 480.0)),
            video_fps=float(data.get("video_fps", 24.0)),
            frame_count=int(data.get("frame_count", 0)),
            seed=data.get("seed"),
            run_id=data.get("run_id"),
        )


# ---------------------------------------------------------------------------
# adapters to the pre-existing single-actor types
# ---------------------------------------------------------------------------


def to_body_state(state: SubstepState | Any, video_fps: float) -> Any:
    """Convert a contract state to ``physim.physics.BodyState`` (``wxyz`` quaternion).

    ``BodyState.quaternion`` predates this contract and is consumed by the Blender
    renderer, which expects ``wxyz``.  The conversion is explicit here and nowhere else.
    """
    from physim.physics import BodyState

    if isinstance(state, SubstepState):
        frame = int(round(state.time_s * video_fps))
        return BodyState(
            frame=frame,
            time_seconds=frame / float(video_fps),
            position=tuple(state.position_m),
            quaternion=quat_to_wxyz(state.quaternion_xyzw),
            linear_velocity=tuple(state.linear_velocity_m_s),
            angular_velocity=tuple(state.angular_velocity_rad_s),
        )
    return state


def from_body_state(state: Any, instance_id: str, step: int, physics_fps: float) -> SubstepState:
    """Convert a legacy ``BodyState`` (``wxyz``) into a contract ``SubstepState``."""
    return SubstepState(
        instance_id=instance_id,
        step=step,
        time_s=substep_time_s(step, physics_fps),
        position_m=tuple(float(v) for v in state.position),
        quaternion_xyzw=quat_from_wxyz(state.quaternion),
        linear_velocity_m_s=tuple(float(v) for v in state.linear_velocity),
        angular_velocity_rad_s=tuple(float(v) for v in state.angular_velocity),
    )


def episodes_from_contacts(
    contacts: Sequence[ContactRecord], gap_tolerance: int = 1
) -> list[ContactEpisode]:
    """Aggregate adjacent substeps of the same body pair into episodes.

    ``gap_tolerance`` bridges at most that many consecutive empty substeps, and the
    bridged count is recorded on the episode so the raw list remains the authority.
    A contact touching static scenery is classified separately, so ground contact can
    never be mistaken for chain propagation.
    """
    by_pair: dict[frozenset[str], list[ContactRecord]] = {}
    for record in contacts:
        by_pair.setdefault(record.pair, []).append(record)

    episodes: list[ContactEpisode] = []
    for pair, records in by_pair.items():
        ordered = sorted(records, key=lambda r: r.step)
        a, b = sorted(pair)
        run: list[ContactRecord] = []
        gap = 0

        def flush(items: list[ContactRecord], bridged: int) -> None:
            if not items:
                return
            # Classify from the RECORD, not from the (sorted) episode pair, because
            # sorting the pair loses which side was static.  Ground contact is scenery
            # resting contact; a two-dynamic-body contact is potential propagation.
            # NOTE: test for the "static:ground" NAME, not membership of the bare word
            # in a tuple -- ``"ground" in (a, b)`` is exact-equality and never matches
            # the prefixed id.
            kind = "dynamic"
            if items[0].involves_static:
                static_names = [
                    n
                    for n in (items[0].instance_a, items[0].instance_b)
                    if n.startswith("static:")
                ]
                is_ground = any(n.split(":", 1)[1] == "ground" for n in static_names)
                kind = "ground" if is_ground else "static_support"
            episodes.append(
                ContactEpisode(
                    instance_a=a,
                    instance_b=b,
                    step_start=items[0].step,
                    step_end=items[-1].step,
                    time_start_s=items[0].time_s,
                    time_end_s=items[-1].time_s,
                    substeps=len(items),
                    gap_tolerance=bridged,
                    peak_normal_force_n=max(i.normal_force_n for i in items),
                    impulse_proxy_n_s=sum(i.normal_force_n for i in items),
                    contact_kind=kind,
                )
            )

        for record in ordered:
            if not run:
                run = [record]
                continue
            if record.step - run[-1].step <= gap_tolerance + 1:
                gap += max(0, record.step - run[-1].step - 1)
                run.append(record)
            else:
                flush(run, gap)
                run, gap = [record], 0
        flush(run, gap)

    episodes.sort(key=lambda e: (e.step_start, e.instance_a, e.instance_b))
    return episodes


def content_sha256(path: str | Path) -> str:
    """SHA-256 of a file, used to bind provenance to actual bytes."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> int:
    """Write JSON Lines, returning the record count.  Never deletes or truncates a
    previous file: callers allocate a fresh run directory first."""
    target = Path(path)
    if target.exists():
        raise ContractError(f"refusing to overwrite an existing record file: {target}")
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            count += 1
    return count


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)
