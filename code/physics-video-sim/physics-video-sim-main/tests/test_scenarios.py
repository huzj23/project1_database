from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from physim.assets import AssetSpec, CollisionSpec
from physim.config import load_yaml
from physim.maps import MapSpec, SurfaceSpec
from physim.physics import BodyState, SimulationResult
from physim.scenarios import ControlVariant, create_scenario, variants_from_config
from physim.validation import validate_sample


def _asset() -> AssetSpec:
    return AssetSpec(
        asset_id="sphere_test",
        kind="object",
        category="sphere",
        asset_dir=Path("."),
        visual_path=Path("sphere.glb"),
        render_import_kwargs={},
        collision=CollisionSpec("sphere", radius=0.1),
        size=(0.2, 0.2, 0.2),
        scale=(1.0, 1.0, 1.0),
        mass_range=(1.0, 1.2),
        friction_range=(0.4, 0.6),
        restitution_range=(0.7, 0.8),
        allowed_scenarios=("rolling", "constant_force", "free_fall"),
        metadata={},
    )


def _map() -> MapSpec:
    surface = SurfaceSpec(
        surface_id="floor",
        position=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        bounds_xy=(-10.0, 10.0, -10.0, 10.0),
        metadata={},
        surface_type="floor",
        object_extent_range=(0.0, 1.0),
    )
    return MapSpec(
        map_id="map",
        environment_asset_id="environment",
        visual_path=Path("scene.blend"),
        visual_scale=(1.0, 1.0, 1.0),
        render_import_kwargs={},
        collision_center=(0.0, 0.0, -0.05),
        collision_half_extents=(10.0, 10.0, 0.05),
        surfaces=(surface,),
        metadata={},
    )


def _shared(scenario: str) -> dict:
    return {
        "scenario": scenario,
        "controlled_variants": {
            "variable": {
                "rolling": "initial_speed",
                "constant_force": "constant_force",
                "free_fall": "gravity",
            }[scenario],
            "multipliers": [1.0, 0.5, 1.5],
            "labels": ["x1", "x0.5", "x1.5"],
        },
        "timing": {"duration_seconds": 1.5, "video_fps": 24, "physics_fps": 240},
        "surface": {"allowed_types": ["floor"], "edge_margin": 0.1},
    }


def test_rolling_controlled_speed_keeps_group_initial_frame_fixed() -> None:
    config = {
        **_shared("rolling"),
        "physics": {
            "gravity": [0, 0, -9.81],
            "rolling_friction": 0.0,
            "spinning_friction": 0.0,
            "linear_speed_range": [0.4, 0.6],
            "direction_degrees_range": [-10, 10],
        },
    }
    scenario = create_scenario(config)
    base = scenario.sample(7, _asset(), _map(), ControlVariant("x1", "initial_speed", 1.0))
    slow = scenario.sample(7, _asset(), _map(), ControlVariant("x0.5", "initial_speed", 0.5))

    assert slow.position == pytest.approx(base.position)
    assert slow.initial_quaternion == pytest.approx(base.initial_quaternion)
    assert slow.mass == pytest.approx(base.mass)
    assert np.linalg.norm(slow.linear_velocity) == pytest.approx(
        np.linalg.norm(base.linear_velocity) * 0.5
    )


def test_constant_force_variant_changes_only_force() -> None:
    config = {
        **_shared("constant_force"),
        "physics": {
            "gravity": [0, 0, -9.81],
            "rolling_friction": 0.0,
            "spinning_friction": 0.0,
            "initial_speed_range": [0.1, 0.2],
            "constant_acceleration_range": [0.2, 0.3],
            "direction_degrees_range": [-10, 10],
        },
    }
    scenario = create_scenario(config)
    base = scenario.sample(8, _asset(), _map(), ControlVariant("x1", "constant_force", 1.0))
    fast = scenario.sample(8, _asset(), _map(), ControlVariant("x1.5", "constant_force", 1.5))

    assert len(base.constant_force) == 3
    assert base.constant_force[2] == 0.0
    assert fast.position == pytest.approx(base.position)
    assert fast.linear_velocity == pytest.approx(base.linear_velocity)
    assert fast.mass == pytest.approx(base.mass)
    assert np.linalg.norm(fast.constant_force) == pytest.approx(
        np.linalg.norm(base.constant_force) * 1.5
    )


def test_free_fall_gravity_variant_keeps_drop_state_fixed() -> None:
    config = {
        **_shared("free_fall"),
        "timing": {"duration_seconds": 2.0, "video_fps": 24, "physics_fps": 240},
        "physics": {
            "gravity": [0, 0, -9.81],
            "horizontal_speed_range": [0.03, 0.12],
            "vertical_speed_range": [-0.05, 0.05],
            "angular_speed_range": [0.0, 2.0],
            "direction_degrees_range": [-180, 180],
            "drop_height_object_extent_range": [3.0, 6.0],
            "drop_height_absolute_range": [0.45, 1.2],
        },
    }
    scenario = create_scenario(config)
    base = scenario.sample(9, _asset(), _map(), ControlVariant("x1", "gravity", 1.0))
    strong = scenario.sample(9, _asset(), _map(), ControlVariant("x1.5", "gravity", 1.5))

    assert strong.position == pytest.approx(base.position)
    assert strong.linear_velocity == pytest.approx(base.linear_velocity)
    assert strong.angular_velocity == pytest.approx(base.angular_velocity)
    assert strong.gravity == pytest.approx(tuple(value * 1.5 for value in base.gravity))


def test_variant_config_rejects_invalid_groups() -> None:
    assert [item.variant_id for item in variants_from_config(_shared("rolling"))] == [
        "x1",
        "x0.5",
        "x1.5",
    ]
    with pytest.raises(ValueError, match="positive"):
        variants_from_config(
            {"controlled_variants": {"variable": "initial_speed", "multipliers": [0]}}
        )


@pytest.mark.parametrize(
    ("scenario_name", "variable"),
    (
        ("rolling", "initial_speed"),
        ("constant_force", "constant_force"),
        ("free_fall", "gravity"),
    ),
)
def test_production_defaults_and_controlled_variable_scope(
    scenario_name: str, variable: str
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = load_yaml(project_root / "configs" / "scenarios" / f"{scenario_name}.yaml")
    variants = {variant.variant_id: variant for variant in variants_from_config(config)}
    scenario = create_scenario(config)
    samples = {
        name: scenario.sample(23, _asset(), _map(), variant)
        for name, variant in variants.items()
    }
    baseline = samples["x1"]
    slow = samples["x0.5"]
    fast = samples["x1.5"]

    assert config["output"]["resolution"] == [1280, 720]
    assert baseline.video_fps == 16
    assert baseline.frame_count == 81
    assert {variant.variable for variant in variants.values()} == {variable}
    for candidate in (slow, fast):
        assert candidate.position == pytest.approx(baseline.position)
        assert candidate.initial_quaternion == pytest.approx(baseline.initial_quaternion)
        assert candidate.mass == pytest.approx(baseline.mass)
        assert candidate.friction == pytest.approx(baseline.friction)
        assert candidate.restitution == pytest.approx(baseline.restitution)

    if scenario_name == "rolling":
        assert np.linalg.norm(slow.linear_velocity) == pytest.approx(
            0.5 * np.linalg.norm(baseline.linear_velocity)
        )
        assert np.linalg.norm(fast.angular_velocity) == pytest.approx(
            1.5 * np.linalg.norm(baseline.angular_velocity)
        )
        assert slow.gravity == pytest.approx(baseline.gravity)
    elif scenario_name == "constant_force":
        assert slow.linear_velocity == pytest.approx(baseline.linear_velocity)
        assert slow.angular_velocity == pytest.approx(baseline.angular_velocity)
        assert np.linalg.norm(slow.constant_force) == pytest.approx(
            0.5 * np.linalg.norm(baseline.constant_force)
        )
        assert np.linalg.norm(fast.constant_force) == pytest.approx(
            1.5 * np.linalg.norm(baseline.constant_force)
        )
    else:
        assert slow.linear_velocity == pytest.approx(baseline.linear_velocity)
        assert slow.angular_velocity == pytest.approx(baseline.angular_velocity)
        assert slow.gravity == pytest.approx(tuple(0.5 * value for value in baseline.gravity))
        assert fast.gravity == pytest.approx(tuple(1.5 * value for value in baseline.gravity))


def test_constant_force_validation_measures_uniform_acceleration() -> None:
    config = {
        **_shared("constant_force"),
        "physics": {
            "gravity": [0, 0, -9.81],
            "initial_speed_range": [0.1, 0.1],
            "constant_acceleration_range": [0.2, 0.2],
            "direction_degrees_range": [0, 0],
        },
    }
    sample = create_scenario(config).sample(3, _asset(), _map())
    states = tuple(
        BodyState(
            frame=index + 1,
            time_seconds=time,
            position=(position, 0.0, 0.1),
            quaternion=(1.0, 0.0, 0.0, 0.0),
            linear_velocity=(velocity, 0.0, 0.0),
            angular_velocity=(0.0, velocity / 0.1, 0.0),
        )
        for index, (time, position, velocity) in enumerate(
            ((0.0, 0.0, 0.1), (0.5, 0.075, 0.2), (1.0, 0.2, 0.3))
        )
    )
    report = validate_sample(
        SimulationResult(states, ()),
        sample,
        _map().surfaces[0],
        {
            "min_travel_distance": 0.1,
            "max_linear_speed": 1.0,
            "max_trajectory_extent_object_ratio": 10.0,
            "min_force_response": 0.01,
            "max_acceleration_relative_std": 0.01,
            "require_supported": True,
            "require_in_map_bounds": True,
        },
    )
    assert report.valid
    assert report.metrics["acceleration_relative_std"] == pytest.approx(0.0)


def test_free_fall_validation_requires_collision_and_bounce() -> None:
    config = {
        **_shared("free_fall"),
        "physics": {
            "gravity": [0, 0, -9.81],
            "horizontal_speed_range": [0.05, 0.05],
            "vertical_speed_range": [0.0, 0.0],
            "angular_speed_range": [0.0, 0.0],
            "direction_degrees_range": [0, 0],
            "drop_height_object_extent_range": [4.0, 4.0],
            "drop_height_absolute_range": [0.4, 1.0],
        },
    }
    sample = create_scenario(config).sample(4, _asset(), _map())
    states = tuple(
        BodyState(
            frame=index + 1,
            time_seconds=time,
            position=(0.05 * time, 0.0, z),
            quaternion=(1.0, 0.0, 0.0, 0.0),
            linear_velocity=(0.05, 0.0, vz),
            angular_velocity=(0.0, 0.0, 0.0),
        )
        for index, (time, z, vz) in enumerate(
            (
                (0.0, 0.9, 0.0),
                (0.25, 0.5, -3.0),
                (0.5, 0.12, 2.0),
                (0.75, 0.3, 1.0),
                (1.0, 0.1, 0.0),
            )
        )
    )
    report = validate_sample(
        SimulationResult(states, ({"frame": 1.5},)),
        sample,
        _map().surfaces[0],
        {
            "min_drop_height": 0.3,
            "min_drop_distance": 0.25,
            "max_linear_speed": 8.0,
            "max_trajectory_extent_object_ratio": 10.0,
            "max_surface_penetration": 0.04,
            "require_expected_collision": True,
            "require_bounce": True,
            "min_bounce_upward_speed": 0.05,
            "require_in_map_bounds": True,
        },
    )
    assert report.valid
    assert report.metrics["collision_count"] == 1
    assert report.metrics["max_post_contact_upward_speed"] == pytest.approx(2.0)
