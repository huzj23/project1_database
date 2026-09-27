from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from physim.assets import AssetSpec, CollisionSpec
from physim.camera import perpendicular_camera
from physim.maps import MapManager, MapSpec, SurfaceSpec
from physim.maps.surface_sampler import SurfaceSampler
from physim.physics import BodyState, SimulationResult, load_simulation_result
from physim.scenarios import RollingSample
from physim.scenarios.rolling import RollingScenario
from physim.validation import validate_rolling


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _surface() -> SurfaceSpec:
    return SurfaceSpec(
        surface_id="court_top",
        position=(0.0, 0.0, 0.246),
        normal=(0.0, 0.0, 1.0),
        bounds_xy=(-13.0, 13.0, -7.0, 7.0),
        metadata={},
    )


def _config() -> dict:
    return {
        "timing": {"duration_seconds": 1.5, "video_fps": 24, "physics_fps": 240},
        "physics": {
            "gravity": [0.0, 0.0, -9.81],
            "rolling_friction": 0.003,
            "spinning_friction": 0.003,
            "linear_speed_range": [1.25, 1.75],
            "direction_degrees_range": [-10.0, 10.0],
        },
        "surface": {"edge_margin": 0.5},
    }


def test_rolling_sample_is_deterministic_and_has_pure_rolling_omega() -> None:
    asset = AssetSpec(
        asset_id="ball",
        kind="object",
        category="ball",
        asset_dir=Path("."),
        visual_path=Path("ball.glb"),
        render_import_kwargs={},
        collision=CollisionSpec("sphere", radius=0.12),
        size=(0.24, 0.24, 0.24),
        scale=(1.0, 1.0, 1.0),
        mass_range=(0.58, 0.65),
        friction_range=(0.45, 0.75),
        restitution_range=(0.7, 0.85),
        allowed_scenarios=("rolling",),
        metadata={},
    )
    map_spec = MapSpec(
        map_id="court",
        environment_asset_id="court_asset",
        visual_path=Path("court.glb"),
        visual_scale=(16.0, 16.0, 16.0),
        render_import_kwargs={},
        collision_center=(0.0, 0.0, 0.123),
        collision_half_extents=(16.0, 10.0, 0.123),
        surfaces=(_surface(),),
        metadata={},
    )
    scenario = RollingScenario(_config())
    first = scenario.sample(123, asset, map_spec)
    second = scenario.sample(123, asset, map_spec)
    assert first == second
    velocity = np.asarray(first.linear_velocity)
    omega = np.asarray(first.angular_velocity)
    contact_velocity = velocity + np.cross(omega, np.asarray((0.0, 0.0, -first.radius)))
    np.testing.assert_allclose(contact_velocity, 0.0, atol=1e-9)


def test_surface_sampler_selects_region_by_object_extent() -> None:
    floor = SurfaceSpec(
        surface_id="floor",
        position=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        bounds_xy=(-2.0, 2.0, -1.0, 1.0),
        metadata={},
        surface_type="floor",
        object_extent_range=(0.18, 0.35),
    )
    table = SurfaceSpec(
        surface_id="table",
        position=(0.0, 0.0, 0.8),
        normal=(0.0, 0.0, 1.0),
        bounds_xy=(-0.5, 0.5, -0.4, 0.4),
        metadata={},
        surface_type="table_top",
        object_extent_range=(0.03, 0.10),
    )
    sampler = SurfaceSampler()

    assert sampler.select_surface(
        (floor, table), 0.24, ("floor", "table_top"), np.random.default_rng(1)
    ) == floor
    assert sampler.select_surface(
        (floor, table), 0.06, ("floor", "table_top"), np.random.default_rng(1)
    ) == table
    with pytest.raises(ValueError, match="No surface accepts"):
        sampler.select_surface(
            (floor, table), 0.14, ("floor", "table_top"), np.random.default_rng(1)
        )


def test_polygon_surface_rejects_cutout_and_respects_margin() -> None:
    surface = SurfaceSpec(
        surface_id="l_shape",
        position=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        bounds_xy=(0.0, 2.0, 0.0, 2.0),
        polygon_xy=((0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0), (1.0, 2.0), (0.0, 2.0)),
        metadata={},
    )

    assert surface.contains_xy(0.5, 1.5)
    assert not surface.contains_xy(1.5, 1.5)
    assert not surface.contains_xy(0.05, 0.5, margin=0.1)


def test_mesh_footprint_radius_can_be_smaller_than_3d_bounding_radius() -> None:
    asset = AssetSpec(
        asset_id="handled_cup",
        kind="object",
        category="special",
        asset_dir=Path("."),
        visual_path=Path("cup.glb"),
        render_import_kwargs={},
        collision=CollisionSpec(
            "mesh",
            mesh_path=Path("cup.obj"),
            simulation_path=Path("cup.urdf"),
            bounding_radius=0.083,
            footprint_radius=0.059,
            support_height=0.060,
        ),
        size=(0.083, 0.118, 0.120),
        scale=(1.0, 1.0, 1.0),
        mass_range=(0.25, 0.40),
        friction_range=(0.3, 0.6),
        restitution_range=(0.05, 0.15),
        allowed_scenarios=("rolling",),
        metadata={},
    )

    assert asset.radius == pytest.approx(0.059)
    assert asset.support_height == pytest.approx(0.060)


def test_configured_initial_orientations_match_resting_semantics() -> None:
    from physim.assets import AssetManager

    manager = AssetManager(PROJECT_ROOT / "configs/assets.yaml", PROJECT_ROOT / "assets")
    cup = manager.get("special_coffee_cup", kind="object", scenario="rolling")
    lime = manager.get("food_lime", kind="object", scenario="rolling")

    assert cup.initial_quaternion == pytest.approx((1.0, 0.0, 0.0, 0.0))
    assert cup.support_height == pytest.approx(0.060)
    assert lime.initial_quaternion == pytest.approx(
        (2**-0.5, 0.0, -(2**-0.5), 0.0)
    )
    assert lime.support_height == pytest.approx(0.030081)
    assert lime.radius == pytest.approx(0.037884)


def test_grouped_map_rejects_unverified_surface_cleanliness() -> None:
    with pytest.raises(ValueError, match="cleanliness: verified_clear"):
        MapManager._surface_entries(
            {
                "surface_groups": [
                    {
                        "surface_type": "table_top",
                        "regions": [
                            {
                                "region_id": "cluttered_teacher_desk",
                                "position": [0, 0, 0.8],
                                "normal": [0, 0, 1],
                                "bounds_xy": [0, 1, 0, 1],
                            }
                        ],
                    }
                ]
            }
        )


def test_camera_is_perpendicular_to_horizontal_motion() -> None:
    states = (
        BodyState(1, 0.0, (0.0, 0.0, 0.366), (1.0, 0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0)),
        BodyState(2, 1.0, (2.0, 0.0, 0.366), (1.0, 0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0)),
    )
    camera = perpendicular_camera(
        SimulationResult(states, ()),
        {"side": "right", "distance": 7.0, "height": 2.2, "look_at_height": 0.35, "focal_length_mm": 50.0},
    )
    motion = np.asarray(states[-1].position[:2]) - np.asarray(states[0].position[:2])
    view_offset = np.asarray(camera.position[:2]) - np.asarray(camera.look_at[:2])
    assert abs(float(np.dot(motion, view_offset))) < 1e-9


def test_camera_azimuth_override_orbits_around_world_z_without_changing_height() -> None:
    states = (
        BodyState(1, 0.0, (0.0, 0.0, 0.2), (1, 0, 0, 0), (1, 0, 0), (0, 1, 0)),
        BodyState(2, 1.0, (1.0, 0.0, 0.2), (1, 0, 0, 0), (1, 0, 0), (0, 1, 0)),
    )
    base = {
        "side": "right",
        "distance": 2.0,
        "height": 1.0,
        "look_at_height": 0.2,
        "focal_length_mm": 50.0,
    }
    original = perpendicular_camera(SimulationResult(states, ()), base)
    rotated = perpendicular_camera(
        SimulationResult(states, ()),
        {**base, "azimuth_offset_degrees": 90.0},
    )

    assert rotated.position[2] == original.position[2]
    np.testing.assert_allclose(rotated.look_at, original.look_at)
    original_offset = np.asarray(original.position[:2]) - np.asarray(original.look_at[:2])
    rotated_offset = np.asarray(rotated.position[:2]) - np.asarray(rotated.look_at[:2])
    assert np.linalg.norm(rotated_offset) == pytest.approx(np.linalg.norm(original_offset))
    assert float(np.dot(original_offset, rotated_offset)) == pytest.approx(0.0, abs=1e-9)


def test_camera_can_use_height_relative_to_an_elevated_trajectory() -> None:
    states = (
        BodyState(1, 0.0, (0.0, 0.0, 1.5), (1.0, 0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0)),
        BodyState(2, 1.0, (1.0, 0.0, 1.5), (1.0, 0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0)),
    )
    camera = perpendicular_camera(
        SimulationResult(states, ()),
        {
            "side": "right",
            "distance": 2.0,
            "height": 1.2,
            "look_at_height": 0.25,
            "focal_length_mm": 50.0,
            "relative_to_trajectory": True,
        },
    )

    assert camera.position[2] == pytest.approx(2.7)
    assert camera.look_at[2] == pytest.approx(1.75)


def test_camera_framing_uses_trajectory_and_largest_object_extent() -> None:
    config = {
        "side": "right",
        "relative_to_trajectory": True,
        "focal_length_mm": 35.0,
        "framing": {
            "sensor_width_mm": 36.0,
            "trajectory_frame_fraction": 0.8,
            "object_padding": 0.25,
            "min_object_frame_fraction": 0.03,
            "max_object_frame_fraction": 0.30,
            "min_distance": 0.4,
            "max_distance": 8.0,
            "elevation_degrees": 12.0,
            "min_height_above_trajectory": 0.45,
            "look_at_offset": 0.0,
        },
    }
    short_states = (
        BodyState(1, 0.0, (0.0, 0.0, 0.1), (1, 0, 0, 0), (1, 0, 0), (0, 1, 0)),
        BodyState(2, 1.0, (1.0, 0.0, 0.1), (1, 0, 0, 0), (1, 0, 0), (0, 1, 0)),
    )
    long_states = (
        short_states[0],
        BodyState(2, 1.0, (1.5, 0.0, 0.1), (1, 0, 0, 0), (1, 0, 0), (0, 1, 0)),
    )

    small = perpendicular_camera(
        SimulationResult(short_states, ()), config, max_object_extent=0.08
    )
    large = perpendicular_camera(
        SimulationResult(short_states, ()), config, max_object_extent=0.22
    )
    longer = perpendicular_camera(
        SimulationResult(long_states, ()), config, max_object_extent=0.08
    )

    assert small.framing is not None
    assert large.framing is not None
    assert longer.framing is not None
    assert large.framing["distance"] > small.framing["distance"]
    assert longer.framing["distance"] > small.framing["distance"]
    assert small.framing["min_object_frame_fraction"] <= small.framing[
        "object_frame_fraction"
    ]
    assert small.framing["object_frame_fraction"] <= small.framing[
        "max_object_frame_fraction"
    ]


def test_validation_accepts_supported_in_bounds_motion() -> None:
    states = tuple(
        BodyState(
            frame=index + 1,
            time_seconds=index / 24,
            position=(index * 0.06, 0.0, 0.366),
            quaternion=(1.0, 0.0, 0.0, 0.0),
            linear_velocity=(1.44, 0.0, 0.0),
            angular_velocity=(0.0, 12.0, 0.0),
        )
        for index in range(25)
    )
    sample = RollingSample(
        seed=1,
        asset_id="ball",
        map_id="court",
        surface_id="court_top",
        position=states[0].position,
        linear_velocity=states[0].linear_velocity,
        angular_velocity=states[0].angular_velocity,
        mass=0.62,
        friction=0.6,
        rolling_friction=0.003,
        spinning_friction=0.003,
        restitution=0.75,
        radius=0.12,
        support_height=0.12,
        gravity=(0.0, 0.0, -9.81),
        video_fps=24,
        physics_fps=240,
        frame_count=25,
    )
    report = validate_rolling(
        SimulationResult(states, ()),
        sample,
        _surface(),
        {
            "min_travel_distance": 1.0,
            "max_linear_speed": 10.0,
            "require_supported": True,
            "require_in_map_bounds": True,
        },
    )
    assert report.valid


def test_load_simulation_result(tmp_path: Path) -> None:
    trajectory_path = tmp_path / "trajectory.json"
    collisions_path = tmp_path / "collisions.json"
    trajectory_path.write_text(
        """[
          {
            "frame": 1,
            "time_seconds": 0.0,
            "position": [1, 2, 3],
            "quaternion": [1, 0, 0, 0],
            "linear_velocity": [4, 5, 6],
            "angular_velocity": [7, 8, 9]
          }
        ]""",
        encoding="utf-8",
    )
    collisions_path.write_text('[{"frame": 1.0}]', encoding="utf-8")

    result = load_simulation_result(trajectory_path, collisions_path)

    assert result.trajectory == (
        BodyState(
            1,
            0.0,
            (1.0, 2.0, 3.0),
            (1.0, 0.0, 0.0, 0.0),
            (4.0, 5.0, 6.0),
            (7.0, 8.0, 9.0),
        ),
    )
    assert result.collisions == ({"frame": 1.0},)


def test_configured_rolling_asset_map_matrix_samples_all_pairs() -> None:
    from physim.assets import AssetManager
    from physim.config import load_run_config
    from physim.maps import MapManager

    config = load_run_config(PROJECT_ROOT / "configs" / "local.yaml")
    asset_manager = AssetManager(
        PROJECT_ROOT / config["paths"]["asset_registry"],
        PROJECT_ROOT / config["paths"]["asset_root"],
    )
    map_manager = MapManager(
        PROJECT_ROOT / config["paths"]["map_registry"], asset_manager
    )
    scenario = RollingScenario(config)
    pairs = []
    for map_id in config["selection"]["map_ids"]:
        map_spec = map_manager.get(map_id, scenario="rolling")
        for asset_id in config["selection"]["asset_ids"]:
            asset = asset_manager.get(asset_id, kind="object", scenario="rolling")
            sample = scenario.sample(123, asset, map_spec)
            surface = map_spec.surface(sample.surface_id)
            xmin, xmax, ymin, ymax = surface.bounds_xy
            assert xmin < sample.position[0] < xmax
            assert ymin < sample.position[1] < ymax
            assert sample.position[2] == pytest.approx(
                surface.position[2] + asset.support_height
            )
            object_extent = max(
                float(size) * float(scale)
                for size, scale in zip(asset.size, asset.scale)
            )
            assert surface.supports_object_extent(object_extent)
            if map_id == "classroom" and object_extent >= 0.18:
                assert surface.surface_type == "floor"
            if map_id == "classroom" and object_extent <= 0.10:
                assert surface.surface_type == "table_top"
                assert "teacher" not in surface.surface_id
            pairs.append((asset_id, map_id))

    expected_pair_count = len(config["selection"]["map_ids"]) * len(
        config["selection"]["asset_ids"]
    )
    assert len(pairs) == expected_pair_count
    assert len(set(pairs)) == expected_pair_count
