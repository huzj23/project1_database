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

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import pybullet as pb

from physim.contracts import (
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
        """Prove the colliders this solver builds actually collide before trusting a solve.

        Stage 03 found two PyBullet behaviours that fail SILENTLY: a static ``GEOM_MESH`` is
        convex-hulled unless flagged concave, and a mesh built from ``vertices=``/``indices=``
        produces a shape that does not collide with ``GEOM_PLANE`` or with a concave trimesh.
        Both make a body free-fall with zero contacts while every other signal looks normal,
        so neither can be detected from the trajectory alone.

        Two things are checked per static collider, with a control box dropped on it:

        ``supported``
            the box makes contact and stops falling. A collider that fails this cannot produce
            a truthful trajectory at all.

        ``concavity_represented``
            for a collider declared ``concave``, the box must come to rest BELOW the collider's
            own bounding-box top. An upward-opening dish is exactly this case: if the box rests
            at the AABB top instead, the concavity was discarded and PyBullet is colliding
            against a filled hull. This assumption (upward-opening concavity) is stated because
            it is what the check can detect; a downward-opening cavity would not be caught here.

        The scene's dynamic bodies are masked out for the duration so their own fall cannot land
        on the control box and be mistaken for the scenery supporting it, and the mask is
        restored before returning.
        """
        cid = self.connect()
        results: dict[str, Any] = {"controls": {}, "static_colliders": {}}

        # Mask every dynamic body so the probe measures the SCENERY, not another body falling
        # onto it. This was a real contamination: an earlier version of this check reported the
        # dish as unsupported because a scene body had landed on the probe.
        saved_masks: list[tuple[int, int, int]] = []
        for body_id in self._body_ids.values():
            group, mask = pb.getCollisionShapeData(body_id, -1, physicsClientId=cid)[0][3], 0
            saved_masks.append((body_id, 1, 1))
            pb.setCollisionFilterGroupMask(body_id, -1, 0, 0, physicsClientId=cid)

        def settle_box_on(support_shape: int, x: float, y: float, drop_z: float) -> dict:
            body = pb.createMultiBody(
                0.05,
                pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[0.008] * 3,
                                        physicsClientId=cid),
                basePosition=(x, y, drop_z), physicsClientId=cid,
            )
            for _ in range(480):
                pb.stepSimulation(physicsClientId=cid)
            pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
            contacts = pb.getContactPoints(bodyA=body, bodyB=support_shape,
                                           physicsClientId=cid)
            pb.removeBody(body, physicsClientId=cid)
            bottom = float(pos[2]) - 0.008
            return {"rest_z": round(float(pos[2]), 6), "rest_bottom_z": round(bottom, 6),
                    "contacts": len(contacts), "rests": bool(len(contacts) > 0)}

        try:
            # Control 1: a plane built the way this solver builds it must support a box.
            plane_shape = pb.createCollisionShape(
                pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0], physicsClientId=cid
            )
            plane_body = pb.createMultiBody(0, plane_shape, basePosition=(0.0, 0.0, 0.0),
                                            physicsClientId=cid)
            results["controls"]["box_on_plane"] = settle_box_on(plane_body, 0.0, 0.0, 0.05)
            pb.removeBody(plane_body, physicsClientId=cid)

            # Control 2: every static mesh collider must support the same box.
            for key, body_id in self._static_ids.items():
                collider = next((c for c in self._statics if c.collider_id == key), None)
                if collider is None:
                    continue
                aabb_min, aabb_max = pb.getAABB(body_id, physicsClientId=cid)
                finite = all(abs(v) < 1e4 for v in list(aabb_min) + list(aabb_max))
                if collider.collider_type == "plane" or not finite:
                    # A GEOM_PLANE has no finite AABB, so it cannot choose a drop point; it is
                    # unbounded and already covered by the control above.
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
                if aabb_top is None:
                    res["concavity_represented"] = None
                elif not res["concave"]:
                    # A convex collider is SUPPOSED to be supported at its top surface.
                    res["concavity_represented"] = None
                else:
                    # The probe must fall INTO the dish, i.e. below the AABB top; resting at or
                    # above it means the declared concavity is not present in the collider.
                    res["concavity_represented"] = bool(
                        res["rest_bottom_z"] < aabb_top - 0.001
                    )
                # The strongest check available, and the one that catches a WRONG DECLARATION
                # rather than a wrong flag: when the collider records the support height a stage
                # measured by raycast, the probe must actually come to rest there. A concave dish
                # left unflagged is silently hulled and supports bodies ~12.65 mm too high, which
                # no flag-based check can see because the declaration itself said "convex".
                support_z = getattr(collider, "support_z_m", None)
                if support_z is None:
                    res["support_height_verified"] = None
                else:
                    err = abs(res["rest_bottom_z"] - float(support_z))
                    res["support_height_verified"] = bool(err <= 0.002)
                    res["support_height_error_m"] = round(err, 9)
                    res["recorded_support_z_m"] = float(support_z)
                results["static_colliders"][key] = res
        finally:
            for body_id, group, mask in saved_masks:
                pb.setCollisionFilterGroupMask(body_id, -1, group, mask,
                                               physicsClientId=cid)

        results["ok"] = bool(
            results["controls"]["box_on_plane"]["rests"]
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
