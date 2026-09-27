"""Thin adapter over PhyCo-Sim's vendored Kubric PyBullet backend."""

from __future__ import annotations

import math
from pathlib import Path

from physim.assets import AssetSpec
from physim.maps import MapSpec
from physim.physics import BodyState, SimulationResult
from physim.scenarios import ScenarioSample


def _body_states(positions, quaternions, linear, angular, video_fps):
    """Build the per-video-frame trajectory the renderer and validators consume."""
    return tuple(
        BodyState(
            frame=index + 1,
            time_seconds=index / video_fps,
            position=tuple(float(v) for v in positions[index]),
            quaternion=tuple(float(v) for v in quaternions[index]),
            linear_velocity=tuple(float(v) for v in linear[index]),
            angular_velocity=tuple(float(v) for v in angular[index]),
        )
        for index in range(len(positions))
    )


class PyBulletBackend:
    def __init__(self, phyco_sim_root: str | Path):
        self.phyco_sim_root = Path(phyco_sim_root)

    def simulate(
        self, sample: ScenarioSample, map_spec: MapSpec, asset: AssetSpec
    ) -> SimulationResult:
        # 240 Hz is the rate every existing scenario was calibrated at, and it
        # remains the default.  A scenario may declare a FINER rate because
        # Bullet's contact solver injects energy into rolling contact at coarse
        # timesteps: measured on an ideal cylinder on an ideal plane, started at
        # exactly v and omega = v/r with mu 0.36, the total mechanical energy
        # grows by a factor 1.37 at 240 Hz but only 1.03 at 1920 Hz (mass and
        # solver iterations have no effect at all -- see tools/_t1b_energy.sh).
        # Only the rate is relaxed; it may never be coarser than the calibrated
        # 240 Hz, and it must still divide evenly into the video frame rate.
        if sample.physics_fps < 240 or sample.physics_fps % sample.video_fps != 0:
            raise ValueError(
                "PhyCo-Sim's backend requires a physics rate that is at least "
                "240 Hz and a whole multiple of the video frame rate; got "
                f"{sample.physics_fps} Hz against {sample.video_fps} fps"
            )

        from physim.reference import load_phyco_kubric

        kb = load_phyco_kubric(self.phyco_sim_root)
        from kubric.simulator import PyBullet

        scene = kb.Scene(
            frame_start=1,
            frame_end=sample.frame_count,
            frame_rate=sample.video_fps,
            step_rate=sample.physics_fps,
            gravity=sample.gravity,
        )
        simulator = PyBullet(scene)
        # The vendored Kubric wrapper never calls setTimeStep (its own source
        # says "TODO: setTimeStep if scene.step_rate != 240 Hz"), so Bullet
        # keeps its 1/240 s default and `steps_per_frame = step_rate //
        # frame_rate` silently changes how much TIME a frame covers.  At the
        # calibrated 240 Hz the two agree, so this is skipped entirely and every
        # existing scenario keeps the exact timestep it was validated with.  A
        # scenario that declares a finer rate gets the timestep it asked for.
        if sample.physics_fps != 240:
            simulator._physics_client.setTimeStep(  # noqa: SLF001
                1.0 / float(sample.physics_fps)
            )
        surface = map_spec.surface(sample.surface_id)
        if surface.collision_simulation_path is not None:
            support_body = kb.FileBasedObject(
                name=f"surface_collision__{surface.surface_id}",
                asset_id=f"{map_spec.map_id}__{surface.surface_id}",
                simulation_filename=str(surface.collision_simulation_path),
                render_filename=None,
                scale=(1.0, 1.0, 1.0),
                static=True,
                friction=sample.friction,
                rolling_friction=sample.rolling_friction,
                spinning_friction=sample.spinning_friction,
                restitution=sample.restitution,
                background=True,
                segmentation_id=1,
            )
        else:
            xmin, xmax, ymin, ymax = surface.bounds_xy
            collision_thickness = float(
                surface.metadata.get("collision_thickness", 0.1)
            )
            support_body = kb.Cube(
                name=f"surface_collision__{surface.surface_id}",
                position=(
                    (xmin + xmax) / 2.0,
                    (ymin + ymax) / 2.0,
                    surface.position[2] - collision_thickness / 2.0,
                ),
                scale=(
                    (xmax - xmin) / 2.0,
                    (ymax - ymin) / 2.0,
                    collision_thickness / 2.0,
                ),
                static=True,
                friction=sample.friction,
                rolling_friction=sample.rolling_friction,
                spinning_friction=sample.spinning_friction,
                restitution=sample.restitution,
                background=True,
                segmentation_id=1,
            )
        if asset.collision.collision_type == "sphere":
            simulated_object = kb.Sphere(
                name="simulated_object",
                position=sample.position,
                quaternion=sample.initial_quaternion,
                scale=(sample.radius,) * 3,
                velocity=sample.linear_velocity,
                angular_velocity=sample.angular_velocity,
                mass=sample.mass,
                friction=sample.friction,
                rolling_friction=sample.rolling_friction,
                spinning_friction=sample.spinning_friction,
                restitution=sample.restitution,
                segmentation_id=2,
            )
            scene += [support_body, simulated_object]
        elif asset.collision.collision_type in ("mesh", "convex_hull"):
            # A sample may name an ALTERNATIVE collision geometry (the refined
            # side hull for a rolling object).  It is carried on the sample, so
            # the adapter never resolves assets itself and the default path --
            # used by every sample that does not declare one -- is untouched.
            collision_simulation = (
                getattr(sample, "collision_simulation_path", None)
                or asset.collision.simulation_path
            )
            if collision_simulation is None:
                raise ValueError(
                    f"Asset {asset.asset_id!r} has no collision simulation file"
                )
            simulated_object = kb.FileBasedObject(
                name="simulated_object",
                asset_id=asset.asset_id,
                simulation_filename=str(collision_simulation),
                render_filename=None,
                scale=asset.scale,
                static=False,
                segmentation_id=2,
            )
            scene += [support_body, simulated_object]
            # The reference URDF loader registers setters only after loading,
            # so apply sampled state after linking the object to PyBullet.
            simulated_object.position = sample.position
            simulated_object.quaternion = sample.initial_quaternion
            simulated_object.velocity = sample.linear_velocity
            simulated_object.angular_velocity = sample.angular_velocity
            simulated_object.mass = sample.mass
            simulated_object.friction = sample.friction
            simulated_object.rolling_friction = sample.rolling_friction
            simulated_object.spinning_friction = sample.spinning_friction
            simulated_object.restitution = sample.restitution

            half_extents = asset.collision.half_extents
            if half_extents is None:
                if asset.size is None:
                    raise ValueError(
                        f"Asset {asset.asset_id!r} requires size or collision half_extents"
                    )
                half_extents = tuple(
                    float(size) * float(scale) / 2.0
                    for size, scale in zip(asset.size, asset.scale)
                )
            x_half, y_half, z_half = half_extents
            inertia = (
                sample.mass * (y_half**2 + z_half**2) / 5.0,
                sample.mass * (x_half**2 + z_half**2) / 5.0,
                sample.mass * (x_half**2 + y_half**2) / 5.0,
            )
            # PhyCo-Sim exposes the body id but not an inertia setter. Keep
            # this compatibility adjustment in the project adapter.
            body_id = simulated_object.linked_objects[simulator]
            simulator._physics_client.changeDynamics(  # noqa: SLF001
                body_id,
                -1,
                mass=sample.mass,
                localInertiaDiagonal=inertia,
                lateralFriction=sample.friction,
                rollingFriction=sample.rolling_friction,
                spinningFriction=sample.spinning_friction,
                restitution=sample.restitution,
                # Velocity attenuation, integrated by the solver.  Zero for every
                # scenario that does not declare it, so this is inert elsewhere.
                linearDamping=float(getattr(sample, "linear_damping", 0.0)),
                angularDamping=float(getattr(sample, "angular_damping", 0.0)),
            )
        else:
            raise ValueError(
                f"Rigid-body simulation does not support collision type "
                f"{asset.collision.collision_type!r}"
            )
        if any(abs(value) > 1e-12 for value in sample.constant_force):
            import pybullet as pb

            simulator.add_persistent_force(
                simulator.get_obj_idx(simulated_object),
                sample.constant_force,
                # The planar force and displacement are collinear, so the
                # initial COM remains on the force line and introduces no
                # artificial torque while preserving a world-space vector.
                point=sample.position,
                frame=pb.WORLD_FRAME,
            )
        support_trajectory: tuple[BodyState, ...] = ()
        collisions: tuple[dict, ...] = ()
        if sample.support_asset_id is not None:
            # A driven second body (the turntable disc) exists for this sample,
            # so the shared run() loop is replaced by the drive loop below.
            object_animation, support_trajectory, support_collisions = (
                self._drive_support(kb, scene, simulator, sample, simulated_object)
            )
            collisions = tuple(support_collisions)
        else:
            animation, collisions = simulator.run(
                frame_start=scene.frame_start, frame_end=scene.frame_end
            )
            object_animation = animation[simulated_object]
        trajectory = tuple(
            BodyState(
                frame=index + 1,
                time_seconds=index / sample.video_fps,
                position=tuple(float(v) for v in object_animation["position"][index]),
                quaternion=tuple(float(v) for v in object_animation["quaternion"][index]),
                linear_velocity=tuple(float(v) for v in object_animation["velocity"][index]),
                angular_velocity=tuple(
                    float(v) for v in object_animation["angular_velocity"][index]
                ),
            )
            for index in range(len(object_animation["position"]))
        )
        serializable_collisions = tuple(
            {
                "frame": float(item["frame"]),
                "position": [float(v) for v in item["position"]],
                "contact_normal": [float(v) for v in item["contact_normal"]],
                "force": float(item["force"]),
                # Tangential friction, present only on the driven-support path.
                # It is carried through explicitly because this comprehension
                # rebuilds each row from a fixed key list, so any field not named
                # here would be dropped before it reaches the dataset.
                **(
                    {
                        "friction_force": float(item["friction_force"]),
                        "friction_direction": [
                            float(v) for v in item["friction_direction"]
                        ],
                    }
                    if "friction_force" in item
                    else {}
                ),
                # Kubric's run() reports asset objects here, while the turntable
                # drive loop reports names directly.  Accept both.
                "instances": [
                    instance if isinstance(instance, str) else instance.name
                    for instance in item["instances"]
                ],
            }
            for item in collisions
        )
        return SimulationResult(
            trajectory=trajectory,
            collisions=serializable_collisions,
            support_trajectory=support_trajectory,
        )

    # ------------------------------------------------------------------
    # Driven support body (turntable)
    # ------------------------------------------------------------------
    def _drive_support(self, kb, scene, simulator, sample, simulated_object):
        """Simulate a spinning disc that CARRIES the actor through contact.

        The disc is a real second dynamic body: PyBullet owns its rotation and
        resolves disc<->actor contact every substep, so the actor's circular path
        is a *consequence* of friction, never a scripted path.  This is the only
        place in the backend where a second body exists and it is reached only
        when the sample declares a support asset, so the single-body path above
        is untouched for every pre-existing scenario.

        The per-substep loop is the frozen, already-validated recipe:

          1. pin the disc's POSITION each substep, returning the ORIENTATION
             unchanged (do not reset it to identity)
          2. ``resetBaseVelocity(bid, [0,0,0], [0,0,omega])``
          3. ``stepSimulation()``
          4. repeat ``physics_fps // video_fps`` (=15) times per video frame

        Each step guards against a failure that was already observed and measured:

          * ``static=True`` on the disc becomes ``useFixedBase=True`` in the URDF
            loader, which bolts the disc to the world so it can NEVER rotate.
          * ``changeDynamics(bid, mass=0)`` makes the body static for the same
            reason, with the same result.
          * Resetting the disc's ORIENTATION to identity every substep destroys
            the rotation that was just integrated.
          * Teleporting the pose every substep instead of letting the solver
            resolve contact produced a measured slip of exactly 0.00 -- the disc
            appeared to spin but nothing was coupled to it.
          * Stepping once per video frame instead of 15 substeps makes the motion
            look about 10x too slow.
        """
        import pybullet as pbc

        del pbc  # module-level calls would target the WRONG client; see below
        # CRITICAL: module-level ``pybullet`` functions target physics client 0.
        # The Kubric wrapper opens its own client per PyBullet instance, and only
        # the FIRST simulator in a process gets id 0.  A second simulator (as in
        # any multi-sample run) therefore has its world stepped on a stale client
        # and never advances -- every state repeats the initial one, which looks
        # exactly like "the disc did not rotate".  ``simulator._physics_client``
        # is the wrapper's own proxy and binds physicsClientId on every call, so
        # all stepping and state reads go through it.
        client = simulator._physics_client  # noqa: SLF001

        support_position = tuple(float(v) for v in sample.support_position)
        disc = kb.FileBasedObject(
            name="support_object",
            asset_id=str(sample.support_asset_id),
            simulation_filename=str(sample.support_simulation_path),
            render_filename=None,
            scale=(1.0, 1.0, 1.0),
            # MUST be False: static=True would set useFixedBase and bolt it.
            static=False,
            segmentation_id=3,
        )
        scene += disc
        disc.position = support_position
        disc.quaternion = sample.support_quaternion
        disc.mass = float(sample.support_mass)
        disc.friction = min(float(sample.support_friction), 1.0)
        disc.rolling_friction = float(sample.support_rolling_friction)
        disc.spinning_friction = float(sample.support_spinning_friction)
        disc.restitution = float(sample.support_restitution)

        disc_id = disc.linked_objects[simulator]
        object_id = simulated_object.linked_objects[simulator]
        angular_velocity = [float(v) for v in sample.support_angular_velocity]
        substeps = sample.physics_fps // sample.video_fps
        # Kubric validates `friction` to <= 1.0, but the turntable manifest
        # declares friction_range [0.80, 1.30].  PyBullet itself accepts >1, so
        # the cap is Kubric's, not the solver's: clamp to the largest value the
        # property allows and record it, rather than letting a legal manifest
        # value crash the run.  The disc's effective friction is what the sweep
        # measured against, so this is reported, not hidden.
        clamped_disc_friction = min(float(sample.support_friction), 1.0)
        if clamped_disc_friction != float(sample.support_friction):
            import sys as _sys

            print(
                f"DIAG support friction clamped "
                f"{float(sample.support_friction):.4f} -> {clamped_disc_friction:.4f} "
                "(Kubric caps friction at 1.0)",
                file=_sys.stderr,
                flush=True,
            )
        disc.friction = clamped_disc_friction

        actor_position: list = []
        actor_quaternion: list = []
        actor_linear: list = []
        actor_angular: list = []
        disc_position: list = []
        disc_quaternion: list = []
        disc_linear: list = []
        disc_angular: list = []
        collisions: list[dict] = []

        for _frame in range(sample.frame_count):
            for _substep in range(substeps):
                # 1. Pin POSITION only.  Reading the orientation back and passing
                #    it straight through preserves the integrated rotation;
                #    writing identity here would erase it every substep.
                _current, orientation = client.getBasePositionAndOrientation(disc_id)
                client.resetBasePositionAndOrientation(
                    disc_id, support_position, orientation
                )
                # 2. Re-impose the constant drive -- this is the turntable motor.
                client.resetBaseVelocity(disc_id, [0.0, 0.0, 0.0], angular_velocity)
                # 3. Let Bullet integrate gravity, contact and friction.
                client.stepSimulation()
            # 4. One recorded state per video frame, after all 15 substeps.
            #    PyBullet's raw getBasePositionAndOrientation returns XYZW
            #    quaternions while this project stores WXYZ everywhere, so the
            #    simulator's own accessor is used -- it performs the conversion.
            position, quaternion = simulator.get_position_and_rotation(object_id)
            linear, angular = simulator.get_velocities(object_id)
            actor_position.append(position)
            actor_quaternion.append(quaternion)
            actor_linear.append(linear)
            actor_angular.append(angular)
            position, quaternion = simulator.get_position_and_rotation(disc_id)
            linear, angular = simulator.get_velocities(disc_id)
            disc_position.append(position)
            disc_quaternion.append(quaternion)
            disc_linear.append(linear)
            disc_angular.append(angular)
            contact = self._disc_contact(client, disc_id, object_id)
            if contact is not None:
                # One row per frame in contact: the disc<->actor normal force is
                # the direct evidence that the actor is being CARRIED by contact
                # rather than merely placed near the disc.
                collisions.append({"frame": float(_frame + 1), **contact})

        # The disc pose the renderer replays is the state the SOLVER produced
        # (read back above), not a re-derived angle: the physics engine owns the
        # rotation and Blender only replays it.
        support_trajectory = _body_states(
            disc_position, disc_quaternion, disc_linear, disc_angular, sample.video_fps
        )
        actor_trajectory = _body_states(
            actor_position, actor_quaternion, actor_linear, actor_angular, sample.video_fps
        )
        object_animation = {
            "position": [state.position for state in actor_trajectory],
            "quaternion": [state.quaternion for state in actor_trajectory],
            "velocity": [state.linear_velocity for state in actor_trajectory],
            "angular_velocity": [state.angular_velocity for state in actor_trajectory],
        }
        return object_animation, support_trajectory, collisions

    @staticmethod
    def _disc_contact(client, disc_id, object_id) -> dict | None:
        """Return the strongest disc<->actor contact for the current frame.

        ``client`` is the simulator's own physics-client proxy, so the query is
        scoped to the world being simulated rather than to client 0.

        PyBullet's contact tuple is
        ``(contactFlag, bodyA, bodyB, linkA, linkB, positionOnA, positionOnB,
        contactNormalOnB, contactDistance, normalForce, lateralFriction1,
        lateralFrictionDir1, lateralFriction2, lateralFrictionDir2)``.

        The LATERAL friction components are recorded alongside the normal force
        on purpose.  For a carried actor the normal force only holds it up; the
        force that actually sweeps it around the circle is tangential friction,
        so the lateral terms are the physical evidence that the circular motion
        came from the contact rather than from the placement.
        """
        best = None
        for contact in client.getContactPoints(bodyA=disc_id, bodyB=object_id):
            normal_force = float(contact[9])
            if normal_force <= 1e-6:
                continue
            lateral_1 = float(contact[10])
            lateral_2 = float(contact[12])
            friction_force = math.hypot(lateral_1, lateral_2)
            if best is None or normal_force > best["force"]:
                best = {
                    "position": [float(v) for v in contact[5]],
                    "contact_normal": [float(v) for v in contact[7]],
                    "force": normal_force,
                    "friction_force": friction_force,
                    "friction_direction": [
                        float(v) for v in contact[11]
                    ],
                    "instances": ["support_object", "simulated_object"],
                }
        return best


# Backward-compatible import name used by the phase-one code and older bundles.
PhyCoPyBulletBackend = PyBulletBackend
