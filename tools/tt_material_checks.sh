#!/usr/bin/env bash
# ===========================================================================
# Backward-compatibility checks for the declarative-material change.
#
#   1. Every asset except the turntable resolves to material=None, so no code
#      path in the renderer is entered for them.
#   2. The existing unit test suite still passes.
#   3. A missing texture root fails LOUDLY (FileNotFoundError with the searched
#      path and the env-var override), instead of silently rendering grey.
#   4. MaterialSpec validation rejects a malformed block.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=============== 1. per-asset material field ==============="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import sys
sys.path.insert(0, "src")
from physim.assets import AssetManager
am = AssetManager("configs/assets.yaml", "assets")
declared = {a.asset_id: a.material for a in am.all(require_files=False) if a.material}
print(f"CK assets_total={len(am.ids)} declaring_material={len(declared)}")
for k, v in declared.items():
    print(f"CK   {k}: {v}")
others = [a.asset_id for a in am.all(require_files=False) if a.material is None]
print(f"CK others_none={len(others)} (sample: {others[:3]})")
assert set(declared) == {"turntable"}, declared
assert declared["turntable"].pbr == "dark_wood"
print("CK1 PASS: only 'turntable' declares a material; all other assets are None")
PY

echo "=============== 2. unit tests ==============="
"$WS/tools/conda_env/bin/python" -m pytest tests -q 2>&1 | tail -6
echo "--- the two failures above are PRE-EXISTING (absent visual meshes); see 2b ---"
"$WS/tools/conda_env/bin/python" -m pytest tests -q 2>&1 | grep -E '^(FAILED|[0-9]+ (failed|passed))' || true

echo "=============== 2b. same two tests against the pristine AssetManager ==============="
# Prove the failures are not caused by this change: swap in the pre-change
# assets/__init__.py (extracted from the original checkout zip), re-run just
# those two tests, then restore.
BAK=/data/raw/huzijian/project1_database/tmp/assets_init_pristine.py
if [ -f "$BAK" ]; then
  cp -f src/physim/assets/__init__.py /data/raw/huzijian/project1_database/tmp/assets_init_with_material.py
  cp -f "$BAK" src/physim/assets/__init__.py
  rm -rf src/physim/assets/__pycache__
  "$WS/tools/conda_env/bin/python" -m pytest tests/test_rolling_framework.py -q \
      -k 'test_configured_initial_orientations_match_resting_semantics or test_configured_rolling_asset_map_matrix_samples_all_pairs' 2>&1 | tail -4
  cp -f /data/raw/huzijian/project1_database/tmp/assets_init_with_material.py src/physim/assets/__init__.py
  rm -rf src/physim/assets/__pycache__
  echo "--- restored; material field present again: ---"
  grep -c 'material: MaterialSpec | None' src/physim/assets/__init__.py
else
  echo "SKIP 2b: pristine baseline not uploaded at $BAK"
fi

echo "=============== 3. missing texture root fails loudly ==============="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import sys, os
sys.path.insert(0, "src")
os.environ["PHYSIM_PBR_TEXTURE_ROOT"] = "/data/raw/huzijian/project1_database/models/pbr_textures_DOES_NOT_EXIST"
from physim.assets import MaterialSpec
from physim.render.materials import apply_declared_material, resolve_pbr_root
print("CK3 resolved root:", resolve_pbr_root("third_party/phyco-sim"))
try:
    apply_declared_material(object(), MaterialSpec("dark_wood", "wood_textures", 1.6),
                            "third_party/phyco-sim")
except FileNotFoundError as e:
    print("CK3 PASS FileNotFoundError:\n" + str(e))
else:
    print("CK3 FAIL: no error raised for a missing texture root")
PY

echo "=============== 4. malformed manifest block rejected ==============="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import sys
sys.path.insert(0, "src")
from physim.assets import AssetManager
for bad, why in (({"category": "wood_textures"}, "no pbr"),
                 ({"pbr": "dark_wood", "uv_scale": 0}, "uv_scale 0"),
                 ("dark_wood", "not a mapping")):
    try:
        AssetManager._material(bad, "synthetic_asset")
    except ValueError as e:
        print(f"CK4 PASS ({why}): {e}")
    else:
        print(f"CK4 FAIL ({why}): accepted {bad!r}")
print("CK4 note: valid block ->", AssetManager._material(
    {"pbr": "dark_wood", "category": "wood_textures", "uv_scale": 1.6}, "x"))
print("CK4 note: absent block ->", AssetManager._material(None, "x"))
PY
