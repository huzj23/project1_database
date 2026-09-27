"""Deterministic sampler for the first rolling scenario."""

from __future__ import annotations

import numpy as np

from physim.assets import AssetSpec
from physim.maps import MapSpec
from physim.maps.surface_sampler import SurfaceSampler
from physim.scenarios import ControlVariant, ScenarioSample, reference_variant
from physim.scenarios.common import (
    base_physics,
    default_variant,
    edge_margin,
    object_extent,
    planar_direction,
    resolve_initial_orientation,
    select_surface,
    timing_parameters,
    uniform,
)


class RollingScenario:
    def __init__(self, config: dict, surface_sampler: SurfaceSampler | None = None):
        self.config = config
        self.surface_sampler = surface_sampler or SurfaceSampler()

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
        surface = select_surface(
            self.config, asset, map_spec, rng, self.surface_sampler
        )
        direction = planar_direction(rng, physics, surface)
        # The pose is resolved BEFORE the speed and the spawn point because it
        # can change the support height and footprint radius, and both of those
        # feed the spawn height and the reserved travel distance.  With no
        # `orientation` block this returns the manifest pose and the manifest
        # geometry, so the arithmetic below is unchanged.
        initial_quaternion, support_height, footprint_radius, orientation = (
            resolve_initial_orientation(self.config, asset, direction)
        )
        duration, video_fps, physics_fps, frame_count = timing_parameters(timing)
        relative_travel_range = physics.get("travel_object_extent_range")
        if relative_travel_range is None:
            base_speed = uniform(
                rng,
                surface.metadata.get(
                    "linear_speed_range", physics["linear_speed_range"]
                ),
            )
        else:
            base_speed = (
                uniform(rng, relative_travel_range) * object_extent(asset) / duration
            )
            surface_speed_range = surface.metadata.get("linear_speed_range")
            if surface_speed_range is not None:
                base_speed = min(
                    max(base_speed, float(surface_speed_range[0])),
                    float(surface_speed_range[1]),
                )
        speed_multiplier = (
            variant.multiplier if variant.variable == "initial_speed" else 1.0
        )
        speed = base_speed * speed_multiplier
        linear_velocity = np.asarray((direction[0] * speed, direction[1] * speed, 0.0))
        normal = np.asarray((0.0, 0.0, 1.0))
        # Rolling without slipping about the (possibly horizontal) spin axis.
        # With the long axis laid along n x d by the side pose, this is the rate
        # that makes the contact-point surface velocity zero.
        angular_velocity = np.cross(normal, linear_velocity) / support_height
        reserved_multiplier = (
            reference_variant(self.config).multiplier
            if variant.variable == "initial_speed"
            else 1.0
        )
        position = self.surface_sampler.sample_position(
            surface=surface,
            radius=footprint_radius,
            support_height=support_height,
            direction_xy=direction,
            travel_distance=base_speed * reserved_multiplier * duration,
            edge_margin=edge_margin(self.config, surface),
            rng=rng,
        )
        mass, friction, restitution = base_physics(
            rng, asset, self._contact_physics(physics, orientation)
        )
        return ScenarioSample(
            scenario="rolling",
            seed=seed,
            variant=variant,
            asset_id=asset.asset_id,
            map_id=map_spec.map_id,
            surface_id=surface.surface_id,
            position=position,
            linear_velocity=tuple(float(v) for v in linear_velocity),
            angular_velocity=tuple(float(v) for v in angular_velocity),
            mass=mass,
            friction=friction,
            rolling_friction=float(physics["rolling_friction"]),
            spinning_friction=float(physics["spinning_friction"]),
            restitution=restitution,
            radius=footprint_radius,
            support_height=support_height,
            gravity=tuple(float(v) for v in physics["gravity"]),
            constant_force=(0.0, 0.0, 0.0),
            video_fps=video_fps,
            physics_fps=physics_fps,
            frame_count=frame_count,
            initial_quaternion=initial_quaternion,
            orientation=orientation,
            collision_simulation_path=orientation.get("collision_simulation"),
        )

    @staticmethod
    def _contact_physics(
        physics: dict, orientation: dict
    ) -> dict:
        """Let the orientation block override the contact friction range.

        A body only rolls if friction can actually resist slip at the contact;
        the manifest's own range is the right default and is used whenever the
        orientation block does not name a replacement, so no existing sample
        changes.
        """
        override = orientation.get("friction_range")
        if override is None:
            return physics
        return {**physics, "friction_range": [float(v) for v in override]}
