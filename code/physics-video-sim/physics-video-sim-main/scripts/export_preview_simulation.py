"""Export a validated physics bundle for local Blender GUI preview."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import yaml


def _script_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--scenario", default="rolling")
    parser.add_argument("--variant")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(_script_args())

    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root / "src"))
    from physim.config import load_run_config
    from physim.pipeline import prepare_sample
    from physim.scenarios import variants_from_config

    config = load_run_config(args.config, scenario=args.scenario)
    variants = variants_from_config(config)
    variant = (
        next((item for item in variants if item.variant_id == args.variant), None)
        if args.variant
        else next((item for item in variants if item.multiplier == 1.0), variants[0])
    )
    if variant is None:
        raise ValueError(f"Unknown variant {args.variant!r}")
    prepared = prepare_sample(
        args.config, args.seed, scenario=args.scenario, variant=variant
    )
    args.output.mkdir(parents=True, exist_ok=False)
    _write_json(
        args.output / "trajectory.json",
        [state.to_dict() for state in prepared.simulation.trajectory],
    )
    _write_json(args.output / "collisions.json", list(prepared.simulation.collisions))
    _write_json(
        args.output / "metadata.json",
        {
            "schema_version": 1,
            "scenario": prepared.sample.scenario,
            "seed": prepared.sample.seed,
            "variant": prepared.sample.variant.to_dict(),
            "asset": {
                "id": prepared.asset.asset_id,
                "material": (
                    dataclasses.asdict(prepared.asset.material)
                    if prepared.asset.material is not None
                    else None
                ),
            },
            "map": {
                "id": prepared.map_spec.map_id,
                "surface_id": prepared.sample.surface_id,
            },
            "physics": prepared.sample.to_dict(),
            "camera": prepared.camera.to_dict(),
            "validation": prepared.validation.to_dict(),
            "frame_count": len(prepared.simulation.trajectory),
        },
    )
    with (args.output / "config.yaml").open("w", encoding="utf-8") as stream:
        yaml.safe_dump(prepared.config, stream, sort_keys=False)
    print(f"PREVIEW_SIMULATION_OUTPUT={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
