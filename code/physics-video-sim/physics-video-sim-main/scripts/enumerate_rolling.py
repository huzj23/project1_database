"""Enumerate configured rolling objects and maps with one deterministic seed.

The default mode validates Scenario sampling for the Cartesian product in the
rolling config. ``--blender-smoke`` additionally launches Blender once per pair
and builds the same PhyCo/Kubric scene used by rendering.  It intentionally does
not replace PyBullet simulation: the two-state trajectory used by the visual
smoke is clearly marked as synthetic in the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


MARKER = "ROLLING_MATRIX_WORKER="


def _script_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/local.yaml"))
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument(
        "--output", type=Path, default=Path("outputs/tests/rolling-asset-matrix.json")
    )
    parser.add_argument("--blender-smoke", action="store_true")
    parser.add_argument(
        "--render-previews",
        action="store_true",
        help="Render one PNG per asset/map pair (implies --blender-smoke).",
    )
    parser.add_argument(
        "--preview-engine",
        choices=("BLENDER_EEVEE", "CYCLES"),
        default="BLENDER_EEVEE",
        help="Blender engine used by --render-previews (default: BLENDER_EEVEE).",
    )
    parser.add_argument(
        "--preview-samples",
        type=int,
        help="Override the render sample count for preview PNGs.",
    )
    parser.add_argument(
        "--preview-lighting-preset",
        help="Add a named environment render.preview_lighting_presets rig.",
    )
    parser.add_argument(
        "--only-map-id",
        action="append",
        help="Limit matrix enumeration to one map ID; may be repeated.",
    )
    parser.add_argument(
        "--only-asset-id",
        action="append",
        help="Limit matrix enumeration to one asset ID; may be repeated.",
    )
    parser.add_argument("--blender-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--asset-id", help=argparse.SUPPRESS)
    parser.add_argument("--map-id", help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--preview-output", type=Path, help=argparse.SUPPRESS)
    return parser


def _project_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def _load_context(config_path: Path):
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root / "src"))
    from physim.assets import AssetManager
    from physim.config import load_run_config
    from physim.maps import MapManager

    resolved_config = _project_path(project_root, config_path).resolve()
    config = load_run_config(resolved_config)
    paths = config["paths"]
    asset_manager = AssetManager(
        _project_path(project_root, paths["asset_registry"]),
        _project_path(project_root, paths["asset_root"]),
    )
    map_manager = MapManager(
        _project_path(project_root, paths["map_registry"]), asset_manager
    )
    return project_root, resolved_config, config, asset_manager, map_manager


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sample_pair(config: dict[str, Any], asset, map_spec, seed: int) -> dict[str, Any]:
    from physim.scenarios.rolling import RollingScenario

    sample = RollingScenario(config).sample(seed, asset, map_spec)
    surface = map_spec.surface(sample.surface_id)
    duration = float(config["timing"]["duration_seconds"])
    endpoint = [
        sample.position[index] + sample.linear_velocity[index] * duration for index in range(3)
    ]
    xmin, xmax, ymin, ymax = surface.bounds_xy
    margin = sample.radius + float(
        surface.metadata.get("edge_margin", config["surface"]["edge_margin"])
    )
    collision_metadata = dict(asset.metadata.get("collision", {}))
    collision_mesh_hash = collision_metadata.get("mesh_sha256")
    checks = {
        "visual_exists": bool(asset.visual_path and asset.visual_path.is_file()),
        "environment_exists": map_spec.visual_path.is_file(),
        "asset_sha256": _sha256(asset.visual_path) == asset.metadata["sha256"],
        "environment_sha256": _sha256(map_spec.visual_path)
        == map_spec.metadata["sha256"],
        "collision_mesh_exists": (
            asset.collision.mesh_path is None or asset.collision.mesh_path.is_file()
        ),
        "collision_mesh_sha256": (
            asset.collision.mesh_path is None
            or collision_mesh_hash is None
            or _sha256(asset.collision.mesh_path) == collision_mesh_hash
        ),
        "collision_simulation_exists": (
            asset.collision.simulation_path is None
            or asset.collision.simulation_path.is_file()
        ),
        "spawn_height": math.isclose(
            sample.position[2],
            surface.position[2] + sample.support_height,
            abs_tol=1e-9,
        ),
        "start_in_bounds": (
            xmin + margin <= sample.position[0] <= xmax - margin
            and ymin + margin <= sample.position[1] <= ymax - margin
        ),
        "endpoint_in_bounds": (
            xmin + margin <= endpoint[0] <= xmax - margin
            and ymin + margin <= endpoint[1] <= ymax - margin
        ),
        "mass_in_range": asset.mass_range[0] <= sample.mass <= asset.mass_range[1],
        "friction_in_range": asset.friction_range[0]
        <= sample.friction
        <= asset.friction_range[1],
        "restitution_in_range": asset.restitution_range[0]
        <= sample.restitution
        <= asset.restitution_range[1],
    }
    return {
        "asset_id": asset.asset_id,
        "map_id": map_spec.map_id,
        "seed": seed,
        "surface_id": sample.surface_id,
        "position": list(sample.position),
        "linear_velocity": list(sample.linear_velocity),
        "angular_velocity": list(sample.angular_velocity),
        "radius": sample.radius,
        "support_height": sample.support_height,
        "mass": sample.mass,
        "friction": sample.friction,
        "restitution": sample.restitution,
        "predicted_endpoint": endpoint,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _synthetic_simulation(sample):
    from physim.physics import BodyState, SimulationResult

    duration = (sample.frame_count - 1) / sample.video_fps
    end_position = tuple(
        sample.position[index] + sample.linear_velocity[index] * duration for index in range(3)
    )
    states = (
        BodyState(
            1,
            0.0,
            sample.position,
            sample.initial_quaternion,
            sample.linear_velocity,
            sample.angular_velocity,
        ),
        BodyState(
            sample.frame_count,
            duration,
            end_position,
            sample.initial_quaternion,
            sample.linear_velocity,
            sample.angular_velocity,
        ),
    )
    return SimulationResult(trajectory=states, collisions=())


def _add_preview_lighting_preset(map_spec, preset_name: str | None) -> list[dict[str, Any]]:
    """Add a manifest-defined comparison rig without modifying source lights."""
    if not preset_name:
        return []

    import bpy
    from mathutils import Vector

    render_config = dict(map_spec.metadata.get("render", {}))
    presets = dict(render_config.get("preview_lighting_presets", {}))
    if preset_name not in presets:
        raise KeyError(
            f"Unknown preview lighting preset {preset_name!r} for map {map_spec.map_id!r}"
        )
    preset = dict(presets[preset_name])
    light_specs = [dict(spec) for spec in preset.get("lights", [])]
    if preset.get("include_manifest_supplemental_lights", False):
        light_specs.extend(
            dict(spec) for spec in render_config.get("supplemental_lights", [])
        )
    if preset.get("include_manifest_area_lights", False):
        light_specs.extend(
            {"type": "AREA", **dict(spec)}
            for spec in render_config.get("area_lights", [])
        )

    collection = bpy.data.collections.new(f"preview_lighting__{preset_name}")
    bpy.context.scene.collection.children.link(collection)
    added = []
    for index, spec in enumerate(light_specs):
        light_type = str(spec.get("type", "AREA")).upper()
        if light_type not in {"AREA", "SUN"}:
            raise ValueError(f"Unsupported preview light type: {light_type}")
        name = str(spec.get("name", f"preview_light_{index}"))
        data = bpy.data.lights.new(name=name, type=light_type)
        data.energy = float(spec["intensity"])
        data.color = tuple(float(value) for value in spec.get("color", (1, 1, 1)))
        obj = bpy.data.objects.new(name=name, object_data=data)
        collection.objects.link(obj)
        obj.location = tuple(float(value) for value in spec.get("position", (0, 0, 0)))
        if light_type == "AREA":
            data.shape = "RECTANGLE"
            data.size = float(spec["width"])
            data.size_y = float(spec.get("height", spec["width"]))
        if "look_at" in spec:
            direction = Vector(spec["look_at"]) - obj.location
            obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        elif "rotation_euler" in spec:
            obj.rotation_euler = tuple(float(value) for value in spec["rotation_euler"])
        added.append(
            {
                "name": name,
                "type": light_type,
                "intensity": data.energy,
                "position": [float(value) for value in obj.location],
            }
        )
    bpy.context.view_layer.update()
    return added


def _blender_worker(args: argparse.Namespace) -> int:
    project_root, _, config, asset_manager, map_manager = _load_context(args.config)
    if not args.asset_id or not args.map_id:
        raise ValueError("Blender worker requires --asset-id and --map-id")

    from physim.camera import merge_camera_config, perpendicular_camera
    from physim.render.blender_backend import PhyCoBlenderBackend
    from physim.scenarios.rolling import RollingScenario

    scenario_name = str(config["scenario"])
    asset = asset_manager.get(args.asset_id, kind="object", scenario=scenario_name)
    map_spec = map_manager.get(args.map_id, scenario=scenario_name)
    sample = RollingScenario(config).sample(args.seed, asset, map_spec)
    surface = map_spec.surface(sample.surface_id)
    simulation = _synthetic_simulation(sample)
    camera = perpendicular_camera(
        simulation,
        merge_camera_config(config["camera"], surface.metadata.get("camera")),
        max_object_extent=max(
            float(size) * float(scale)
            for size, scale in zip(
                asset.size or (asset.radius * 2.0,) * 3,
                asset.scale,
            )
        ),
    )
    scratch = project_root / "cache" / "rolling-matrix" / args.map_id / args.asset_id
    backend = PhyCoBlenderBackend(
        _project_path(project_root, config["paths"]["phyco_sim_root"]), scratch
    )
    built = backend.build_scene(sample, simulation, asset, map_spec, camera, config)
    preview_lights = _add_preview_lighting_preset(
        map_spec, args.preview_lighting_preset
    )
    preview_output = None
    if args.preview_output:
        import bpy

        preview_output = _project_path(project_root, args.preview_output)
        preview_output.parent.mkdir(parents=True, exist_ok=True)
        scene = bpy.context.scene
        scene.render.engine = args.preview_engine
        preview_samples = (
            args.preview_samples
            if args.preview_samples is not None
            else int(config["render"]["samples_per_pixel"])
        )
        if args.preview_engine == "CYCLES":
            scene.cycles.samples = preview_samples
            scene.cycles.use_denoising = bool(config["render"]["use_denoising"])
        else:
            scene.eevee.taa_render_samples = preview_samples
        scene.render.resolution_x = int(config["output"]["resolution"][0])
        scene.render.resolution_y = int(config["output"]["resolution"][1])
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(preview_output)
        scene.frame_set(1)
        bpy.ops.render.render(write_still=True)
    result = {
        "asset_id": args.asset_id,
        "map_id": args.map_id,
        "seed": args.seed,
        "surface_id": surface.surface_id,
        "surface_type": surface.surface_type,
        "trajectory_source": "synthetic_two_state_visual_smoke",
        "camera": camera.to_dict(),
        "diagnostics": built.diagnostics,
        "preview_lighting_preset": args.preview_lighting_preset,
        "preview_supplemental_lights": preview_lights,
        "preview_output": str(preview_output) if preview_output else None,
        "passed": True,
    }
    if args.worker_output:
        worker_output = _project_path(project_root, args.worker_output)
        worker_output.parent.mkdir(parents=True, exist_ok=True)
        worker_output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(MARKER + json.dumps(result, sort_keys=True))
    return 0


def _run_blender_smoke(
    project_root: Path,
    config_path: Path,
    config: dict[str, Any],
    asset_id: str,
    map_id: str,
    seed: int,
    preview_output: Path | None = None,
    preview_engine: str = "BLENDER_EEVEE",
    preview_samples: int | None = None,
    preview_lighting_preset: str | None = None,
) -> dict[str, Any]:
    blender = _project_path(project_root, config["paths"]["blender_executable"])
    worker_output = (
        project_root / "cache" / "rolling-matrix" / map_id / asset_id / "result.json"
    )
    command = [
        str(blender),
        "--background",
        "--factory-startup",
        "--python",
        str(Path(__file__).resolve()),
        "--",
        "--config",
        str(config_path),
        "--seed",
        str(seed),
        "--asset-id",
        asset_id,
        "--map-id",
        map_id,
        "--worker-output",
        str(worker_output),
        "--blender-worker",
    ]
    if preview_output is not None:
        command.extend(["--preview-output", str(preview_output)])
        command.extend(["--preview-engine", preview_engine])
        if preview_samples is not None:
            command.extend(["--preview-samples", str(preview_samples)])
        if preview_lighting_preset is not None:
            command.extend(["--preview-lighting-preset", preview_lighting_preset])
    environment = os.environ.copy()
    runtime_root = _project_path(
        project_root, config["paths"]["blender_python_packages"]
    )
    python_paths = [str(project_root / "src"), str(runtime_root)]
    if environment.get("PYTHONPATH"):
        python_paths.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(python_paths)
    completed = subprocess.run(
        command,
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    marker_lines = [line for line in completed.stdout.splitlines() if line.startswith(MARKER)]
    if completed.returncode or (not marker_lines and not worker_output.is_file()):
        return {
            "asset_id": asset_id,
            "map_id": map_id,
            "passed": False,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout.splitlines()[-20:],
            "stderr_tail": completed.stderr.splitlines()[-20:],
        }
    if worker_output.is_file():
        return json.loads(worker_output.read_text(encoding="utf-8"))
    return json.loads(marker_lines[-1][len(MARKER) :])


def main() -> int:
    args = _parser().parse_args(_script_args())
    if args.blender_worker:
        return _blender_worker(args)

    if args.render_previews:
        args.blender_smoke = True
    project_root, config_path, config, asset_manager, map_manager = _load_context(args.config)
    scenario_name = str(config["scenario"])
    rows = []
    map_ids = args.only_map_id or config["selection"]["map_ids"]
    asset_ids = args.only_asset_id or config["selection"]["asset_ids"]
    for map_id in map_ids:
        map_spec = map_manager.get(map_id, scenario=scenario_name)
        for asset_id in asset_ids:
            asset = asset_manager.get(asset_id, kind="object", scenario=scenario_name)
            row = _sample_pair(config, asset, map_spec, args.seed)
            if args.blender_smoke:
                row["blender_smoke"] = _run_blender_smoke(
                    project_root,
                    config_path,
                    config,
                    asset_id,
                    map_id,
                    args.seed,
                    (
                        project_root
                        / "outputs"
                        / "previews"
                        / "asset-matrix"
                        / (
                            f"{map_id}__{asset_id}.png"
                            if args.preview_engine == "BLENDER_EEVEE"
                            else f"{map_id}__{asset_id}__cycles.png"
                        )
                        if args.render_previews
                        else None
                    ),
                    args.preview_engine,
                    args.preview_samples,
                    args.preview_lighting_preset,
                )
                row["passed"] = row["passed"] and row["blender_smoke"]["passed"]
            rows.append(row)
            print(
                f"{'PASS' if row['passed'] else 'FAIL'} "
                f"asset={asset_id} map={map_id} seed={args.seed}"
            )

    report = {
        "schema_version": 1,
        "scenario": scenario_name,
        "seed_policy": "same fixed seed for every asset/map pair",
        "seed": args.seed,
        "physics_simulated": False,
        "blender_scene_built": args.blender_smoke,
        "pair_count": len(rows),
        "passed_count": sum(row["passed"] for row in rows),
        "failed_count": sum(not row["passed"] for row in rows),
        "pairs": rows,
    }
    output = _project_path(project_root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"ROLLING_MATRIX_REPORT={output}")
    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
