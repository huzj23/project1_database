"""Motions #5/#6: an actor carried by a spinning turntable disc.

Two scenarios share one mechanism:

``turntable_carry`` (圆周运动)
    The disc spins at a constant angular velocity and a real scanned actor
    placed on it is CARRIED AROUND by contact friction.  The circular path is a
    consequence of the disc<->actor contact that PyBullet resolves every
    substep; nothing about the arc is written down anywhere.

``turntable_spin`` (转盘自转)
    The same rig at a slower spin, so the actor stays put on the disc and
    co-rotates with it.  What the clip shows is the rotation of the disc itself
    (and of the actor riding it) rather than a large arc.

What the sampler does and does NOT decide
-----------------------------------------
The sampler chooses the *initial conditions and the drive*: where the disc sits
on the table, how fast it turns, where the actor is placed on it, and the
contact parameters.  It never places the actor at a later time, and it never
writes an angle into the trajectory.  The actor's position at every frame comes
out of the solver.

Geometry (all frozen and measured, see ``configs/maps.yaml``)
-------------------------------------------------------------
``replicad_apartment_table_top`` is a flat 0.60 x 0.60 m region whose measured
top is z = 0.7584.  The disc is r = 0.30 m and 0.022 m thick, so its centre sits
at 0.7584 + 0.011 = 0.7694 and its top face -- the surface the actor rests on --
is at 0.7804.  The actor is therefore spawned at ``0.7694 + disc_half + support``
which is exactly the height ``actor_support_z + support_height`` that the
validator checks against.

The disc is loaded with the map's own floor mesh as collision (not the table
geometry): the disc is a dynamic body resting on its contact with that mesh,
and the table is scenery in the render.  The 0.30 m radius is the frozen value;
0.55 m hangs off the table edge.
"""

from __future__ import annotations

import math

import numpy as np

from physim.assets import AssetManager, AssetSpec
from physim.maps import MapSpec
from physim.maps.surface_sampler import SurfaceSampler
from physim.scenarios import ControlVariant, ScenarioSample
from physim.scenarios.common import (
    base_physics,
    default_variant,
    select_surface,
    timing_parameters,
    uniform,
)

class TurntableScenario:
    """Sample a spinning-disc scene for one actor."""

    #: Scenario name -> whether the actor is meant to be carried around the
    #: disc (large net arc) or to ride it in place (small net arc).
    CARRY = "turntable_carry"
    SPIN = "turntable_spin"

    def __init__(
        self,
        config: dict,
        surface_sampler: SurfaceSampler | None = None,
        asset_manager: AssetManager | None = None,
    ):
        self.config = config
        self.surface_sampler = surface_sampler or SurfaceSampler()
        self.asset_manager = asset_manager
        self.scenario_name = str(config["scenario"])
        if self.scenario_name not in (self.CARRY, self.SPIN):
            raise KeyError(f"TurntableScenario cannot serve {self.scenario_name!r}")

    # ------------------------------------------------------------------
    def _support_asset(self) -> AssetSpec:
        """Resolve the turntable disc through the AssetManager.

        The disc is declared in the scenario config as an asset id, never as a
        path: scenario code must not build absolute asset paths.
        """
        support_id = str(self.config["support"]["asset_id"])
        if self.asset_manager is None:
            raise ValueError(
                "The turntable scenario needs an AssetManager to resolve its "
                f"support asset {support_id!r}; create_scenario() was called "
                "without one"
            )
        # The disc declares `allowed_scenarios: []` on purpose -- it is scenery
        # the actor rides on, not a subject -- so ask for it without a scenario.
        return self.asset_manager.get(support_id, kind="object")

    # ------------------------------------------------------------------
    def _select_surface(self, asset, map_spec, rng):
        """Resolve the region the disc stands on.

        The generic sampler filters regions by the ACTOR's extent, which is the
        right rule when the actor rests directly on the map.  Here the thing that
        must fit on the table is the 0.60 m DISC, not the actor, and the measured
        `replicad_apartment_table_top` region is exactly 0.60 x 0.60 m -- so it is
        named explicitly by id and the disc fit is checked against it below.
        The actor's own fit is a separate check, against the disc.
        """
        surface_id = self.config["surface"].get("surface_id")
        if surface_id:
            surface = map_spec.surface(str(surface_id))
            allowed = tuple(
                str(value) for value in self.config["surface"].get("allowed_types", ())
            )
            if allowed and surface.surface_type not in allowed:
                raise ValueError(
                    f"Surface {surface.surface_id!r} has type "
                    f"{surface.surface_type!r}, expected one of {allowed}"
                )
            return surface
        return select_surface(
            self.config, asset, map_spec, rng, self.surface_sampler
        )

    # ------------------------------------------------------------------
    def sample(
        self,
        seed: int,
        asset: AssetSpec,
        map_spec: MapSpec,
        variant: ControlVariant | None = None,
    ) -> ScenarioSample:
        variant = default_variant(variant)
        rng = np.random.default_rng(seed)
        physics = self.config["physics"]
        timing = self.config["timing"]
        support_config = self.config["support"]
        surface = self._select_surface(asset, map_spec, rng)
        disc = self._support_asset()
        if disc.collision.simulation_path is None:
            raise ValueError(
                f"Support asset {disc.asset_id!r} has no URDF collision; the "
                "turntable needs an exact cylinder primitive"
            )
        duration, video_fps, physics_fps, frame_count = timing_parameters(timing)

        disc_radius = float(disc.radius)
        disc_half = float(disc.support_height)

        # --- where the disc sits on the table --------------------------------
        # The region is chosen by the map, but the disc must fit ENTIRELY inside
        # it.  `replicad_apartment_table_top` is exactly the disc's own diameter
        # (0.60 x 0.60 m for a 0.30 m disc), so the disc has no freedom at all
        # there and is pinned to the region centre -- which is precisely the
        # placement the region was measured for.  A larger region leaves slack
        # and the disc is sampled within it.
        xmin, xmax, ymin, ymax = surface.bounds_xy
        centre_x = (xmin + xmax) / 2.0
        centre_y = (ymin + ymax) / 2.0
        if (xmax - xmin) / 2.0 < disc_radius or (ymax - ymin) / 2.0 < disc_radius:
            raise ValueError(
                f"Surface {surface.surface_id!r} is {(xmax - xmin):.3f} x "
                f"{(ymax - ymin):.3f} m, too small for a {2 * disc_radius:.3f} m disc"
            )
        disc_margin = float(surface.metadata.get("disc_edge_margin", 0.0))
        slack_x = max(0.0, (xmax - xmin) / 2.0 - disc_radius - disc_margin)
        slack_y = max(0.0, (ymax - ymin) / 2.0 - disc_radius - disc_margin)
        disc_x = centre_x + float(rng.uniform(-slack_x, slack_x))
        disc_y = centre_y + float(rng.uniform(-slack_y, slack_y))
        disc_z = float(surface.position[2]) + disc_half
        disc_position = (disc_x, disc_y, disc_z)
        # The disc's TOP face: the surface the actor actually rests on.
        actor_support_z = disc_z + disc_half

        # --- the drive -------------------------------------------------------
        # Omega is measured, not guessed: see configs/scenarios/*.yaml for the
        # sweep that establishes the carried band and the throw-off threshold.
        omega = uniform(
            rng,
            surface.metadata.get("angular_speed_range", physics["angular_speed_range"]),
        )
        if variant.variable == "angular_speed":
            omega *= variant.multiplier

        # --- where the actor sits on the disc --------------------------------
        # Kept well inside the rim so the actor cannot be spun off by the
        # placement alone; the configured range is a fraction of the radius.
        orbit_fraction = uniform(
            rng, physics.get("orbit_radius_fraction_range", (0.35, 0.55))
        )
        orbit_radius = orbit_fraction * disc_radius
        start_angle = float(rng.uniform(0.0, 2.0 * math.pi))
        # Actors are only accepted if they physically fit on the disc without
        # overhanging the rim at their own footprint radius.
        if orbit_radius + float(asset.radius) > disc_radius:
            raise ValueError(
                f"Actor {asset.asset_id!r} (footprint {asset.radius:.3f} m) does "
                f"not fit on a {disc_radius:.3f} m disc at orbit {orbit_radius:.3f} m"
            )

        mass, friction, restitution = base_physics(rng, asset, physics)
        # The actor is placed at rest ON the disc: its circular motion must come
        # from the contact, so it is given NO initial linear or angular velocity.
        # A non-zero spin here would be us prescribing part of the motion.
        position = (
            disc_x + orbit_radius * math.cos(start_angle),
            disc_y + orbit_radius * math.sin(start_angle),
            actor_support_z + float(asset.support_height),
        )
        return ScenarioSample(
            scenario=self.scenario_name,
            seed=seed,
            variant=variant,
            asset_id=asset.asset_id,
            map_id=map_spec.map_id,
            surface_id=surface.surface_id,
            position=position,
            linear_velocity=(0.0, 0.0, 0.0),
            angular_velocity=(0.0, 0.0, 0.0),
            mass=mass,
            friction=friction,
            rolling_friction=float(physics.get("rolling_friction", 0.0)),
            spinning_friction=float(physics.get("spinning_friction", 0.0)),
            restitution=restitution,
            radius=asset.radius,
            support_height=asset.support_height,
            gravity=tuple(float(v) for v in physics["gravity"]),
            constant_force=(0.0, 0.0, 0.0),
            video_fps=video_fps,
            physics_fps=physics_fps,
            frame_count=frame_count,
            initial_quaternion=asset.initial_quaternion,
            # --- the driven disc ---
            support_asset_id=disc.asset_id,
            support_simulation_path=str(disc.collision.simulation_path),
            support_visual_path=str(disc.visual_path),
            support_render_import_kwargs=dict(disc.render_import_kwargs),
            # The disc's manifest declares its material; carrying the spec on the
            # sample keeps manifest knowledge in the scenario and bpy out of it.
            support_material=disc.material,
            support_position=disc_position,
            support_quaternion=(1.0, 0.0, 0.0, 0.0),
            support_mass=float(
                uniform(rng, support_config.get("mass_range", disc.mass_range))
            ),
            support_friction=float(
                uniform(
                    rng, support_config.get("friction_range", disc.friction_range)
                )
            ),
            support_rolling_friction=float(support_config.get("rolling_friction", 0.0)),
            support_spinning_friction=float(
                support_config.get("spinning_friction", 0.0)
            ),
            support_restitution=float(support_config.get("restitution", 0.0)),
            support_radius=disc_radius,
            support_half_thickness=disc_half,
            support_angular_velocity=(0.0, 0.0, omega),
            orbit_radius=orbit_radius,
            actor_support_z=actor_support_z,
        )
