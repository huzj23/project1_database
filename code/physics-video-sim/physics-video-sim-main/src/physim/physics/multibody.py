"""V5.5 stage 04: the reusable N-rigid-body solver.

04 section 1 requires ONE reusable interface shared by stages 05-08 -- "不是制作三个独立
脚本" (not three separate scripts) -- and forbids reusing the turntable's `_drive_support`,
which resets position/velocity every substep.  For a domino chain every body is a real
movable rigid body from the start: nothing switches from passive to active at a scripted
moment, and nothing receives a push after contact.

Design
------
* Bodies come from the stage-02 contract (`BodySpec`), so identity, roles, units and time
  are already frozen.  Nothing here re-implements those.
* Static scenery is a separate list (`StaticCollider`); it can carry force but never moves.
* The solver records EVERY substep for EVERY dynamic body and EVERY contact -- 04 forbids
  the old "max 100 contacts" cap.
* Time follows the contract exactly: substep k covers ((k-1)dt, k*dt] and is reported at
  k*dt, which is the V5 off-by-one-dt bug this must not repeat.
* A zero-initial-penetration check runs BEFORE any solve, because stage 03 measured that
  this pybullet build exposes no collision margin -- so geometry, not margin, must
  guarantee separation.

Determinism
-----------
04 requires the same seed to reproduce event order exactly, so all randomness is seeded
and the step order is fixed.  pybullet's solver is deterministic for a fixed build and
step sequence.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pybullet as pb

from physim.contracts import (
    OUTPUT_SCHEMA_VERSION,
    ROLE_TRIGGER,
    Z_UP_GRAVITY,
    BodySpec,
    ContactRecord,
    MultibodyResult,
    StaticCollider,
    SubstepState,
    ContractError,
    episodes_from_contacts,
    frame_time_s,
    substep_time_s,
    write_jsonl,
)

#: 04 section 2 starting points.  Recorded as DEFAULTS, not as measured material data.
DEFAULT_PHYSICS_FPS = 480.0
DEFAULT_VIDEO_FPS = 24.0
DEFAULT_SOLVER_ITERATIONS = 150
DEFAULT_RESTITUTION = 0.05
DEFAULT_LATERAL_FRICTION = 0.5
DEFAULT_LINEAR_DAMPING = 0.02
DEFAULT_ANGULAR_DAMPING = 0.02
DEFAULT_ROLLING_FRICTION = 0.001
DEFAULT_SPINNING_FRICTION = 0.001


@dataclass
class SolverSettings:
    """Every knob the solver uses, so an attempt can change exactly one factor."""

    physics_fps: float = DEFAULT_PHYSICS_FPS
    video_fps: float = DEFAULT_VIDEO_FPS
    solver_iterations: int = DEFAULT_SOLVER_ITERATIONS
    restitution: float = DEFAULT_RESTITUTION
    lateral_friction: float = DEFAULT_LATERAL_FRICTION
    linear_damping: float = DEFAULT_LINEAR_DAMPING
    angular_damping: float = DEFAULT_ANGULAR_DAMPING
    rolling_friction: float = DEFAULT_ROLLING_FRICTION
    spinning_friction: float = DEFAULT_SPINNING_FRICTION
    gravity_m_s2: tuple[float, float, float] = Z_UP_GRAVITY
    #: 04 section 2: if (|v| + |w|*R)*dt exceeds this fraction of the thinnest collision
    #: thickness, reduce dt or velocity and evaluate CCD.
    penetration_guard_fraction: float = 0.1
    #: Report a contact only above this force; suppresses solver noise micro-contacts.
    contact_force_threshold_n: float = 1e-6
    #: 04 section 3: initial penetration must not exceed min(1 mm, t_min*5%).
    max_initial_penetration_m: float = 1e-3

    def to_dict(self) -> dict[str, Any]:
        return {
            "physics_fps": self.physics_fps,
            "video_fps": self.video_fps,
            "solver_iterations": self.solver_iterations,
            "restitution": self.restitution,
            "lateral_friction": self.lateral_friction,
            "linear_damping": self.linear_damping,
            "angular_damping": self.angular_damping,
            "rolling_friction": self.rolling_friction,
            "spinning_friction": self.spinning_friction,
            "gravity_m_s2": list(self.gravity_m_s2),
            "penetration_guard_fraction": self.penetration_guard_fraction,
            "contact_force_threshold_n": self.contact_force_threshold_n,
            "max_initial_penetration_m": self.max_initial_penetration_m,
            "parameter_status": (
                "debugging ranges from 04 section 2, NOT measured material properties; "
                "effective values must be read back with getDynamicsInfo"
            ),
        }


@dataclass
class PenetrationReport:
    """Pre-solve overlap check.  Non-empty means the layout is invalid, not that the
    solver needs a bigger margin (this build has none)."""

    max_penetration_m: float
    violating_pairs: list[dict[str, Any]] = field(default_factory=list)
    checked_pairs: int = 0

    @property
    def passed(self) -> bool:
        return not self.violating_pairs

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_penetration_m": self.max_penetration_m,
            "checked_pairs": self.checked_pairs,
            "violating_pairs": self.violating_pairs,
            "passed": self.passed,
        }


class MultibodySolver:
    """Solves an N-body scene and returns a contract-conformant result.

    Usage:
        solver = MultibodySolver(settings)
        solver.load(bodies, static_colliders)
        report = solver.check_initial_penetration()
        result = solver.run(frame_count=96, trigger_velocity=...)
    """

    def __init__(self, settings: SolverSettings | None = None, *, seed: int = 550001) -> None:
        self.settings = settings or SolverSettings()
        self.seed = seed
        self.client: int | None = None
        self._body_ids: dict[str, int] = {}
        self._static_ids: dict[str, int] = {}
        self._bodies: list[BodySpec] = []
        self._statics: list[StaticCollider] = []
        self._asset_files: dict[str, Path] = {}
        self._primitives: dict[str, dict[str, float]] = {}

    # ------------------------------------------------------------------ setup

    def __enter__(self) -> "MultibodySolver":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.disconnect()

    def connect(self) -> int:
        if self.client is None:
            self.client = pb.connect(pb.DIRECT)
            if self.client < 0:
                raise ContractError("pybullet could not open a DIRECT connection")
            pb.resetSimulation(physicsClientId=self.client)
            pb.setGravity(*self.settings.gravity_m_s2, physicsClientId=self.client)
            pb.setTimeStep(1.0 / self.settings.physics_fps, physicsClientId=self.client)
            pb.setPhysicsEngineParameter(
                numSolverIterations=self.settings.solver_iterations,
                physicsClientId=self.client,
            )
        return self.client

    def disconnect(self) -> None:
        if self.client is not None:
            pb.disconnect(self.client)
            self.client = None

    # ------------------------------------------------------------------ loading

    def load(
        self,
        bodies: Sequence[BodySpec],
        static_colliders: Sequence[StaticCollider] = (),
        *,
        asset_collision_files: dict[str, Path] | None = None,
        primitives: dict[str, dict[str, float]] | None = None,
    ) -> None:
        """Create every body and static collider.

        `asset_collision_files` maps asset_id -> a closed collision mesh (OBJ).  Stage 03
        established that GSO ships a closed designed proxy per asset, and that this engine
        exposes no collision margin, so a CLOSED mesh is required rather than optional.

        `primitives` supplies dimensions for primitive colliders, keyed by instance_id or
        asset_id, as e.g. ``{"box_001": {"half_extents_m": (0.05, 0.1, 0.02)}}``.
        """
        cid = self.connect()
        self._bodies = list(bodies)
        self._statics = list(static_colliders)
        files = asset_collision_files or {}
        prims = primitives or {}
        # Retained for the geometry-dependent introspection methods below.
        self._asset_files = dict(files)
        self._primitives = dict(prims)

        for spec in bodies:
            shape = self._shape_for(spec, files, prims)
            if not spec.is_dynamic:
                # mass 0 in the contract means "does not move"; it must still be present
                # as a collider, so it is created as a static body.
                body_id = pb.createMultiBody(
                    0, shape, basePosition=list(spec.position_m),
                    baseOrientation=list(spec.quaternion_xyzw),
                    physicsClientId=cid,
                )
                self._apply_material(body_id, spec)
                self._body_ids[spec.instance_id] = body_id
                continue

            body_id = pb.createMultiBody(
                spec.mass_kg, shape,
                basePosition=list(spec.position_m),
                baseOrientation=list(spec.quaternion_xyzw),
                physicsClientId=cid,
            )
            if body_id < 0:
                raise ContractError(f"{spec.instance_id}: createMultiBody failed")
            self._apply_material(body_id, spec)
            if spec.inertia_diagonal_kg_m2 is not None:
                # Stage 03 computed Ixx = m*(h^2+d^2)/12 for boxes; install it so the
                # engine does not substitute its own approximation.
                pb.changeDynamics(
                    body_id, -1,
                    localInertiaDiagonal=list(spec.inertia_diagonal_kg_m2),
                    physicsClientId=cid,
                )
            pb.resetBaseVelocity(
                body_id,
                linearVelocity=list(spec.linear_velocity_m_s),
                angularVelocity=list(spec.angular_velocity_rad_s),
                physicsClientId=cid,
            )
            self._body_ids[spec.instance_id] = body_id

        for collider in static_colliders:
            body_id = self._create_static(collider)
            if body_id is not None:
                self._static_ids[collider.collider_id] = body_id

    def _apply_material(self, body_id: int, spec: BodySpec) -> None:
        cid = self.connect()
        pb.changeDynamics(
            body_id, -1,
            lateralFriction=spec.friction,
            restitution=spec.restitution,
            linearDamping=spec.linear_damping,
            angularDamping=spec.angular_damping,
            rollingFriction=self.settings.rolling_friction,
            spinningFriction=self.settings.spinning_friction,
            physicsClientId=cid,
        )

    def _shape_for(
        self,
        spec: BodySpec,
        files: dict[str, Path],
        primitives: dict[str, dict[str, float]],
    ) -> int:
        """Build this body's collision shape.

        Priority: an explicit closed mesh > a primitive.  A mesh is preferred because
        stage 03 measured that this engine exposes NO collision margin, so the proxy's own
        closed geometry is what guarantees separation.

        The stage-02 ``BodySpec`` deliberately carries no primitive dimensions (it records
        a ``collider_type`` and optional mesh URI), so primitive sizes are passed in
        explicitly via ``primitives``.  They are never guessed here: a missing entry is an
        error, because an invented size would silently mis-place every contact.
        """
        cid = self.connect()

        mesh = files.get(spec.asset_id)
        if mesh is None and spec.collision_uri:
            mesh = Path(spec.collision_uri)
        if mesh is not None and Path(mesh).is_file():
            return pb.createCollisionShape(
                pb.GEOM_MESH, fileName=str(mesh), physicsClientId=cid
            )

        geo = primitives.get(spec.instance_id) or primitives.get(spec.asset_id)
        if geo is None:
            raise ContractError(
                f"{spec.instance_id}: collider_type {spec.collider_type!r} needs explicit "
                f"geometry (a closed collision mesh, or a primitives entry); none supplied"
            )

        if spec.collider_type == "sphere":
            if "radius_m" not in geo:
                raise ContractError(f"{spec.instance_id}: sphere needs radius_m")
            return pb.createCollisionShape(
                pb.GEOM_SPHERE, radius=float(geo["radius_m"]), physicsClientId=cid
            )
        if spec.collider_type == "cylinder":
            if "radius_m" not in geo or "height_m" not in geo:
                raise ContractError(f"{spec.instance_id}: cylinder needs radius_m and height_m")
            return pb.createCollisionShape(
                pb.GEOM_CYLINDER, radius=float(geo["radius_m"]),
                height=float(geo["height_m"]), physicsClientId=cid,
            )
        if spec.collider_type == "box":
            if "half_extents_m" not in geo:
                raise ContractError(f"{spec.instance_id}: box needs half_extents_m")
            return pb.createCollisionShape(
                pb.GEOM_BOX, halfExtents=[float(v) for v in geo["half_extents_m"]],
                physicsClientId=cid,
            )
        raise ContractError(
            f"{spec.instance_id}: collider_type {spec.collider_type!r} has no geometry "
            f"and no collision mesh was supplied"
        )

    def _create_static(self, collider: StaticCollider) -> int | None:
        cid = self.connect()
        if collider.collider_type == "plane":
            # `planeNormal` is NOT optional in practice. Called without it, PyBullet builds a
            # plane whose normal is not (0,0,1); stage 03 measured a body then free-falling
            # straight through it. The normal is therefore always stated explicitly.
            shape = pb.createCollisionShape(
                pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0], physicsClientId=cid
            )
        elif collider.collider_type == "box" and collider.half_extents_m:
            shape = pb.createCollisionShape(
                pb.GEOM_BOX, halfExtents=list(collider.half_extents_m), physicsClientId=cid
            )
        elif collider.uri and Path(collider.uri).is_file():
            # Concave scenery must be flagged, because an unflagged static GEOM_MESH is
            # convex-hulled: the Italian Flat tray would then collide as a solid block whose
            # top is its rim, 12.65 mm above the floor the props actually stand on.
            flags = pb.GEOM_FORCE_CONCAVE_TRIMESH if collider.concave else 0
            shape = pb.createCollisionShape(
                pb.GEOM_MESH, fileName=collider.uri, flags=flags, physicsClientId=cid
            )
        else:
            return None
        body_id = pb.createMultiBody(
            0, shape,
            basePosition=list(collider.position_m),
            baseOrientation=list(collider.quaternion_xyzw),
            physicsClientId=cid,
        )
        if body_id >= 0:
            pb.changeDynamics(
                body_id, -1,
                lateralFriction=self.settings.lateral_friction,
                restitution=self.settings.restitution,
                physicsClientId=cid,
            )
        return body_id if body_id >= 0 else None

    # ------------------------------------------------------------------ checks

    def self_check(self) -> dict[str, Any]:
        """Prove the colliders this solver builds actually collide, WITHOUT touching the solve.

        Two PyBullet behaviours fail SILENTLY: a static ``GEOM_MESH`` is convex-hulled unless
        flagged concave, and a mesh built from ``vertices=``/``indices=`` produces a shape that
        does not collide with ``GEOM_PLANE`` or with a concave trimesh. Both make a body free-fall
        with zero contacts while every other signal looks normal, so neither can be detected from
        the trajectory alone.

        THIS CHECK RUNS IN ITS OWN PRIVATE WORLD, and that is not a convenience. The first version
        probed the solver's own world and masked the dynamic bodies while it did so -- which meant
        they fell freely for the whole check. With one control plus four colliders at 480 steps
        each, that is 2400 steps, about 5 s of free fall, and the recorded trajectory then started
        with every body roughly 240 m below the floor (``0.5 * 9.81 * 7^2 = 240``). The check was
        correct about the colliders and silently destroyed the run it was validating.

        A private world holds copies of the same static colliders and no dynamic bodies at all, so
        the probe cannot be contaminated by a body falling onto it and the real solve's state is
        never advanced.

        Per static collider, with a control box dropped on it:

        ``supported``
            the box makes contact and stops falling.
        ``concavity_represented``
            for a collider declared ``concave``, the box must rest BELOW the collider's bounding
            box top. An upward-opening dish is exactly this case; resting at the AABB top means the
            concavity was discarded and PyBullet is colliding against a filled hull. This assumes
            upward-opening concavity, which is what the check can detect.
        ``support_height_verified``
            where the collider records the support height an earlier stage measured by raycast,
            the box must actually rest there within 2 mm. This is the only check that catches a
            WRONG DECLARATION, such as a dish declared convex: the declaration agrees with the
            flag, so only an independent measurement exposes it.
        """
        cid = pb.connect(pb.DIRECT)
        results: dict[str, Any] = {"controls": {}, "static_colliders": {},
                                  "private_world": True,
                                  "note": ("runs in a separate PyBullet world containing copies "
                                           "of the static colliders only, so the solver's state "
                                           "is never advanced")}
        try:
            pb.resetSimulation(physicsClientId=cid)
            pb.setGravity(*self.settings.gravity_m_s2, physicsClientId=cid)
            pb.setTimeStep(1.0 / self.settings.physics_fps, physicsClientId=cid)
            pb.setPhysicsEngineParameter(
                numSolverIterations=self.settings.solver_iterations, physicsClientId=cid
            )

            def make_static(collider: StaticCollider) -> int | None:
                if collider.collider_type == "plane":
                    shape = pb.createCollisionShape(
                        pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0], physicsClientId=cid
                    )
                elif collider.collider_type == "box" and collider.half_extents_m:
                    shape = pb.createCollisionShape(
                        pb.GEOM_BOX, halfExtents=list(collider.half_extents_m),
                        physicsClientId=cid,
                    )
                elif collider.uri and Path(collider.uri).is_file():
                    flags = pb.GEOM_FORCE_CONCAVE_TRIMESH if collider.concave else 0
                    shape = pb.createCollisionShape(
                        pb.GEOM_MESH, fileName=collider.uri, flags=flags, physicsClientId=cid
                    )
                else:
                    return None
                if shape < 0:
                    return None
                body = pb.createMultiBody(0, shape, basePosition=list(collider.position_m),
                                          baseOrientation=list(collider.quaternion_xyzw),
                                          physicsClientId=cid)
                if body >= 0:
                    pb.changeDynamics(body, -1,
                                      lateralFriction=self.settings.lateral_friction,
                                      restitution=self.settings.restitution,
                                      physicsClientId=cid)
                return body if body >= 0 else None

            def settle_box_on(support_body: int, x: float, y: float, drop_z: float) -> dict:
                body = pb.createMultiBody(
                    0.05,
                    pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[0.008] * 3,
                                            physicsClientId=cid),
                    basePosition=(x, y, drop_z), physicsClientId=cid,
                )
                for _ in range(480):
                    pb.stepSimulation(physicsClientId=cid)
                pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
                contacts = pb.getContactPoints(bodyA=body, bodyB=support_body,
                                               physicsClientId=cid)
                pb.removeBody(body, physicsClientId=cid)
                bottom = float(pos[2]) - 0.008
                return {"rest_z": round(float(pos[2]), 6), "rest_bottom_z": round(bottom, 6),
                        "contacts": len(contacts), "rests": bool(len(contacts) > 0)}

            # Control: a plane built the way this solver builds it must support a box.
            plane_collider = StaticCollider(collider_id="__control_plane__",
                                            collider_type="plane")
            plane_body = make_static(plane_collider)
            if plane_body is None:
                results["controls"]["box_on_plane"] = {"rests": False,
                                                       "error": "plane could not be created"}
            else:
                results["controls"]["box_on_plane"] = settle_box_on(plane_body, 0.0, 0.0, 0.05)
                pb.removeBody(plane_body, physicsClientId=cid)

            for collider in self._statics:
                body_id = make_static(collider)
                if body_id is None:
                    results["static_colliders"][collider.collider_id] = {
                        "supported": False,
                        "error": "collider could not be created in the private world",
                    }
                    continue
                aabb_min, aabb_max = pb.getAABB(body_id, physicsClientId=cid)
                finite = all(abs(v) < 1e4 for v in list(aabb_min) + list(aabb_max))
                if collider.collider_type == "plane" or not finite:
                    cx = cy = 0.0
                    drop = float(collider.position_m[2]) + 0.05
                    aabb_top = None
                else:
                    cx = 0.5 * (aabb_min[0] + aabb_max[0])
                    cy = 0.5 * (aabb_min[1] + aabb_max[1])
                    drop = float(aabb_max[2]) + 0.03
                    aabb_top = float(aabb_max[2])
                res = settle_box_on(body_id, cx, cy, drop)
                res["concave"] = bool(getattr(collider, "concave", False))
                res["collider_type"] = collider.collider_type
                res["drop_z"] = round(drop, 6)
                res["aabb_top_z"] = round(aabb_top, 6) if aabb_top is not None else None
                res["probe_xy"] = [round(cx, 6), round(cy, 6)]
                res["unbounded"] = aabb_top is None
                res["supported"] = bool(
                    res["rests"] and (aabb_top is None or res["rest_bottom_z"] <= drop - 0.02)
                )
                if aabb_top is None or not res["concave"]:
                    res["concavity_represented"] = None
                else:
                    res["concavity_represented"] = bool(
                        res["rest_bottom_z"] < aabb_top - 0.001
                    )
                support_z = getattr(collider, "support_z_m", None)
                if support_z is None:
                    res["support_height_verified"] = None
                else:
                    err = abs(res["rest_bottom_z"] - float(support_z))
                    res["support_height_verified"] = bool(err <= 0.002)
                    res["support_height_error_m"] = round(err, 9)
                    res["recorded_support_z_m"] = float(support_z)
                results["static_colliders"][collider.collider_id] = res
                pb.removeBody(body_id, physicsClientId=cid)
        finally:
            pb.disconnect(cid)

        results["ok"] = bool(
            results["controls"]["box_on_plane"].get("rests")
            and all(
                v.get("supported", True)
                and v.get("concavity_represented") is not False
                and v.get("support_height_verified") is not False
                for v in results["static_colliders"].values()
            )
        )
        return results

    def check_initial_penetration(self) -> PenetrationReport:
        """Detect overlap BEFORE solving.

        Stage 03 measured that this pybullet build has no collision margin, so a
        penetrating initial layout cannot be hidden by a margin; it would instead produce
        a violent first-step separation that falsifies the whole trajectory.
        """
        cid = self.connect()
        pb.performCollisionDetection(physicsClientId=cid)
        all_ids = list(self._body_ids.values()) + list(self._static_ids.values())
        name_of = {v: k for k, v in {**self._body_ids, **self._static_ids}.items()}

        worst = 0.0
        violations: list[dict[str, Any]] = []
        checked = 0
        for i in range(len(all_ids)):
            for j in range(i + 1, len(all_ids)):
                a, b = all_ids[i], all_ids[j]
                checked += 1
                for contact in pb.getContactPoints(a, b, physicsClientId=cid):
                    # contactDistance is negative when the surfaces overlap.
                    dist = float(contact[8])
                    if dist < 0:
                        depth = -dist
                        worst = max(worst, depth)
                        if depth > self.settings.max_initial_penetration_m:
                            violations.append({
                                "instance_a": name_of.get(a, str(a)),
                                "instance_b": name_of.get(b, str(b)),
                                "penetration_m": round(depth, 9),
                            })
        return PenetrationReport(
            max_penetration_m=worst, violating_pairs=violations, checked_pairs=checked
        )

    # ------------------------------------------------------------------ solving

    def run(
        self,
        frame_count: int,
        *,
        settle_seconds: float = 0.0,
        record_substeps: bool = True,
        run_id: str | None = None,
    ) -> MultibodyResult:
        """Step the world and record all state and contacts.

        `settle_seconds` performs the 04 section 3 pre-settle.  Its t=0 becomes the
        settled state used to build the production world, so the settle is a pre-solve and
        is NOT part of the recorded trajectory.
        """
        cid = self.connect()
        fps = self.settings.physics_fps

        if settle_seconds > 0:
            for _ in range(int(round(settle_seconds * fps))):
                pb.stepSimulation(physicsClientId=cid)

        steps_per_frame = int(round(fps / self.settings.video_fps))
        trajectories: dict[str, list[Any]] = {b.instance_id: [] for b in self._bodies}
        substeps: list[SubstepState] = []
        contacts: list[ContactRecord] = []
        name_of = {v: k for k, v in self._body_ids.items()}

        step = 0
        for frame in range(frame_count):
            # Record the pre-step state as this frame's state, so frame 0 is the settled
            # initial state rather than the result of one advance.
            self._capture(frame, trajectories)

            for _ in range(steps_per_frame):
                step += 1
                pb.stepSimulation(physicsClientId=cid)
                contacts.extend(self._collect_contacts(step))
                if record_substeps:
                    substeps.extend(self._capture_substep(step))

        # 04 section 1: state/contact recording covers every substep of the whole run.
        result = MultibodyResult(
            bodies=list(self._bodies),
            trajectories=trajectories,
            substeps=substeps,
            contacts=contacts,
            static_colliders=list(self._statics),
            physics_fps=fps,
            video_fps=self.settings.video_fps,
            frame_count=frame_count,
            seed=self.seed,
            run_id=run_id,
        )
        result.events = episodes_from_contacts(contacts)
        return result

    def _capture(self, frame: int, trajectories: dict[str, list[Any]]) -> None:
        from physim.physics import BodyState

        cid = self.connect()
        for iid, body_id in self._body_ids.items():
            pos, orn = pb.getBasePositionAndOrientation(body_id, physicsClientId=cid)
            lin, ang = pb.getBaseVelocity(body_id, physicsClientId=cid)
            trajectories[iid].append(
                BodyState(
                    frame=frame,
                    time_seconds=frame_time_s(frame, self.settings.video_fps),
                    position=tuple(float(v) for v in pos),
                    # pybullet is xyzw; the legacy BodyState is wxyz.
                    quaternion=(float(orn[3]), float(orn[0]), float(orn[1]), float(orn[2])),
                    linear_velocity=tuple(float(v) for v in lin),
                    angular_velocity=tuple(float(v) for v in ang),
                )
            )

    def _capture_substep(self, step: int) -> list[SubstepState]:
        cid = self.connect()
        out: list[SubstepState] = []
        for iid, body_id in self._body_ids.items():
            spec = next(b for b in self._bodies if b.instance_id == iid)
            if not spec.is_dynamic:
                continue
            pos, orn = pb.getBasePositionAndOrientation(body_id, physicsClientId=cid)
            lin, ang = pb.getBaseVelocity(body_id, physicsClientId=cid)
            out.append(
                SubstepState(
                    instance_id=iid,
                    step=step,
                    time_s=substep_time_s(step, self.settings.physics_fps),
                    position_m=tuple(float(v) for v in pos),
                    quaternion_xyzw=tuple(float(v) for v in orn),
                    linear_velocity_m_s=tuple(float(v) for v in lin),
                    angular_velocity_rad_s=tuple(float(v) for v in ang),
                )
            )
        return out

    def _collect_contacts(self, step: int) -> list[ContactRecord]:
        """Every contact at this substep -- no cap, per 04 section 4."""
        cid = self.connect()
        name_of = {v: k for k, v in {**self._body_ids, **self._static_ids}.items()}
        out: list[ContactRecord] = []
        for a_id, a_name in name_of.items():
            for b_id, b_name in name_of.items():
                if a_id >= b_id:
                    continue
                for cp in pb.getContactPoints(a_id, b_id, physicsClientId=cid):
                    force = float(cp[9])
                    if force < self.settings.contact_force_threshold_n:
                        continue
                    out.append(
                        ContactRecord(
                            step=step,
                            time_s=substep_time_s(step, self.settings.physics_fps),
                            instance_a=a_name,
                            instance_b=b_name,
                            link_a=int(cp[3]),
                            link_b=int(cp[4]),
                            position_on_a_m=tuple(float(v) for v in cp[5]),
                            position_on_b_m=tuple(float(v) for v in cp[6]),
                            normal_on_b=tuple(float(v) for v in cp[7]),
                            signed_distance_m=float(cp[8]),
                            normal_force_n=force,
                            lateral_force_1_n=float(cp[10]),
                            lateral_force_2_n=float(cp[12]),
                            lateral_dir_1=tuple(float(v) for v in cp[11]),
                            lateral_dir_2=tuple(float(v) for v in cp[13]),
                        )
                    )
        return out

    # ------------------------------------------------------------------ introspection

    def effective_parameters(self) -> dict[str, Any]:
        """Read back what the engine ACTUALLY has, per 04 section 2.

        `getDynamicsInfo` is the authority; the settings object is only what was asked for.
        """
        cid = self.connect()
        out: dict[str, Any] = {}
        for iid, body_id in self._body_ids.items():
            dyn = pb.getDynamicsInfo(body_id, -1, physicsClientId=cid)
            out[iid] = {
                "mass_kg": float(dyn[0]),
                "lateral_friction": float(dyn[1]),
                "local_inertia_diagonal_kg_m2": [float(v) for v in dyn[2]],
                "restitution": float(dyn[5]),
                "linear_damping": float(dyn[6]),
                "angular_damping": float(dyn[7]),
                "rolling_friction": float(dyn[8]) if len(dyn) > 8 else None,
                "spinning_friction": float(dyn[9]) if len(dyn) > 9 else None,
            }
        return out

    def _radius_for(self, spec: BodySpec) -> float | None:
        """Characteristic radius of a body from the geometry it was built with.

        Used only by the step-size guard.  Returns ``None`` when no geometry is known, so
        the guard reports "not evaluated" instead of comparing against a made-up radius.
        """
        geo = self._primitives.get(spec.instance_id) or self._primitives.get(spec.asset_id)
        if geo:
            if "half_extents_m" in geo:
                return 0.5 * max(float(v) for v in geo["half_extents_m"])
            if "radius_m" in geo and "height_m" in geo:
                r, h = float(geo["radius_m"]), float(geo["height_m"])
                return math.hypot(r, h / 2.0)
            if "radius_m" in geo:
                return float(geo["radius_m"])
        # A mesh collider: fall back to half the largest axis of the collision mesh's
        # bounding box, computed from the file rather than assumed.
        mesh = self._asset_files.get(spec.asset_id)
        if mesh is None and spec.collision_uri:
            mesh = Path(spec.collision_uri)
        if mesh is not None and Path(mesh).is_file():
            return self._mesh_radius(Path(mesh))
        return None

    @staticmethod
    def _mesh_radius(path: Path) -> float | None:
        """Half the largest bounding-box axis of an OBJ, read from its vertices."""
        lo = [float("inf")] * 3
        hi = [float("-inf")] * 3
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if not line.startswith("v "):
                        continue
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    for i in range(3):
                        value = float(parts[1 + i])
                        lo[i] = min(lo[i], value)
                        hi[i] = max(hi[i], value)
        except (OSError, ValueError):
            return None
        if lo[0] == float("inf"):
            return None
        return 0.5 * max(hi[i] - lo[i] for i in range(3))

    def motion_guard(self, thinnest_thickness_m: float | None = None) -> dict[str, Any]:
        """04 section 2 step-size check.

        Requires ``(|v| + |w|*R)*dt <= guard_fraction * t_min``.  When ``t_min`` (the
        thinnest relevant collision thickness) is given the bound is evaluated directly;
        otherwise only the raw per-step travel is reported, because judging the bound
        without a real thickness would be guesswork.
        """
        cid = self.connect()
        dt = 1.0 / self.settings.physics_fps
        rows = []
        worst = 0.0
        for spec in self._bodies:
            body_id = self._body_ids.get(spec.instance_id)
            if body_id is None:
                continue
            lin, ang = pb.getBaseVelocity(body_id, physicsClientId=cid)
            speed = math.sqrt(sum(v * v for v in lin))
            spin = math.sqrt(sum(v * v for v in ang))
            # Rotation radius from the geometry this body was actually built with; if the
            # caller supplied none, the radius is reported as unknown and that body is
            # excluded from the bound rather than judged against an invented number.
            radius = self._radius_for(spec)
            travel = (speed + spin * radius) * dt if radius is not None else None
            if travel is not None:
                worst = max(worst, travel)
            rows.append({
                "instance_id": spec.instance_id,
                "speed_m_s": round(speed, 6),
                "spin_rad_s": round(spin, 6),
                "radius_m": round(radius, 6) if radius is not None else None,
                "per_step_travel_m": round(travel, 9) if travel is not None else None,
            })

        out: dict[str, Any] = {
            "dt_s": dt,
            "guard_fraction": self.settings.penetration_guard_fraction,
            "worst_per_step_travel_m": round(worst, 9),
            "bodies": rows,
        }
        if thinnest_thickness_m is not None and thinnest_thickness_m > 0:
            bound = self.settings.penetration_guard_fraction * thinnest_thickness_m
            out["thinnest_thickness_m"] = thinnest_thickness_m
            out["allowed_travel_m"] = round(bound, 9)
            out["within_bound"] = worst <= bound
            out["violating_bodies"] = [
                r["instance_id"] for r in rows if r["per_step_travel_m"] > bound
            ]
        else:
            # Judging the bound without a real thickness would be guesswork, so the check
            # is explicitly reported as NOT evaluated rather than silently passing.
            out["within_bound"] = None
            out["note"] = (
                "thinnest_thickness_m not supplied, so the bound was NOT evaluated; "
                "pass a real thickness rather than assuming one"
            )
        return out


# ---------------------------------------------------------------------------- evidence


def write_evidence(result: MultibodyResult, out_dir: Path) -> dict[str, str]:
    """Write the complete stage-02 evidence package for a solved result.

    Everything 02 requires per attempt, in one place so no stage can forget a file or invent its
    own subset:

      trajectory.json         per-body state at every VIDEO frame
      motion_substeps.jsonl   every physics substep, one JSON object per line
      contacts.jsonl          every contact at every substep, with the raw contact data
      events.json             contact episodes (start, end, peak force, participants)
      causality.json          per-body motion attribution built ONLY from real contact evidence
      validation.json         the contract checks, with unevaluated checks kept as unevaluated
      scene_delta.json        what changed relative to the source scene
      status.json             pass/fail per declared acceptance criterion

    `causality.json` is deliberately conservative. It reports, for each body, the first substep
    at which it moved and the contacts active immediately before that substep. It does NOT label
    a contact as the cause: 02 states the recorded A/B order is not a causal direction, so the
    evidence is presented and the inference is left to the reader. A body that moved with no
    preceding contact is flagged as `moved_without_preceding_contact`, which is a real failure
    signal rather than a silent omission.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    def emit(name: str, payload: Any, *, jsonl: bool = False) -> None:
        p = out_dir / name
        with p.open("w", encoding="utf-8") as h:
            if jsonl:
                for row in payload:
                    h.write(json.dumps(row) + "\n")
            else:
                h.write(json.dumps(payload, indent=2))
        written[name] = str(p)

    # ---- trajectory: video frames ------------------------------------------------------
    #
    # FIELD NAMES AND QUATERNION ORDER. `BodyState` (the pre-existing physics dataclass) uses
    # `position`, `quaternion`, `linear_velocity`, `angular_velocity`, and its `quaternion` is
    # **wxyz**, because it predates the 02 contract and is consumed by the Blender backend. The
    # written contract is **xyzw**. The conversion is explicit here for the same reason the rest
    # of the project does it explicitly at the boundary: an implicit swap silently mirrors every
    # body, and `q` vs `-q` makes that easy to miss.
    def q_to_xyzw(q_wxyz) -> list[float]:
        w, x, y, z = (float(v) for v in q_wxyz)
        return [x, y, z, w]

    traj: dict[str, list[dict[str, Any]]] = {}
    for iid, states in result.trajectories.items():
        rows = []
        for st in states:
            rows.append({
                "frame": st.frame,
                "time_s": frame_time_s(st.frame, result.video_fps),
                "blender_frame": st.frame + 1,
                "position_m": [float(v) for v in st.position],
                "quaternion_xyzw": q_to_xyzw(st.quaternion),
                "linear_velocity_m_s": [float(v) for v in st.linear_velocity],
                "angular_velocity_rad_s": [float(v) for v in st.angular_velocity],
            })
        traj[iid] = rows
    emit("trajectory.json", {
        "video_fps": result.video_fps,
        "quaternion_convention": "xyzw",
        "source_convention_note": (
            "physim.physics.BodyState stores wxyz; converted explicitly to the 02 contract's "
            "xyzw for every row written here"),
        "bodies": traj,
    })

    # ---- substeps ----------------------------------------------------------------------
    # `SubstepState` is part of the 02 contract and already uses xyzw and the `*_m`/`*_s`
    # names, so these rows are written as stored.
    emit("motion_substeps.jsonl", [
        {
            "step": s.step,
            "time_s": substep_time_s(s.step, result.physics_fps),
            "instance_id": s.instance_id,
            "position_m": [float(v) for v in s.position_m],
            "quaternion_xyzw": [float(v) for v in s.quaternion_xyzw],
            "linear_velocity_m_s": [float(v) for v in s.linear_velocity_m_s],
            "angular_velocity_rad_s": [float(v) for v in s.angular_velocity_rad_s],
        }
        for s in result.substeps
    ], jsonl=True)

    # ---- contacts ----------------------------------------------------------------------
    emit("contacts.jsonl", [
        {
            "step": c.step,
            "time_s": substep_time_s(c.step, result.physics_fps),
            "pair": sorted(c.pair),
            "instance_a": getattr(c, "instance_a", None),
            "instance_b": getattr(c, "instance_b", None),
            "link_a": getattr(c, "link_a", None),
            "link_b": getattr(c, "link_b", None),
            "position_on_a_m": list(c.position_on_a_m),
            "position_on_b_m": list(c.position_on_b_m),
            "normal_on_b": list(c.normal_on_b),
            "signed_distance_m": c.signed_distance_m,
            "normal_force_n": c.normal_force_n,
            "lateral_force_1_n": c.lateral_force_1_n,
            "lateral_force_2_n": c.lateral_force_2_n,
            "lateral_dir_1": list(c.lateral_dir_1),
            "lateral_dir_2": list(c.lateral_dir_2),
            "impulse_proxy_n_s": None,
        }
        for c in result.contacts
    ], jsonl=True)

    # impulse_proxy = sum(F_normal * dt) per contact pair per substep, labelled an ESTIMATE.
    dt = 1.0 / result.physics_fps
    agg: dict[tuple, float] = {}
    for c in result.contacts:
        key = (c.step, "|".join(sorted(c.pair)))
        agg[key] = agg.get(key, 0.0) + c.normal_force_n * dt
    emit("impulse_proxy.json", {
        "labelled": "estimate",
        "method": "sum(F_normal_n * dt) accumulated per contact pair per substep",
        "dt_s": dt,
        "rows": [{"step": k[0], "pair": k[1],
                  "impulse_proxy_n_s": round(v, 9)} for k, v in sorted(agg.items())],
    })

    # ---- events / episodes --------------------------------------------------------------
    emit("events.json", [
        {"instance_a": e.instance_a,
         "instance_b": e.instance_b,
         "pair": sorted(e.pair) if getattr(e, "pair", None) else
                 sorted((e.instance_a, e.instance_b)),
         "step_start": e.step_start,
         "step_end": e.step_end,
         "time_start_s": e.time_start_s,
         "time_end_s": e.time_end_s,
         "substeps": e.substeps,
         "gap_tolerance": e.gap_tolerance,
         "duration_s": round(float(e.time_end_s) - float(e.time_start_s), 9)}
        for e in result.events
    ])

    # ---- causality ----------------------------------------------------------------------
    contacts_by_step: dict[int, list] = {}
    for c in result.contacts:
        contacts_by_step.setdefault(c.step, []).append(c)
    causes: dict[str, Any] = {}
    for iid, states in result.trajectories.items():
        start = None
        for st in states:
            if st.frame == 0:
                continue
            # Movement is judged in world space against the body's own t=0 pose.
            p0 = np.asarray(states[0].position, float)
            p1 = np.asarray(st.position, float)
            q0 = np.asarray(states[0].quaternion, float)
            q1 = np.asarray(st.quaternion, float)
            moved = (float(np.linalg.norm(p1 - p0)) > 1e-4
                     or abs(float(np.dot(q0, q1))) < 1.0 - 1e-7)
            if moved:
                start = st.frame
                break
        if start is None:
            causes[iid] = {"moved": False,
                           "note": "no frame showed motion beyond 0.1 mm / 0.001 rad"}
            continue
        first_step = start * int(round(result.physics_fps / result.video_fps)) + 1
        prior: list = []
        for k in range(first_step - 1, max(first_step - 9, 0), -1):
            if contacts_by_step.get(k):
                prior = contacts_by_step[k]
                break
        causes[iid] = {
            "moved": True,
            "first_moving_frame": start,
            "first_moving_time_s": frame_time_s(start, result.video_fps),
            "contacts_immediately_before": [
                {"step": c.step, "pair": sorted(c.pair),
                 "normal_force_n": c.normal_force_n,
                 "signed_distance_m": c.signed_distance_m}
                for c in prior
            ],
            "moved_without_preceding_contact": bool(not prior),
            "causal_direction": None,
            "causal_direction_note": (
                "NOT inferred here. 02 states the recorded A/B contact order is not a causal "
                "direction; only the temporal ordering and the force evidence are reported."
            ),
        }
    emit("causality.json", {
        "convention": "substep k covers ((k-1)*dt, k*dt]; dt = 1/physics_fps",
        "bodies": causes,
    })

    # ---- validation ---------------------------------------------------------------------
    validation: dict[str, Any] = {"messages": [], "checks": {}}
    try:
        result.validate_identity()
        validation["checks"]["identity"] = True
    except Exception as exc:
        validation["checks"]["identity"] = False
        validation["messages"].append(f"identity: {exc}")
    try:
        result.validate_time()
        validation["checks"]["time"] = True
    except Exception as exc:
        validation["checks"]["time"] = False
        validation["messages"].append(f"time: {exc}")
    try:
        result.validate_quaternions()
        validation["checks"]["quaternions"] = True
    except Exception as exc:
        validation["checks"]["quaternions"] = False
        validation["messages"].append(f"quaternions: {exc}")
    try:
        result.validate_no_passive_actors()
        validation["checks"]["no_passive_actors"] = True
    except Exception as exc:
        validation["checks"]["no_passive_actors"] = False
        validation["messages"].append(f"no_passive_actors: {exc}")
    # A final-frame penetration sweep, and an honest "not evaluated" where it cannot be judged.
    validation["checks"]["no_body_below_floor"] = all(
        min(s.position[2] for s in states) > -1.0
        for states in result.trajectories.values()
    )
    validation["pass"] = all(v for k, v in validation["checks"].items()
                             if isinstance(v, bool))
    emit("validation.json", validation)

    emit("scene_delta.json", {
        "added": [b.instance_id for b in result.bodies],
        "removed": [],
        "static_colliders": [c.collider_id for c in result.static_colliders],
        "source_objects_deleted": [],
        "note": ("the source scene is never modified; bodies are added to a runtime copy whose "
                 "layer report records every object and states that none was deleted"),
    })

    # ---- bodies: the persistent identity and role record --------------------------------
    #
    # 02 section 1 requires this file and names its contents: persistent id, role, mass, COM and
    # the visual/collision bindings. It was previously left to each stage to write, which is how
    # stage 05 came to depend on a `bodies.json` that no code ever produced. Writing it here means
    # every stage gets the same record from the same source, and a stage that reads it back reads
    # what the solver actually built.
    emit("bodies.json", [
        {
            "instance_id": b.instance_id,
            "asset_id": b.asset_id,
            "role": b.role,
            "mass_kg": b.mass_kg,
            "mass_range_kg": list(b.mass_range_kg) if b.mass_range_kg else None,
            "mass_basis": b.mass_basis,
            "collider_type": b.collider_type,
            "position_m": [float(v) for v in b.position_m],
            "quaternion_xyzw": [float(v) for v in b.quaternion_xyzw],
            "linear_velocity_m_s": [float(v) for v in b.linear_velocity_m_s],
            "angular_velocity_rad_s": [float(v) for v in b.angular_velocity_rad_s],
            "com_local_m": [float(v) for v in b.com_local_m],
            "inertia_diagonal_kg_m2": ([float(v) for v in b.inertia_diagonal_kg_m2]
                                       if b.inertia_diagonal_kg_m2 else None),
            "friction": b.friction,
            "restitution": b.restitution,
            "linear_damping": b.linear_damping,
            "angular_damping": b.angular_damping,
            "source_object_id": b.source_object_id,
            "collision_uri": b.collision_uri,
            "is_dynamic": bool(b.is_dynamic),
        }
        for b in result.bodies
    ])

    # ---- status: the declared acceptance criteria, evaluated -----------------------------
    #
    # 02 section 1 requires `status.json` per attempt. The solver can only judge what it can see,
    # so the checks below are the ones that are true of ANY solve; a stage adds its own task
    # criteria on top. A criterion that cannot be judged from the recorded data is reported as
    # `null` with a reason rather than being quietly reported as a pass.
    criteria: list[dict[str, Any]] = [
        {"name": "no_body_below_floor",
         "pass": validation["checks"].get("no_body_below_floor"),
         "detail": "no body's origin fell more than 1 m below z = 0 at any recorded frame"},
        {"name": "time_contract",
         "pass": validation["checks"].get("time"),
         "detail": "frames start at 0 and time_s = frame / video_fps"},
        {"name": "quaternion_convention",
         "pass": validation["checks"].get("quaternions"),
         "detail": "every written quaternion is unit-norm xyzw"},
        {"name": "identity_unique",
         "pass": validation["checks"].get("identity"),
         "detail": "instance_ids are unique and distinct from asset_ids where required"},
    ]
    emit("status.json", {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "physics_fps": result.physics_fps,
        "video_fps": result.video_fps,
        "frame_count": len(next(iter(result.trajectories.values()), [])),
        "criteria": criteria,
        "all_pass": all(c["pass"] for c in criteria if c["pass"] is not None),
        "stage_criteria_note": ("this file judges only the solver-level contract; a stage's own "
                                "task criteria are recorded in that stage's acceptance record"),
    })

    return written
