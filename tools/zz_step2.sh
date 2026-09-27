#!/usr/bin/env bash
# Install manifests + licenses, wire the rename through live configs,
# copy the missing HF tooling, and report the maps.yaml cleanliness state.
set -uo pipefail
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
UP=/data/raw/huzijian/project1_database/tmp/upstream
cd "$R" || exit 1

EL=assets/objects/special_plush_elephant
RA=assets/environments/replicad_apartment

echo "=== install elephant manifest + license ==="
cp -f "$UP/elephant_asset.yaml"  "$EL/asset.yaml"
cp -f "$UP/elephant_SOURCE.md"   "$EL/license/SOURCE.md"

echo "=== install replicad manifest + license ==="
cp -f "$UP/replicad_asset.yaml"  "$RA/asset.yaml"
cp -f "$UP/replicad_SOURCE.md"   "$RA/license/SOURCE.md"

echo "=== wire rename into LIVE configs (datasets/ untouched) ==="
for f in configs/scenarios/turntable_carry_gso.yaml configs/scenarios/turntable_spin_gso.yaml; do
  before=$(grep -c 'gso_sootheze_cold_therapy_elephant' "$f" || true)
  sed -i 's/gso_sootheze_cold_therapy_elephant/special_plush_elephant/g' "$f"
  after=$(grep -c 'special_plush_elephant' "$f" || true)
  echo "  $f : old=$before new=$after"
done

echo "=== copy missing HF tooling from the mentor's clone (not run, not modified) ==="
mkdir -p scripts docs
cp -f /data/raw/huzijian/project1_database/tmp/hf_src/sync_hf_assets.py        scripts/sync_hf_assets.py
cp -f /data/raw/huzijian/project1_database/tmp/hf_src/HUGGINGFACE_DATASET_CARD.md docs/HUGGINGFACE_DATASET_CARD.md
sha256sum scripts/sync_hf_assets.py docs/HUGGINGFACE_DATASET_CARD.md
echo "  source sha256 (must match):"
sha256sum /data/raw/huzijian/project1_database/tmp/hf_src/sync_hf_assets.py \
          /data/raw/huzijian/project1_database/tmp/hf_src/HUGGINGFACE_DATASET_CARD.md

echo
echo "=== maps.yaml: replicad_apartment region cleanliness ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import yaml
m = yaml.safe_load(open("configs/maps.yaml"))
rep = m["maps"]["replicad_apartment"]
n = 0
for grp in rep.get("surface_groups", []):
    print(f"  surface_type={grp.get('surface_type')}")
    for r in grp.get("regions", []):
        n += 1
        print(f"    region_id={r.get('region_id')}")
        print(f"      cleanliness={r.get('cleanliness')!r}")
        print(f"      verification={r.get('verification')!r}")
print(f"  total regions: {n}")
PY

echo
echo "=== final tree: elephant ==="
find "$EL" -printf '%y %10s %p\n' | sort -k3
echo "=== final tree: replicad ==="
find "$RA" -printf '%y %10s %p\n' | sort -k3
