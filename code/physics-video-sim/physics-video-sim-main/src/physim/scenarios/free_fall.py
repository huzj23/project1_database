"""Free fall followed by a Bullet-resolved ground collision and bounce."""

from __future__ import annotations

import numpy as np

from physim.assets import AssetSpec
from physim.maps import MapSpec
from physim.maps.surface_sampler import SurfaceSampler
from physim.scenarios import ControlVariant, ScenarioSample
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


class FreeFallScenario:
    """Sample drop conditions; no position or bounce is scripted per frame."""

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
        mass, friction, restitution = base_physics(rng, asset, physics)
        extent = object_extent(asset)
        relative_height = uniform(rng, physics["drop_height_object_extent_range"])
        min_height, max_height = (
            float(value) for value in physics["drop_height_absolute_range"]
        )
        drop_height = min(max(relative_height * extent, min_height), max_height)
        horizontal_speed = uniform(rng, physics.get("horizontal_speed_range", (0.0, 0.0)))
        vertical_speed = uniform(rng, physics.get("vertical_speed_range", (0.0, 0.0)))
        linear_velocity = (
            float(direction[0] * horizontal_speed),
            float(direction[1] * horizontal_speed),
            float(vertical_speed),
        )
        angular_speed = uniform(rng, physics.get("angular_speed_range", (0.0, 0.0)))
        angular_axis = rng.normal(size=3)
        angular_axis /= max(float(np.linalg.norm(angular_axis)), 1e-12)
        angular_velocity = tuple(float(value * angular_speed) for value in angular_axis)
        duration, video_fps, physics_fps, frame_count = timing_parameters(timing)
        position = self.surface_sampler.sample_position(
            surface=surface,
            radius=asset.radius,
            support_height=asset.support_height + drop_height,
            direction_xy=direction,
            travel_distance=horizontal_speed * duration,
            edge_margin=edge_margin(self.config, surface),
            rng=rng,
        )
        gravity_multiplier = (
            variant.multiplier if variant.variable == "gravity" else 1.0
        )
        gravity = tuple(
            float(value) * gravity_multiplier for value in physics["gravity"]
        )
        if variant.variable == "restitution":
            restitution = min(1.0, restitution * variant.multiplier)
        return ScenarioSample(
            scenario="free_fall",
            seed=seed,
            variant=variant,
            asset_id=asset.asset_id,
            map_id=map_spec.map_id,
            surface_id=surface.surface_id,
            position=position,
            linear_velocity=linear_velocity,
            angular_velocity=angular_velocity,
            mass=mass,
            friction=friction,
            rolling_friction=float(physics.get("rolling_friction", 0.0)),
            spinning_friction=float(physics.get("spinning_friction", 0.0)),
            restitution=restitution,
            radius=asset.radius,
            support_height=asset.support_height,
            gravity=gravity,
            constant_force=(0.0, 0.0, 0.0),
            video_fps=video_fps,
            physics_fps=physics_fps,
            frame_count=frame_count,
            initial_quaternion=asset.initial_quaternion,
        )
