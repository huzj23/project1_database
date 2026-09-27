"""Scenario 4: damped motion (阻尼运动).

The actor is given an initial speed on a frictionless support and its velocity is
attenuated by Bullet's own damping coefficients.  Nothing about the trajectory is
prescribed: the sampler chooses an initial state and a damping coefficient, the
solver integrates ``v(t) = v0 * (1 - k*dt)^(t/dt)``, and the validator measures
what actually happened.

This is deliberately NOT friction.  Coulomb friction produces a constant
deceleration (``v = v0 - mu*g*t``, a straight line that reaches zero in finite
time), whereas damping produces exponential decay that approaches zero
asymptotically.  Keeping ``lateralFriction = 0`` and using ``linearDamping``
separates the two so the clip shows genuine damped motion.
"""

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


class DampingScenario:
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

        # Each variant scales the damping coefficient, so the x0.5 clip visibly
        # travels further than x1 and x1.5 stops sooner.  Same seed, same spawn
        # pose, same nuisance variables -- only the declared variable changes.
        damping_multiplier = (
            variant.multiplier if variant.variable == "damping" else 1.0
        )
        base_damping = uniform(rng, physics["damping_range"])
        damping = base_damping * damping_multiplier

        relative_travel_range = physics.get("travel_object_extent_range")
        if relative_travel_range is None:
            base_speed = uniform(rng, physics["initial_speed_range"])
        else:
            # Distance under exponential decay is v0/k * (1 - exp(-k*T)); solve for
            # the v0 that yields the requested travel.
            travel = uniform(rng, relative_travel_range) * object_extent(asset)
            decay = max(damping, 1e-6)
            base_speed = travel * decay / max(1.0 - np.exp(-decay * duration), 1e-6)
        initial_speed = base_speed

        linear_velocity = np.asarray(
            (direction[0] * initial_speed, direction[1] * initial_speed, 0.0)
        )
        # A sliding (non-rolling) start: no spin is imposed.  Our actors are convex
        # hulls, so an imposed rolling spin would merely be braked by the contact.
        angular_velocity = np.zeros(3, dtype=np.float64)

        # Reserve room for the FULL decay integral of the largest variant, so a
        # slower-decaying sibling still fits inside the surface.
        reserved_damping = max(
            base_damping * reference_variant(self.config).multiplier, 1e-6
        )
        reserved_distance = (
            base_speed / reserved_damping * (1.0 - np.exp(-reserved_damping * duration))
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
        mass, friction, restitution = base_physics(rng, asset, physics)
        return ScenarioSample(
            scenario="damping",
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
            constant_force=(0.0, 0.0, 0.0),
            video_fps=video_fps,
            physics_fps=physics_fps,
            frame_count=frame_count,
            initial_quaternion=asset.initial_quaternion,
            linear_damping=float(damping),
            angular_damping=float(damping),
        )
