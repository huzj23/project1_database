"""Build a GUI preview from a server-produced simulation bundle."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


PREVIEW_MARKER = "PHYSIM_PREVIEW="


def _script_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--save-blend", type=Path, required=True)
    parser.add_argument("--sample-root", type=Path, required=True)
    args = parser.parse_args(_script_args())

    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root / "src"))

    import bpy

    from physim.camera import CameraSpec
    from physim.physics import load_simulation_result
    from physim.pipeline import prepare_sample
    from physim.preview import add_preview_guides
    from physim.render.blender_backend import PhyCoBlenderBackend
    from physim.scenarios import ControlVariant

    simulation = load_simulation_result(
        args.sample_root / "trajectory.json", args.sample_root / "collisions.json"
    )
    metadata_path = args.sample_root / "metadata.json"
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.is_file()
        else {}
    )
    variant_data = metadata.get("variant", {"variant_id": "baseline"})
    variant = ControlVariant(**variant_data)
    camera_data = metadata.get("camera")
    camera = CameraSpec(**camera_data) if camera_data else None
    prepared = prepare_sample(
        args.config,
        args.seed,
        scenario=args.scenario,
        variant=variant,
        asset_id=metadata.get("asset", {}).get("id"),
        map_id=metadata.get("map", {}).get("id"),
        simulation=simulation,
        camera_override=camera,
    )
    if metadata_path.is_file():
        recorded = metadata["physics"]
        sampled = prepared.sample.to_dict()
        for key in (
            "position",
            "linear_velocity",
            "angular_velocity",
            "mass",
            "friction",
            "restitution",
        ):
            expected = recorded[key]
            actual = sampled[key]
            expected_values = expected if isinstance(expected, list) else [expected]
            actual_values = actual if isinstance(actual, tuple) else [actual]
            if any(
                not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-9)
                for left, right in zip(expected_values, actual_values)
            ):
                raise RuntimeError(
                    f"Local Scenario sample does not match server metadata for {key}: "
                    f"{actual!r} != {expected!r}"
                )
    sample_id = (
        f"{prepared.sample.scenario}-seed-{prepared.sample.seed:06d}-"
        f"{prepared.sample.variant.variant_id}"
    )
    scratch_dir = prepared.project_root / "cache" / "preview" / sample_id
    backend = PhyCoBlenderBackend(prepared.phyco_sim_root, scratch_dir)
    built = backend.build_scene(
        prepared.sample,
        prepared.simulation,
        prepared.asset,
        prepared.map_spec,
        prepared.camera,
        prepared.config,
    )
    preview_config = dict(prepared.config)
    preview_config["camera_look_at"] = prepared.camera.look_at
    guides = add_preview_guides(
        built,
        prepared.sample,
        prepared.simulation,
        preview_config,
    )

    args.save_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.save_blend))
    result = {
        "asset": prepared.asset.asset_id,
        "blender_version": bpy.app.version_string,
        "camera": prepared.camera.to_dict(),
        "frame_count": len(prepared.simulation.trajectory),
        "guides": guides,
        "map": prepared.map_spec.map_id,
        "sample": prepared.sample.to_dict(),
        "save_blend": str(args.save_blend),
        "simulation_source": str(args.sample_root),
        "validation": prepared.validation.to_dict(),
    }
    print(PREVIEW_MARKER + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
