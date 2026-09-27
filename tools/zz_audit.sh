#!/usr/bin/env bash
R=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main
cd "$R" || exit 1

echo "=== mtimes: preflight log vs the files it validates ==="
stat -c '%y  %n' /data/raw/huzijian/project1_database/tmp/zz_preflight_final.log \
  assets/objects/special_plush_elephant/asset.yaml \
  assets/objects/special_plush_elephant/collision/model.obj \
  assets/environments/replicad_apartment/asset.yaml \
  configs/scenarios/turntable_carry_gso.yaml \
  configs/scenarios/turntable_spin_gso.yaml

echo
echo "=== stray backups: elephant + replicad must be ABSENT ==="
for f in assets/objects/special_plush_elephant/asset.yaml.t3dev-bak \
         assets/environments/replicad_apartment/asset.yaml.t3dev-bak \
         assets/environments/replicad_apartment/visual/scene.blend1 \
         assets/environments/replicad_apartment/visual/scene.glb; do
  if [ -e "$f" ]; then echo "  STILL PRESENT: $f"; else echo "  gone: $f"; fi
done

echo
echo "=== remaining t3dev-bak files (belong to OTHER assets, out of scope) ==="
find assets -name '*.t3dev-bak' | sed 's/^/  /'

echo
echo "=== old id outside datasets/ : LIVE configs and assets only ==="
echo "-- in configs/ (live .yaml only, excluding .pre_* backups) --"
grep -rn 'gso_sootheze_cold_therapy_elephant' configs --include='*.yaml' 2>/dev/null | sed 's/^/  /' || echo "  (none)"
echo "-- in assets/ --"
grep -rn 'gso_sootheze_cold_therapy_elephant' assets 2>/dev/null | sed 's/^/  /' || echo "  (none)"
echo "-- in src/ scripts/ tests/ docs/ --"
grep -rn 'gso_sootheze_cold_therapy_elephant' src scripts tests docs 2>/dev/null | sed 's/^/  /' || echo "  (none)"
echo "-- in configs/ .pre_* historical backups (NOT loaded by the pipeline) --"
grep -rln 'gso_sootheze_cold_therapy_elephant' configs 2>/dev/null | sed 's/^/  /'

echo
echo "=== elephant + replicad final trees ==="
find assets/objects/special_plush_elephant assets/environments/replicad_apartment \
  -printf '%y %10s %p\n' | sort -k3
