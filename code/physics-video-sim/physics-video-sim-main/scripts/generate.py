"""Generate one validated scenario sample or controlled-variable group."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _script_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/server.yaml")
    parser.add_argument("--scenario", choices=("rolling", "constant_force", "free_fall"))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--variant")
    parser.add_argument("--all-variants", action="store_true")
    parser.add_argument("--asset-id")
    parser.add_argument("--map-id")
    args = parser.parse_args(_script_args())
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root / "src"))
    from physim.config import load_run_config
    from physim.pipeline import run_group, run_sample
    from physim.scenarios import variants_from_config

    config_path = project_root / args.config
    config = load_run_config(config_path, scenario=args.scenario)
    seed = int(config["project"]["seed"] if args.seed is None else args.seed)
    if args.all_variants:
        if args.asset_id or args.map_id:
            raise ValueError("--all-variants does not accept asset/map overrides")
        outputs = run_group(config_path, seed, scenario=args.scenario)
        for output in outputs:
            print(f"SAMPLE_OUTPUT={output}")
    else:
        variants = variants_from_config(config)
        if args.variant is None:
            variant = next(
                (item for item in variants if item.multiplier == 1.0), variants[0]
            )
        else:
            try:
                variant = next(item for item in variants if item.variant_id == args.variant)
            except StopIteration as exc:
                available = ", ".join(item.variant_id for item in variants)
                raise ValueError(
                    f"Unknown variant {args.variant!r}; available: {available}"
                ) from exc
        output = run_sample(
            config_path,
            seed,
            scenario=args.scenario,
            variant=variant,
            asset_id=args.asset_id,
            map_id=args.map_id,
        )
        print(f"SAMPLE_OUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
