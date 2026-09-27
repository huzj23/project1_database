"""Low-cost, scenario-aware validation before expensive rendering."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from physim.maps import SurfaceSpec
from physim.physics import SimulationResult
from physim.scenarios import ScenarioSample


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    reasons: tuple[str, ...]
    travel_distance: float
    trajectory_extent: float
    trajectory_extent_object_ratio: float
    max_linear_speed: float
    supported_fraction: float
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _expected_support_z(sample: ScenarioSample, surface: SurfaceSpec) -> float:
    """z of the surface the actor is expected to rest on.

    For every pre-existing scenario this is the map surface's own z.  A sample
    that rides a driven support body (the turntable) declares the height it
    actually rests on -- the disc's TOP face -- because reusing the table's
    z would put the expected height 22 mm below the actor and collapse
    ``supported_fraction``.
    """
    declared = getattr(sample, "actor_support_z", None)
    return float(surface.position[2]) if declared is None else float(declared)


def _measure(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, float]]:
    if not result.trajectory:
        raise ValueError("Simulation produced no trajectory states")
    positions = np.asarray([state.position for state in result.trajectory], dtype=np.float64)
    velocities = np.asarray(
        [state.linear_velocity for state in result.trajectory], dtype=np.float64
    )
    reasons: list[str] = []
    if not np.isfinite(positions).all() or not np.isfinite(velocities).all():
        reasons.append("non_finite_state")
    travel = float(np.linalg.norm(positions[-1] - positions[0]))
    trajectory_extent = float(np.linalg.norm(positions.max(axis=0) - positions.min(axis=0)))
    object_extent = max(2.0 * sample.radius, 2.0 * sample.support_height)
    extent_ratio = trajectory_extent / object_extent
    max_speed = float(np.linalg.norm(velocities, axis=1).max())
    expected_z = _expected_support_z(sample, surface) + sample.support_height
    supported_fraction = float(np.mean(np.abs(positions[:, 2] - expected_z) <= 0.03))
    if max_speed > float(config.get("max_linear_speed", float("inf"))):
        reasons.append("excessive_speed")
    max_ratio = float(config.get("max_trajectory_extent_object_ratio", float("inf")))
    if extent_ratio > max_ratio:
        reasons.append("trajectory_too_large_for_object")
    if config.get("require_in_map_bounds", True):
        inside = np.asarray(
            [
                surface.contains_xy(float(position[0]), float(position[1]), sample.radius)
                for position in positions
            ]
        )
        if not bool(np.all(inside)):
            reasons.append("outside_surface_bounds")
    metrics = {
        "travel_distance": travel,
        "trajectory_extent": trajectory_extent,
        "trajectory_extent_object_ratio": extent_ratio,
        "max_linear_speed": max_speed,
        "supported_fraction": supported_fraction,
    }
    return positions, velocities, reasons, metrics


def _report(reasons: list[str], metrics: dict[str, Any]) -> ValidationReport:
    return ValidationReport(
        valid=not reasons,
        reasons=tuple(reasons),
        travel_distance=float(metrics["travel_distance"]),
        trajectory_extent=float(metrics["trajectory_extent"]),
        trajectory_extent_object_ratio=float(
            metrics["trajectory_extent_object_ratio"]
        ),
        max_linear_speed=float(metrics["max_linear_speed"]),
        supported_fraction=float(metrics["supported_fraction"]),
        metrics=metrics,
    )


def validate_rolling(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> ValidationReport:
    positions, velocities, reasons, metrics = _measure(result, sample, surface, config)
    if config.get("reject_initial_overlap", True):
        initial_bottom = float(positions[0, 2] - sample.support_height)
        if initial_bottom < float(surface.position[2]) - 0.005:
            reasons.append("initial_surface_penetration")
    object_extent = max(2.0 * sample.radius, 2.0 * sample.support_height)
    minimum_travel = max(
        float(config.get("min_travel_distance", 0.0)),
        float(config.get("min_travel_object_extent_ratio", 0.0)) * object_extent,
    )
    if metrics["travel_distance"] < minimum_travel:
        reasons.append("insufficient_travel")
    if config.get("require_supported", True) and metrics["supported_fraction"] < 0.9:
        reasons.append("not_supported")
    planar_speeds = np.linalg.norm(velocities[:, :2], axis=1)
    initial_speed = max(float(planar_speeds[0]), 1e-9)
    speed_relative_change = float(
        np.max(np.abs(planar_speeds - planar_speeds[0])) / initial_speed
    )
    if speed_relative_change > float(
        config.get("max_speed_relative_change", float("inf"))
    ):
        reasons.append("non_uniform_speed")
    metrics["max_speed_relative_change"] = speed_relative_change
    metrics["minimum_travel_distance"] = minimum_travel
    return _report(reasons, metrics)


def validate_constant_force(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> ValidationReport:
    positions, velocities, reasons, metrics = _measure(result, sample, surface, config)
    if config.get("reject_initial_overlap", True):
        initial_bottom = float(positions[0, 2] - sample.support_height)
        if initial_bottom < float(surface.position[2]) - 0.005:
            reasons.append("initial_surface_penetration")
    if metrics["travel_distance"] < float(config["min_travel_distance"]):
        reasons.append("insufficient_travel")
    if config.get("require_supported", True) and metrics["supported_fraction"] < 0.9:
        reasons.append("not_supported")
    force_xy = np.asarray(sample.constant_force[:2], dtype=np.float64)
    force_norm = float(np.linalg.norm(force_xy))
    if force_norm <= 1e-12:
        reasons.append("missing_constant_force")
        measured_acceleration = 0.0
    else:
        direction = force_xy / force_norm
        measured_acceleration = float(
            np.dot(velocities[-1, :2] - velocities[0, :2], direction)
            / max(result.trajectory[-1].time_seconds, 1e-9)
        )
        if measured_acceleration < float(config.get("min_force_response", 0.01)):
            reasons.append("insufficient_force_response")
    times = np.asarray(
        [state.time_seconds for state in result.trajectory], dtype=np.float64
    )
    if force_norm > 1e-12 and len(times) > 2:
        direction = force_xy / force_norm
        projected_speeds = velocities[:, :2] @ direction
        accelerations = np.diff(projected_speeds) / np.diff(times)
        acceleration_mean = float(np.mean(accelerations))
        acceleration_std = float(np.std(accelerations))
        acceleration_relative_std = acceleration_std / max(abs(acceleration_mean), 1e-9)
        if acceleration_relative_std > float(
            config.get("max_acceleration_relative_std", float("inf"))
        ):
            reasons.append("non_uniform_acceleration")
    else:
        acceleration_relative_std = 0.0
    metrics["measured_force_direction_acceleration"] = measured_acceleration
    metrics["acceleration_relative_std"] = acceleration_relative_std
    return _report(reasons, metrics)


def validate_free_fall(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> ValidationReport:
    positions, velocities, reasons, metrics = _measure(result, sample, surface, config)
    ground_center_z = float(surface.position[2] + sample.support_height)
    drop_distance = float(positions[0, 2] - positions[:, 2].min())
    contact_frames = tuple(float(item["frame"]) for item in result.collisions)
    if positions[0, 2] <= ground_center_z + float(config.get("min_drop_height", 0.1)):
        reasons.append("insufficient_initial_height")
    if drop_distance < float(config.get("min_drop_distance", 0.1)):
        reasons.append("insufficient_drop")
    if config.get("require_expected_collision", True) and not contact_frames:
        reasons.append("missing_ground_collision")
    first_contact_frame = min(contact_frames) if contact_frames else float("inf")
    post_contact_indices = [
        index
        for index, state in enumerate(result.trajectory)
        if float(state.frame - 1) >= first_contact_frame
    ]
    upward_speed = (
        float(velocities[post_contact_indices[0] :, 2].max())
        if post_contact_indices
        else 0.0
    )
    if config.get("require_bounce", True) and upward_speed < float(
        config.get("min_bounce_upward_speed", 0.05)
    ):
        reasons.append("missing_bounce")
    penetration = float(max(0.0, ground_center_z - positions[:, 2].min()))
    if penetration > float(config.get("max_surface_penetration", 0.03)):
        reasons.append("excessive_surface_penetration")
    metrics.update(
        {
            "drop_distance": drop_distance,
            "collision_count": len(contact_frames),
            "first_collision_frame": (
                first_contact_frame if contact_frames else None
            ),
            "max_post_contact_upward_speed": upward_speed,
            "max_surface_penetration": penetration,
        }
    )
    return _report(reasons, metrics)


def validate_free_fall_soft(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> ValidationReport:
    """Free fall for a SOFT actor: a real impact, then it settles.

    The mentor's `validate_free_fall` requires a measurable rebound, which is
    right for a ball and wrong for a plush toy -- a teddy that bounces like a
    basketball would be the unrealistic result.  This variant keeps every
    geometric guarantee (real contact, negligible penetration, stays in bounds,
    stays on the support) and replaces "must bounce" with "must come to rest",
    while additionally capping the rebound so a mis-tuned restitution cannot
    masquerade as a bouncy ball.
    """
    positions, velocities, reasons, metrics = _measure(result, sample, surface, config)
    ground_center_z = float(surface.position[2] + sample.support_height)
    drop_distance = float(positions[0, 2] - positions[:, 2].min())
    contact_frames = tuple(float(item["frame"]) for item in result.collisions)

    if positions[0, 2] <= ground_center_z + float(config.get("min_drop_height", 0.1)):
        reasons.append("insufficient_initial_height")
    if drop_distance < float(config.get("min_drop_distance", 0.1)):
        reasons.append("insufficient_drop")
    if config.get("require_expected_collision", True) and not contact_frames:
        reasons.append("missing_ground_collision")

    penetration = float(max(0.0, ground_center_z - positions[:, 2].min()))
    if penetration > float(config.get("max_surface_penetration", 0.03)):
        reasons.append("excessive_surface_penetration")

    # settle: the tail of the trajectory must be essentially motionless
    tail = max(3, len(velocities) // 5)
    tail_speed = float(np.linalg.norm(velocities[-tail:], axis=1).max())
    if tail_speed > float(config.get("max_settle_speed", 0.05)):
        reasons.append("did_not_settle")

    # rebound must stay small, i.e. it really is a soft body
    first_contact = min(contact_frames) if contact_frames else float("inf")
    post = [i for i, s in enumerate(result.trajectory)
            if float(s.frame - 1) >= first_contact]
    rebound = float(velocities[post[0]:, 2].max()) if post else 0.0
    if rebound > float(config.get("max_soft_rebound_speed", 0.35)):
        reasons.append("rebound_too_large_for_soft_actor")

    metrics.update({
        "drop_distance": drop_distance,
        "collision_count": len(contact_frames),
        "max_surface_penetration": penetration,
        "settle_tail_speed": tail_speed,
        "soft_rebound_speed": rebound,
    })
    return _report(reasons, metrics)


def validate_damping(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> ValidationReport:
    """Validate exponentially attenuated motion.

    Damping is exponential (v = v0 * exp(-k*t)), unlike Coulomb friction which is
    linear and reaches zero in finite time.  The checks therefore are:

      * the speed must DECREASE monotonically (a damping coefficient that fails to
        act would leave it constant; an unstable contact would make it rise)
      * the final speed must be a real fraction of the initial speed -- strictly
        between the two extremes, proving attenuation happened without the body
        simply being stopped by an impact
      * the body must stay on the support, and travel far enough to be visible
    """
    positions, velocities, reasons, metrics = _measure(result, sample, surface, config)
    if config.get("reject_initial_overlap", True):
        initial_bottom = float(positions[0, 2] - sample.support_height)
        if initial_bottom < float(surface.position[2]) - 0.005:
            reasons.append("initial_surface_penetration")

    object_extent = max(2.0 * sample.radius, 2.0 * sample.support_height)
    minimum_travel = max(
        float(config.get("min_travel_distance", 0.0)),
        float(config.get("min_travel_object_extent_ratio", 0.0)) * object_extent,
    )
    if metrics["travel_distance"] < minimum_travel:
        reasons.append("insufficient_travel")
    if config.get("require_supported", True) and metrics["supported_fraction"] < 0.9:
        reasons.append("not_supported")

    planar_speeds = np.linalg.norm(velocities[:, :2], axis=1)
    initial_speed = float(planar_speeds[0])
    final_speed = float(planar_speeds[-1])
    if initial_speed <= 1e-9:
        reasons.append("no_initial_motion")
        decay_ratio = 1.0
    else:
        decay_ratio = final_speed / initial_speed
        # Attenuation must actually occur.
        if decay_ratio > float(config.get("max_decay_ratio", 0.95)):
            reasons.append("insufficient_damping")
        # ...but the body must not be arrested almost immediately, which would mean
        # the coefficient is so large the motion is a stop rather than a decay.
        if decay_ratio < float(config.get("min_decay_ratio", 0.02)):
            reasons.append("over_damped")
        # Monotonic decay: allow a small tolerance for contact jitter.
        rises = np.diff(planar_speeds) > float(config.get("speed_rise_tolerance", 0.02))
        if int(np.count_nonzero(rises)) > int(config.get("max_speed_rises", 3)):
            reasons.append("non_monotonic_decay")

    # Compare against the analytic exponential the coefficient implies.  This is a
    # measurement of the solver's behaviour, not a prescribed trajectory: a large
    # deviation means damping is not the mechanism producing the motion.
    expected_ratio = float(
        np.exp(-float(getattr(sample, "linear_damping", 0.0))
               * float(result.trajectory[-1].time_seconds))
    )
    metrics["damping_decay_ratio"] = decay_ratio
    metrics["damping_expected_ratio"] = expected_ratio
    metrics["damping_ratio_error"] = abs(decay_ratio - expected_ratio)
    if config.get("max_decay_ratio_error") is not None:
        if metrics["damping_ratio_error"] > float(config["max_decay_ratio_error"]):
            reasons.append("damping_decay_mismatch")
    return _report(reasons, metrics)


def _turntable_geometry(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, Any], np.ndarray]:
    """Shared measurement for both turntable motions.

    Adds the quantities that make "carried by the disc" a measurable claim
    rather than a visual impression:

    ``net_arc_degrees``
        Net signed angle swept by the actor about the disc AXIS, accumulated
        from consecutive frames so it is unwrapped and can exceed 360 deg.  This
        is the circular travel the scenario is about.
    ``net_radial_displacement``
        How far the actor moved toward or away from the axis, start to end.  A
        genuine circular carry has a large arc with a small radial change;
        a straight slide off the disc has a large radial change.
    ``max_radius`` / ``mean_radius``
        Distance from the axis, against the disc radius -- the "stays on the
        disc" check.
    ``disc_rotation_degrees``
        Net rotation of the DISC itself, measured from its quaternion, so #6
        can require that the disc really turned instead of trusting the
        commanded omega.
    ``radial_fraction_of_travel``
        Fraction of the actor's total path length that was spent moving radially.
        Near zero means the path was genuinely circular.
    """
    positions, velocities, reasons, metrics = _measure(result, sample, surface, config)
    if sample.support_position is None:
        raise ValueError("Turntable validation requires a declared support body")
    axis = np.asarray(sample.support_position[:2], dtype=np.float64)
    radius = float(sample.support_radius)
    if radius <= 0:
        raise ValueError("Turntable validation requires a positive disc radius")

    offsets = positions[:, :2] - axis
    radii = np.linalg.norm(offsets, axis=1)
    angles = np.unwrap(np.arctan2(offsets[:, 1], offsets[:, 0]))
    net_arc_degrees = float(np.degrees(angles[-1] - angles[0]))
    net_radial_displacement = float(radii[-1] - radii[0])
    max_radius = float(radii.max())
    mean_radius = float(radii.mean())

    # Path length split into circumferential and radial components.  Theta is
    # the unwrapped angle, so the tangential step is r * d(theta).
    steps = np.diff(offsets, axis=0)
    path_length = float(np.linalg.norm(steps, axis=1).sum())
    tangential = np.abs(np.diff(angles)) * radii[:-1]
    radial = np.abs(np.diff(radii))
    radial_fraction = float(
        radial.sum() / max(radial.sum() + tangential.sum(), 1e-12)
    )

    disc_rotation_degrees = 0.0
    if result.support_trajectory:
        disc_quaternions = np.asarray(
            [state.quaternion for state in result.support_trajectory], dtype=np.float64
        )
        disc_rotation_degrees = _yaw_degrees(disc_quaternions)

    # Slip: how much of the disc's own surface motion the actor actually
    # followed.  1.0 means it rides the disc exactly, 0.0 means the disc spins
    # underneath it without coupling.  Measured, never commanded.
    expected_arc = abs(disc_rotation_degrees)
    slip_ratio = (
        abs(net_arc_degrees) / expected_arc if expected_arc > 1e-6 else 0.0
    )

    if config.get("reject_initial_overlap", True):
        # The actor must start ON the disc, not inside the table below it.
        expected_z = _expected_support_z(sample, surface) + sample.support_height
        if positions[0, 2] < expected_z - 0.01:
            reasons.append("initial_support_penetration")
    if config.get("require_supported", True) and metrics["supported_fraction"] < float(
        config.get("min_supported_fraction", 0.9)
    ):
        reasons.append("not_supported")

    metrics.update(
        {
            "disc_radius": radius,
            "orbit_radius": float(sample.orbit_radius),
            "start_radius": float(radii[0]),
            "max_radius": max_radius,
            "mean_radius": mean_radius,
            "net_arc_degrees": net_arc_degrees,
            "net_radial_displacement": net_radial_displacement,
            "path_length": path_length,
            "radial_fraction_of_travel": radial_fraction,
            "disc_rotation_degrees": disc_rotation_degrees,
            "slip_ratio": slip_ratio,
            "support_contact_frames": len(result.collisions),
        }
    )
    return positions, velocities, reasons, metrics, radii


def _yaw_degrees(quaternions: np.ndarray) -> float:
    """Net rotation about Z accumulated from consecutive wxyz quaternions.

    Each frame's absolute yaw is read from the rotation matrix and the
    difference between consecutive frames is wrapped to (-pi, pi] before being
    summed, so the total is unwrapped and may exceed 360 deg.

    Reading a single quaternion's yaw would alias at +-180 deg (a 400 deg spin
    would report 40 deg), and a naive relative-quaternion formula gets the sign
    convention wrong -- both were observed and are why this is derived from the
    matrix and unit-checked against a known constant-rate spin.
    """
    total = 0.0
    previous = None
    for w, x, y, z in quaternions:
        # Yaw of this orientation, straight from R = f(w,x,y,z).
        r00 = 1.0 - 2.0 * (y * y + z * z)
        r10 = 2.0 * (x * y + w * z)
        current = math.atan2(r10, r00)
        if previous is not None:
            delta = current - previous
            while delta > math.pi:
                delta -= 2.0 * math.pi
            while delta < -math.pi:
                delta += 2.0 * math.pi
            total += delta
        previous = current
    return float(math.degrees(total))


def validate_turntable_carry(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> ValidationReport:
    """Motion #5 (圆周运动): the actor is CARRIED around by contact friction.

    The checks are the physical content of that sentence:

      * it stays ON the disc -- its distance from the axis never exceeds the
        disc radius, so it was not flung off;
      * it actually travelled a CIRCULAR arc -- a large net angular
        displacement about the axis while its radial displacement stays small;
      * it is genuinely carried, not merely sitting there while the disc spins
        underneath -- the measured slip ratio must be substantial;
      * it stays supported and its speed stays bounded.
    """
    positions, velocities, reasons, metrics, radii = _turntable_geometry(
        result, sample, surface, config
    )
    disc_radius = float(sample.support_radius)

    # Stays on the disc.  The margin allows the actor's own footprint to overhang
    # by a little without counting as ejected; a throw-off leaves the radius
    # entirely.
    allowed_radius = disc_radius + float(config.get("max_overhang", 0.02))
    if metrics["max_radius"] > allowed_radius:
        reasons.append("left_the_disc")

    # A real circular carry, not a straight slide: large arc, small radial drift.
    if abs(metrics["net_arc_degrees"]) < float(config.get("min_arc_degrees", 60.0)):
        reasons.append("insufficient_circular_travel")
    if abs(metrics["net_radial_displacement"]) > float(
        config.get("max_radial_displacement", 0.10)
    ):
        reasons.append("path_not_circular")
    if metrics["radial_fraction_of_travel"] > float(
        config.get("max_radial_fraction_of_travel", 0.35)
    ):
        reasons.append("travel_not_tangential")

    # Carried by friction, rather than the disc spinning underneath.
    if metrics["slip_ratio"] < float(config.get("min_slip_ratio", 0.5)):
        reasons.append("not_carried_by_contact")

    # Bounded motion, and the disc really turned.
    if metrics["max_linear_speed"] > float(
        config.get("max_linear_speed", float("inf"))
    ):
        reasons.append("excessive_speed")
    if abs(metrics["disc_rotation_degrees"]) < float(
        config.get("min_disc_rotation_degrees", 20.0)
    ):
        reasons.append("disc_did_not_rotate")
    metrics["allowed_radius"] = allowed_radius
    return _report(reasons, metrics)


def validate_turntable_spin(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> ValidationReport:
    """Motion #6 (转盘自转): the disc spins and the actor co-rotates in place.

    Here the subject is the ROTATION rather than a large arc, so the checks are:

      * the disc really rotated -- measured from its quaternion, by a
        configured minimum, so a disc that failed to turn is rejected even
        though the commanded omega was non-zero;
      * the actor co-rotated with it instead of being left behind or thrown off
        -- it must stay near its spawn radius and must not drift far;
      * it stays on the disc and supported, with bounded speed.
    """
    positions, velocities, reasons, metrics, radii = _turntable_geometry(
        result, sample, surface, config
    )
    disc_radius = float(sample.support_radius)

    # The disc must actually have turned.
    if abs(metrics["disc_rotation_degrees"]) < float(
        config.get("min_disc_rotation_degrees", 60.0)
    ):
        reasons.append("disc_did_not_rotate")

    # The actor rides it: it co-rotates (slip high) without flying off.
    if abs(metrics["net_arc_degrees"]) < float(config.get("min_arc_degrees", 20.0)):
        reasons.append("actor_did_not_corotate")
    if metrics["slip_ratio"] < float(config.get("min_slip_ratio", 0.5)):
        reasons.append("not_carried_by_contact")
    if metrics["max_radius"] > disc_radius + float(config.get("max_overhang", 0.02)):
        reasons.append("left_the_disc")

    # "Stays put" means it does not wander across the disc, and does not drift
    # away from where it was placed.
    if abs(metrics["net_radial_displacement"]) > float(
        config.get("max_radial_displacement", 0.06)
    ):
        reasons.append("actor_drifted_radially")
    if metrics["max_radius"] - metrics["start_radius"] > float(
        config.get("max_radial_growth", 0.06)
    ):
        reasons.append("actor_drifted_outward")
    if metrics["max_linear_speed"] > float(
        config.get("max_linear_speed", float("inf"))
    ):
        reasons.append("excessive_speed")
    return _report(reasons, metrics)


def validate_sample(
    result: SimulationResult,
    sample: ScenarioSample,
    surface: SurfaceSpec,
    config: dict[str, Any],
) -> ValidationReport:
    if sample.scenario == "rolling":
        return validate_rolling(result, sample, surface, config)
    if sample.scenario == "constant_force":
        return validate_constant_force(result, sample, surface, config)
    if sample.scenario == "damping":
        return validate_damping(result, sample, surface, config)
    if sample.scenario == "turntable_carry":
        return validate_turntable_carry(result, sample, surface, config)
    if sample.scenario == "turntable_spin":
        return validate_turntable_spin(result, sample, surface, config)
    if sample.scenario == "free_fall":
        # soft actors settle instead of bouncing; see validate_free_fall_soft
        if str(getattr(sample, "material_class", "") or "").lower() in ("soft", "plush"):
            return validate_free_fall_soft(result, sample, surface, config)
        return validate_free_fall(result, sample, surface, config)
    raise KeyError(f"No validator registered for scenario {sample.scenario!r}")
