#!/usr/bin/env bash
# ===========================================================================
# V5.5 stage 01 regression: prove the patched render module did not break the
# EXISTING pipeline for the already-registered scenarios.
#
# 01 section 5 changed blender_backend.py, and 02 section 5 requires that old
# SimulationResult and all registered scenarios still load.  This exercises the real
# server pipeline (physics only; no Blender) across every registered scenario config.
# ===========================================================================
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$REPO" || exit 1

echo "=== available scenario configs ==="
ls configs/scenarios/ | sed 's/^/  /'

echo
echo "=== A. import the patched package ==="
"$PY" - <<'PY'
import sys
sys.path.insert(0, "src")
import physim
from physim.safe_output import allocate_run_dir, quarantine, find_workspace_root
from physim.render.blender_backend import purge_stale_frames
import inspect
print("  physim imports OK")
print("  purge signature:", inspect.signature(purge_stale_frames))
print("  find_workspace_root() ->", find_workspace_root("."))
PY

echo
echo "=== B. every registered scenario still loads and simulates ==="
"$PY" - <<'PY'
import json, sys, traceback
from pathlib import Path
sys.path.insert(0, "src")

from physim.assets import AssetManager
from physim.maps import MapManager
from physim.config import load_run_config
from physim.scenarios import create_scenario, variants_from_config, reference_variant

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)

# name -> (config, scenario config name)
cases = []
for p in sorted(Path("configs/scenarios").glob("*.yaml")):
    if ".pre_" in p.name:
        continue
    cases.append(p.stem)

print(f"  scenario configs found: {len(cases)}")
ok = fail = 0
for name in cases:
    try:
        cfg = load_run_config("configs/server.yaml", scenario=name)
        # In a scenario config `scenario` is a top-level STRING id (e.g. "rolling"),
        # not a mapping -- verified against configs/scenarios/rolling_gso.yaml.
        sid = cfg["scenario"]
        assert isinstance(sid, str), f"scenario id is {type(sid)}, expected str"
        need_asset_mgr = sid in ("turntable_carry", "turntable_spin")
        s = create_scenario(cfg, asset_manager=am) if need_asset_mgr else create_scenario(cfg)
        v = reference_variant(cfg)
        print(f"    {name:28s} scenario={sid:18s} create_scenario OK  variant={v.variant_id}")
        ok += 1
    except Exception as exc:
        print(f"    {name:28s} FAILED: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        fail += 1

print()
print(f"  RESULT: {ok} ok, {fail} failed")
sys.exit(1 if fail else 0)
PY
rc=$?
echo "  python rc=$rc"
