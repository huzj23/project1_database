"""Motion drivers for single-object, non-interactive physics scenarios.

Two families are implemented:

``circular``
    A single object traces a **fixed circular trajectory**.  The trajectory is
    analytic (kinematic keyframing) rather than integrated, which guarantees a
    perfectly closed, repeatable loop -- ideal for a ground-truth physics
    annotation.  Velocity and centripetal acceleration are computed in closed
    form and written per frame, so the asset carries exact physical labels even
    though the path is prescribed.

``damped``
    A single object is given an initial velocity and then left to PyBullet:
    linear/angular damping plus Coulomb friction dissipate energy.  This is a
    genuine rigid-body integration, so the per-frame labels are read back from
    the solver.

Both produce the same annotation structure:
``{frame: {object_name: {position, quaternion, velocity, angular_velocity, ...}}}``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np


# --------------------------------------------------------------------------------------
# Circular motion
# --------------------------------------------------------------------------------------

@dataclass
class CircularSpec:
    """Parameters of a fixed circular trajectory.

    The trajectory is parameterised the way a physicist would: by the circle
    **radius** and the **period** of one revolution.  Angular speed, tangential
    speed and centripetal acceleration are all derived, which keeps the
    resulting numbers in a physically sensible range regardless of clip length.
    """

    radius: float = 1.2
    #: seconds per revolution (the primary physical control)
    period_s: float = 2.0
    #: centre of the circle
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    #: plane normal; "z" == horizontal circle
    axis: str = "z"
    #: body self-rotation expressed as revolutions per *orbit* (0 == no spin)
    spin_per_orbit: float = 1.0
    #: launch phase in radians
    phase0: float = 0.0

    @property
    def omega(self) -> float:
        if self.period_s <= 0:
            raise ValueError("period_s must be > 0")
        return 2.0 * math.pi / self.period_s

    @property
    def tangential_speed(self) -> float:
        return abs(self.radius * self.omega)

    @property
    def centripetal_accel(self) -> float:
        return abs(self.radius * self.omega * self.omega)


def quat_to_matrix(q) -> np.ndarray:
    """Rotation matrix from a (w, x, y, z) quaternion."""
    w, x, y, z = (float(v) for v in q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def keyframe_states(obj, states: Dict[int, dict],
                    origin_offset_local=None) -> None:
    """Write per-frame states onto a Kubric asset as Blender keyframes.

    The trajectories produced by this module are expressed at the body's
    **centre of mass**, which is the physically meaningful quantity to annotate.
    A ``FileBasedObject``'s ``position`` trait, however, drives the *mesh origin*
    -- and these meshes are not centred on it (the ball's vertices, for example,
    sit around local ``z = 1.0``, exactly its URDF inertial origin).

    So we convert::

        mesh_origin_world = com_world - R(quaternion) @ (scale * offset_local)

    passing ``origin_offset_local`` scaled by the object's scale.  With no offset
    this reduces to placing the asset straight at the annotated position.
    """
    off = None
    if origin_offset_local is not None:
        off = np.asarray(origin_offset_local, dtype=float)
        if not np.any(off):
            off = None

    for f, s in states.items():
        q = tuple(s["quaternion"])
        pos = np.asarray(s["position"], dtype=float)
        if off is not None:
            pos = pos - quat_to_matrix(q) @ off
        obj.position = tuple(float(v) for v in pos)
        obj.quaternion = q
        obj.velocity = tuple(s["velocity"])
        obj.angular_velocity = tuple(s["angular_velocity"])
        obj.keyframe_insert("position", f)
        obj.keyframe_insert("quaternion", f)
        obj.keyframe_insert("velocity", f)
        obj.keyframe_insert("angular_velocity", f)


def _basis(axis: str):
    if axis == "z":
        return np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
    if axis == "y":
        return np.array([1.0, 0, 0]), np.array([0, 0, 1.0]), np.array([0, 1.0, 0])
    if axis == "x":
        return np.array([0, 1.0, 0]), np.array([0, 0, 1.0]), np.array([1.0, 0, 0])
    raise ValueError(f"axis must be x/y/z, got {axis!r}")


def circular_states(spec: CircularSpec, n_frames: int, fps: float) -> Dict[int, dict]:
    """Exact kinematic states for a fixed circular trajectory.

    Returns a mapping ``frame -> state`` where ``state`` holds position,
    quaternion (w,x,y,z), linear velocity, linear acceleration and angular
    velocity, all in world units.
    """
    e1, e2, n = _basis(spec.axis)
    c = np.asarray(spec.center, dtype=float)
    omega = spec.omega
    # body spin follows the orbit, so the clip is visually self-similar
    spin = omega * spec.spin_per_orbit

    states: Dict[int, dict] = {}
    for f in range(n_frames):
        t = f / fps
        theta = spec.phase0 + omega * t
        ct, st = math.cos(theta), math.sin(theta)

        # position on the circle
        pos = c + spec.radius * (ct * e1 + st * e2)

        # velocity = d/dt position  (tangential)
        vel = spec.radius * omega * (-st * e1 + ct * e2)

        # acceleration = centripetal, magnitude R*omega^2, pointing at the centre
        acc = -spec.radius * omega * omega * (ct * e1 + st * e2)

        # body spin about the circle normal (quaternion, w-x-y-z)
        angle = spec.spin_per_orbit * theta
        quat = (math.cos(angle / 2.0),
                float(math.sin(angle / 2.0) * n[0]),
                float(math.sin(angle / 2.0) * n[1]),
                float(math.sin(angle / 2.0) * n[2]))

        states[f] = {
            "t": t,
            "position": pos.tolist(),
            "quaternion": list(quat),
            "velocity": vel.tolist(),
            "acceleration": acc.tolist(),
            "angular_velocity": (spin * n).tolist(),
            "theta": theta,
            "speed": float(np.linalg.norm(vel)),
            "centripetal_accel": float(np.linalg.norm(acc)),
        }
    return states


def apply_circular(kb, obj, spec: CircularSpec, n_frames: int, fps: float,
                   origin_offset_local=None):
    """Keyframe ``obj`` along the circular trajectory and return its states."""
    states = circular_states(spec, n_frames, fps)
    keyframe_states(obj, states, origin_offset_local)
    return states


# --------------------------------------------------------------------------------------
# Damped motion
# --------------------------------------------------------------------------------------

@dataclass
class DampedSpec:
    """Parameters for the dissipative (exponentially decaying) scenario.

    The trajectory is the closed-form solution of the linear viscous-damping
    model::

        v(t) = v0 * exp(-k t)
        x(t) = x0 + (v0 / k) * (1 - exp(-k t))
        a(t) = -k * v(t)

    This is prescribed rather than solver-integrated on purpose -- see
    :func:`damped_states` for why.
    """

    #: initial linear speed in m/s
    speed: float = 3.0
    #: heading in the XY plane, degrees
    direction_deg: float = 0.0
    #: viscous damping coefficient k in 1/s (the decay rate)
    linear_damping: float = 1.2
    #: angular decay rate in 1/s
    angular_damping: float = 1.5
    #: initial spin about +Z in rad/s
    spin_rate: float = 6.0
    #: starting position
    start: Tuple[float, float, float] = (-1.25, 0.0, 0.9)
    #: spin axis
    axis: str = "z"

    @property
    def travel_distance(self) -> float:
        """Total asymptotic displacement, ``v0 / k``."""
        return self.speed / max(self.linear_damping, 1e-9)

    @property
    def velocity(self) -> Tuple[float, float, float]:
        d = math.radians(self.direction_deg)
        return (self.speed * math.cos(d), self.speed * math.sin(d), 0.0)

    @property
    def start_position(self) -> Tuple[float, float, float]:
        """Start placed half a travel-span *before* the origin, so the run is centred."""
        d = math.radians(self.direction_deg)
        half = 0.5 * self.travel_distance
        return (self.start[0] - half * math.cos(d),
                self.start[1] - half * math.sin(d),
                self.start[2])


def damped_states(spec: DampedSpec, n_frames: int, fps: float) -> Dict[int, dict]:
    """Closed-form states of a linearly damped body.

    Why not let PyBullet integrate this?  Kubric loads every URDF with
    ``useMaximalCoordinates=True``; in that mode this PyBullet build silently
    ignores per-body damping/friction (``changeDynamics`` returns success but
    leaves the values at their defaults, and a URDF ``<dynamics>`` element is
    ignored as well).  Prescribing the exact solution gives labels that are
    *more* accurate than a solver read-back, and makes the asset perfectly
    reproducible.

    Energy bookkeeping is included so the annotation is self-checking:
    ``kinetic_energy`` decays as ``exp(-2 k t)``.
    """
    e1, e2, n = _basis(spec.axis)
    k = max(spec.linear_damping, 1e-9)
    ka = max(spec.angular_damping, 1e-9)
    theta_dir = math.radians(spec.direction_deg)
    heading = math.cos(theta_dir) * e1 + math.sin(theta_dir) * e2
    start = np.asarray(spec.start_position, dtype=float)
    v0 = float(spec.speed)
    w0 = float(spec.spin_rate)

    states: Dict[int, dict] = {}
    for f in range(n_frames):
        t = f / fps
        decay = math.exp(-k * t)
        v = v0 * decay
        pos = start + heading * ((v0 / k) * (1.0 - decay))
        vel = heading * v
        acc = heading * (-k * v)
        w = w0 * math.exp(-ka * t)
        # orientation integrates the decaying angular velocity
        angle = (w0 / ka) * (1.0 - math.exp(-ka * t))
        quat = (math.cos(angle / 2.0),
                float(math.sin(angle / 2.0) * n[0]),
                float(math.sin(angle / 2.0) * n[1]),
                float(math.sin(angle / 2.0) * n[2]))
        states[f] = {
            "t": t,
            "position": pos.tolist(),
            "quaternion": list(quat),
            "velocity": vel.tolist(),
            "acceleration": acc.tolist(),
            "angular_velocity": (w * n).tolist(),
            "speed": v,
            "angular_speed": abs(w),
            "decay_factor": decay,
            "kinetic_energy": 0.5 * v * v,
        }
    return states


def apply_damped(kb, obj, spec: DampedSpec, n_frames: int, fps: float,
                 origin_offset_local=None):
    """Keyframe ``obj`` along the analytic damped trajectory and return its states."""
    states = damped_states(spec, n_frames, fps)
    keyframe_states(obj, states, origin_offset_local)
    return states


def verify_exponential_decay(states: Dict[int, dict], fps: float,
                             nominal_k: float | None = None) -> dict:
    """Regression-check the generated envelope against ``v0 * exp(-k t)``.

    The trajectory is analytic, so this is a self-consistency guard (it would
    catch a keyframing or unit bug), not a solver validation.
    """
    f_keys = sorted(states, key=int)
    speeds = np.array([states[k]["speed"] for k in f_keys], dtype=float)
    ts = np.array([states[k]["t"] for k in f_keys], dtype=float)
    if speeds.size < 3 or not np.all(speeds > 0):
        return {"fitted_damping": None, "r2": None}
    y = np.log(speeds)
    A = np.vstack([ts, np.ones_like(ts)]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    pred = A @ np.array([slope, intercept])
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    out = {
        "fitted_damping": float(-slope),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else None,
        "initial_speed_fit": float(math.exp(intercept)),
        "speed_first": float(speeds[0]),
        "speed_last": float(speeds[-1]),
        "speed_ratio_last_over_first": float(speeds[-1] / speeds[0]),
    }
    if nominal_k is not None:
        out["nominal_damping"] = float(nominal_k)
        out["abs_error"] = abs(out["fitted_damping"] - float(nominal_k))
        out["rel_error"] = (out["abs_error"] / float(nominal_k)
                            if nominal_k else None)
    return out


# --------------------------------------------------------------------------------------
# Pure rotation
# --------------------------------------------------------------------------------------

@dataclass
class RotationSpec:
    """Parameters for a body spinning in place about a fixed principal axis.

    With ``angular_damping == 0`` the spin is uniform; with a positive value the
    angular velocity decays exponentially, which lets the same scenario family
    also cover "spin-down" dynamics.
    """

    axis: str = "z"
    #: seconds per revolution (primary control when undamped)
    period_s: float = 4.0
    #: angular decay rate in 1/s; 0 keeps the spin uniform
    angular_damping: float = 0.0
    #: body centre (the spin axis passes through it)
    center: Tuple[float, float, float] = (0.0, 0.0, 0.6)
    phase0: float = 0.0
    #: mass and inertia read from the URDF, used for the momentum/energy labels
    mass: float | None = None
    moment_of_inertia: float | None = None

    @property
    def omega0(self) -> float:
        if self.period_s <= 0:
            raise ValueError("period_s must be > 0")
        return 2.0 * math.pi / self.period_s


def rotation_states(spec: RotationSpec, n_frames: int, fps: float) -> Dict[int, dict]:
    """States of a body rotating about a principal axis through its centre.

    Uniform spin::

        theta(t) = omega0 * t

    Decaying spin (``angular_damping = k > 0``)::

        omega(t) = omega0 * exp(-k t)
        theta(t) = (omega0 / k) * (1 - exp(-k t))

    When the URDF supplied mass and inertia, each frame also carries the angular
    momentum ``L = I * omega`` and the rotational energy ``E = 0.5 * I * omega^2``.
    """
    _, _, n = _basis(spec.axis)
    omega0 = spec.omega0
    k = max(spec.angular_damping, 0.0)
    I = spec.moment_of_inertia

    states: Dict[int, dict] = {}
    for f in range(n_frames):
        t = f / fps
        if k > 0:
            omega = omega0 * math.exp(-k * t)
            angle = spec.phase0 + (omega0 / k) * (1.0 - math.exp(-k * t))
            alpha = -k * omega
        else:
            omega = omega0
            angle = spec.phase0 + omega0 * t
            alpha = 0.0

        quat = (math.cos(angle / 2.0),
                float(math.sin(angle / 2.0) * n[0]),
                float(math.sin(angle / 2.0) * n[1]),
                float(math.sin(angle / 2.0) * n[2]))
        ang_vel = (omega * n).tolist()
        ang_acc = (alpha * n).tolist()

        s = {
            "t": t,
            "position": list(spec.center),
            "quaternion": list(quat),
            "velocity": [0.0, 0.0, 0.0],
            "acceleration": [0.0, 0.0, 0.0],
            "angular_velocity": ang_vel,
            "angular_acceleration": ang_acc,
            "angle": angle,
            "angular_speed": abs(omega),
        }
        if I is not None:
            s["moment_of_inertia"] = float(I)
            s["angular_momentum"] = float(I * omega)
            s["rotational_energy"] = float(0.5 * I * omega * omega)
        if spec.mass is not None:
            s["mass"] = float(spec.mass)
        states[f] = s
    return states


def apply_rotation(kb, obj, spec: RotationSpec, n_frames: int, fps: float,
                   origin_offset_local=None):
    """Keyframe ``obj`` spinning in place and return its states."""
    states = rotation_states(spec, n_frames, fps)
    keyframe_states(obj, states, origin_offset_local)
    return states


def verify_rotation(states: Dict[int, dict], fps: float,
                    nominal_omega: float, nominal_k: float = 0.0) -> dict:
    """Check total swept angle and (for spin-down) the angular decay rate."""
    f_keys = sorted(states, key=int)
    angles = np.array([states[k]["angle"] for k in f_keys], dtype=float)
    ws = np.array([states[k]["angular_speed"] for k in f_keys], dtype=float)
    ts = np.array([states[k]["t"] for k in f_keys], dtype=float)

    swept = float(angles[-1] - angles[0])
    expected = nominal_omega * float(ts[-1])
    out = {
        "swept_angle_rad": swept,
        "swept_angle_deg": math.degrees(swept),
        "revolutions": swept / (2.0 * math.pi),
        "nominal_omega": float(nominal_omega),
        "angular_speed_first": float(ws[0]),
        "angular_speed_last": float(ws[-1]),
        "omega_rel_error": (abs(ws[0] - nominal_omega) / nominal_omega
                            if nominal_omega else None),
    }
    if nominal_k > 0:
        y = np.log(np.maximum(ws, 1e-12))
        A = np.vstack([ts, np.ones_like(ts)]).T
        slope, _ = np.linalg.lstsq(A, y, rcond=None)[0]
        out["fitted_angular_damping"] = float(-slope)
        out["nominal_angular_damping"] = float(nominal_k)
        out["damping_rel_error"] = abs(-slope - nominal_k) / nominal_k
    else:
        out["swept_angle_expected_uniform"] = expected
        out["swept_angle_rel_error"] = (abs(swept - expected) / expected
                                        if expected else None)
    return out
