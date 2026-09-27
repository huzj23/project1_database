#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
cd "$R" || exit 1

echo "=== old id OUTSIDE datasets/ (must be empty) ==="
grep -rn 'gso_sootheze_cold_therapy_elephant' . --exclude-dir=datasets 2>/dev/null || echo "  (none - good)"

echo
echo "=== new id references ==="
grep -rn 'special_plush_elephant' . --exclude-dir=datasets 2>/dev/null

echo
echo "=== old id INSIDE datasets/ (historical, must be preserved) ==="
echo -n "  file count: "
grep -rl 'gso_sootheze_cold_therapy_elephant' datasets 2>/dev/null | wc -l

echo
echo "=== non-live backup files NOT touched (contain old id) ==="
ls -la configs/scenarios/*.pre_eleph configs/scenarios/*.pre_pullback configs/scenarios/*.pre_camC 2>/dev/null

echo
echo "=== live scenario configs: asset_ids ==="
for f in configs/scenarios/turntable_carry_gso.yaml configs/scenarios/turntable_spin_gso.yaml; do
  echo "  $f:"
  sed -n '/^selection:/,/^timing:/p' "$f" | sed 's/^/    /'
done

echo
echo "=== HF tooling in place ==="
ls -la scripts/sync_hf_assets.py docs/HUGGINGFACE_DATASET_CARD.md

echo
echo "=== stray-file check (must be gone) ==="
find assets -name '*.t3dev-bak' -o -name '*.blend1' -o -name 'scene.glb' | sed 's/^/  /' || true
echo "  (empty above = clean)"
