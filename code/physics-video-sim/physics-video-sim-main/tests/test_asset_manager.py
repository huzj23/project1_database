from __future__ import annotations

from pathlib import Path

import pytest

from physim.assets import AssetManager
from physim.maps import MapManager


def _write_registry(root: Path) -> Path:
    registry = root / "assets.yaml"
    registry.write_text(
        """version: 2
manifest: asset.yaml
roots:
  object: objects
  environment: environments
  material: materials
  hdri: hdri
""",
        encoding="utf-8",
    )
    return registry


def _write_asset(root: Path, kind_root: str, asset_id: str, extension: str) -> None:
    asset_dir = root / kind_root / asset_id
    visual = asset_dir / f"visual{extension}"
    visual.parent.mkdir(parents=True)
    visual.write_bytes(b"test")
    kind = {
        "objects": "object",
        "environments": "environment",
        "materials": "material",
        "hdri": "hdri",
    }[kind_root]
    category = "sphere" if kind == "object" else kind
    collision = "type: none"
    if kind == "object":
        collision = "type: sphere\n  radius: 0.12"
    elif kind == "environment":
        collision = (
            "type: box\n"
            "  center: [0, 0, 0.1]\n"
            "  half_extents: [5, 4, 0.1]"
        )
    blend_option = "\n  object_name: TestObject" if extension == ".blend" else ""
    asset_dir.joinpath("asset.yaml").write_text(
        f"""version: 1
id: {asset_id}
kind: {kind}
category: {category}
visual:
  mesh: visual{extension}{blend_option}
  size: [0.24, 0.24, 0.24]
  scale: [1, 1, 1]
collision:
  {collision}
physics:
  mass_range: [0.5, 0.7]
  friction_range: [0.4, 0.8]
  restitution_range: [0.1, 0.9]
allowed_scenarios: [rolling]
""",
        encoding="utf-8",
    )


def test_discovers_all_asset_kinds_and_reads_custom_ball(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path)
    _write_asset(tmp_path, "objects", "custom_ball", ".glb")
    _write_asset(tmp_path, "environments", "court", ".fbx")
    _write_asset(tmp_path, "materials", "rubber", ".mtl")
    _write_asset(tmp_path, "hdri", "studio", ".hdr")

    manager = AssetManager(registry, tmp_path)
    ball = manager.get("custom_ball", kind="object", scenario="rolling")

    assert manager.ids == ("court", "custom_ball", "rubber", "studio")
    assert ball.category == "sphere"
    assert ball.radius == 0.12
    assert ball.size == (0.24, 0.24, 0.24)
    assert ball.mass_range == (0.5, 0.7)
    assert ball.friction_range == (0.4, 0.8)
    assert ball.restitution_range == (0.1, 0.9)
    assert ball.allowed_scenarios == ("rolling",)


def test_rejects_scenario_not_allowed_by_asset(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path)
    _write_asset(tmp_path, "objects", "custom_ball", ".obj")

    manager = AssetManager(registry, tmp_path)

    with pytest.raises(ValueError, match="not allowed"):
        manager.get("custom_ball", scenario="free_fall")


@pytest.mark.parametrize(
    "extension", [".blend", ".fbx", ".glb", ".gltf", ".obj", ".wrl", ".x3d"]
)
def test_accepts_phyco_blender_import_formats(tmp_path: Path, extension: str) -> None:
    registry = _write_registry(tmp_path)
    _write_asset(tmp_path, "objects", "custom_ball", extension)

    asset = AssetManager(registry, tmp_path).get("custom_ball", scenario="rolling")

    assert asset.visual_path is not None
    assert asset.visual_path.suffix == extension
    if extension == ".blend":
        assert asset.render_import_kwargs["filename"] == "TestObject"


def test_map_resolves_environment_only_through_asset_manager(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path)
    _write_asset(tmp_path, "environments", "court", ".glb")
    map_registry = tmp_path / "maps.yaml"
    map_registry.write_text(
        """version: 2
maps:
  court_map:
    environment_asset_id: court
    surfaces:
      - surface_id: top
        position: [0, 0, 0.2]
        normal: [0, 0, 1]
        bounds_xy: [-5, 5, -4, 4]
""",
        encoding="utf-8",
    )

    asset_manager = AssetManager(registry, tmp_path)
    map_spec = MapManager(map_registry, asset_manager).get(
        "court_map", scenario="rolling"
    )

    assert map_spec.environment_asset_id == "court"
    assert map_spec.visual_path == tmp_path / "environments" / "court" / "visual.glb"
    assert map_spec.collision_half_extents == (5.0, 4.0, 0.1)


def test_rejects_asset_file_outside_its_directory(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path)
    asset_dir = tmp_path / "objects" / "bad"
    asset_dir.mkdir(parents=True)
    asset_dir.joinpath("asset.yaml").write_text(
        """version: 1
id: bad
kind: object
category: test
visual:
  mesh: ../other/model.glb
collision:
  type: sphere
  radius: 0.1
allowed_scenarios: [rolling]
""",
        encoding="utf-8",
    )

    manager = AssetManager(registry, tmp_path)

    with pytest.raises(ValueError, match="escapes"):
        manager.get("bad", require_files=False)


def test_non_primitive_object_requires_low_poly_collision_mesh(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path)
    _write_asset(tmp_path, "objects", "food_lime", ".glb")
    manifest = tmp_path / "objects" / "food_lime" / "asset.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "category: sphere", "category: food"
        ),
        encoding="utf-8",
    )

    manager = AssetManager(registry, tmp_path)

    with pytest.raises(ValueError, match="requires a low-poly"):
        manager.get("food_lime")
