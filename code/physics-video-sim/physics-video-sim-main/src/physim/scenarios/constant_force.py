"""Planar motion driven by a constant world-space force."""

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
    select_surface,
    timing_parameters,
    uniform,
)


class ConstantForceScenario:
    """Sample conditions only; Bullet integrates the resulting acceleration."""

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
        duration, video_fps, physics_fps, frame_count = timing_parameters(timing)
        extent = object_extent(asset)
        initial_travel_range = physics.get("initial_travel_object_extent_range")
        if initial_travel_range is None:
            speed_range = surface.metadata.get(
                "initial_speed_range", physics["initial_speed_range"]
            )
            initial_speed = uniform(rng, speed_range)
        else:
            initial_speed = uniform(rng, initial_travel_range) * extent / duration
        mass, friction, restitution = base_physics(rng, asset, physics)
        acceleration_travel_range = physics.get(
            "acceleration_travel_object_extent_range"
        )
        if acceleration_travel_range is None:
            base_acceleration = uniform(rng, physics["constant_acceleration_range"])
        else:
            acceleration_travel = uniform(rng, acceleration_travel_range) * extent
            base_acceleration = 2.0 * acceleration_travel / duration**2
        force_multiplier = (
            variant.multiplier if variant.variable == "constant_force" else 1.0
        )
        acceleration = base_acceleration * force_multiplier
        force_magnitude = mass * acceleration
        force = np.asarray(
            (direction[0] * force_magnitude, direction[1] * force_magnitude, 0.0)
        )
        linear_velocity = np.asarray(
            (direction[0] * initial_speed, direction[1] * initial_speed, 0.0)
        )
        normal = np.asarray((0.0, 0.0, 1.0))
        angular_velocity = np.cross(normal, linear_velocity) / asset.support_height
        reserved_multiplier = (
            reference_variant(self.config).multiplier
            if variant.variable == "constant_force"
            else 1.0
        )
        reserved_distance = (
            initial_speed * duration
            + 0.5 * base_acceleration * reserved_multiplier * duration**2
        )
        position = self.surface_sampler.sample_position(
            surface=surface,
            radius=asset.radius,
            support_height=asset.support_height,
            direction_xy=direction,
            travel_distance=reserved_distance,
            edge_margin=edge_margin(self.config, surface),
            rng=rng,
        )
        return ScenarioSample(
            scenario="constant_force",
            seed=seed,
            variant=variant,
            asset_id=asset.asset_id,
            map_id=map_spec.map_id,
            surface_id=surface.surface_id,
            position=position,
            linear_velocity=tuple(float(value) for value in linear_velocity),
            angular_velocity=tuple(float(value) for value in angular_velocity),
            mass=mass,
            friction=friction,
            rolling_friction=float(physics.get("rolling_friction", 0.0)),
            spinning_friction=float(physics.get("spinning_friction", 0.0)),
            restitution=restitution,
            radius=asset.radius,
            support_height=asset.support_height,
            gravity=tuple(float(value) for value in physics["gravity"]),
            constant_force=tuple(float(value) for value in force),
            video_fps=video_fps,
            physics_fps=physics_fps,
            frame_count=frame_count,
            initial_quaternion=asset.initial_quaternion,
        )
