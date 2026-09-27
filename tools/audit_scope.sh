#!/usr/bin/env bash
# ===========================================================================
# Q1: does the outdoor work touch anything the frozen indoor pipeline uses?
# Q2: does the indoor scene provide its own interactive floor?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS" || exit 1

echo "=== Q1a: is the mentor repo / pipeline under version control? ==="
for d in "$WS/code/physics-video-sim/physics-video-sim-main" "$WS/code/vendor/phyco-sim" "$WS"; do
  if [ -d "$d/.git" ]; then
    echo "  GIT REPO: $d"
  fi
done

echo
echo "=== Q1b: files modified in the last 2 days under code/ ==="
find "$WS/code" -type f \( -name '*.py' -o -name '*.yaml' -o -name '*.yml' \) \
     -newermt '2 days ago' 2>/dev/null | grep -v '__pycache__' | sed "s|$WS/|  |"

echo
echo "=== Q1c: the outdoor scripts -- do they reference indoor assets? ==="
for f in ground_shadowcatcher.sh plane_rows.sh plane_sink.sh ground_probe.sh \
         ground_size.sh outdoor_fix.sh outdoor_fix2.sh ground_seam.sh seam_locate.sh \
         hdri_horizon.sh render_outdoor.sh render_outdoor2.sh render_outdoor3.sh; do
  p="$WS/tools/$f"
  [ -f "$p" ] || continue
  indoor=$(grep -c -E 'replicad|frl_apartment|Stage_v3|scene\.blend' "$p" 2>/dev/null || echo 0)
  cfg=$(grep -c -E 'scenarios/free_fall|configs/maps|configs/server' "$p" 2>/dev/null || echo 0)
  echo "  $f  indoor_refs=$indoor  pipeline_config_refs=$cfg"
done

echo
echo "=== Q2a: indoor pipeline -- where does the object rest? ==="
echo "  maps.yaml support region for the apartment:"
grep -A4 -i 'replicad_apartment_floor_pinned' "$WS/code/physics-video-sim/physics-video-sim-main/configs/maps.yaml" 2>/dev/null | sed 's/^/    /'

echo
echo "=== Q2b: does the ReplicaCAD stage GLB contain a floor mesh with collision? ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, os
WS = "/data/raw/huzijian/project1_database"
p = os.path.join(WS, "models/backgrounds/replicad/stages/frl_apartment_stage.glb")
print("  stage glb exists:", os.path.isfile(p),
      f"({os.path.getsize(p)/1048576:.1f} MB)" if os.path.isfile(p) else "")
# ReplicaCAD ships .stage_config.json / semantic mesh lists; look for floor entries
cfgdir = os.path.join(WS, "models/backgrounds/replicad")
for cand in ("stages/frl_apartment_stage.stage_config.json",
             "configs/stages/frl_apartment_stage.stage_config.json"):
    q = os.path.join(cfgdir, cand)
    if os.path.isfile(q):
        d = json.load(open(q))
        print("  stage_config:", cand)
        for k, v in list(d.items())[:8]:
            print(f"    {k}: {str(v)[:110]}")
PY

echo
echo "=== Q2c: what the indoor environment manifest declares ==="
find "$WS/code/physics-video-sim/physics-video-sim-main/assets/environments" -name 'asset.yaml' 2>/dev/null | while read f; do
  echo "  --- ${f#$WS/} ---"
  sed 's/^/    /' "$f"
done
