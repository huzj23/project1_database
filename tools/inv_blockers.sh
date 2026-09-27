#!/usr/bin/env bash
# Two last blockers for tonight's plan:
#  A) the spheres' asset.yaml references visual/model.glb but no visual/ dir exists
#     -> is there ANY ball-like object with a real visual?
#  B) can we export Stage_v3_sc0..sc3 as environments (they are GLBs, not blends)?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== A) any ball/sphere visual anywhere on the server? ==="
find "$WS" \( -iname '*.glb' -o -iname '*.obj' \) 2>/dev/null \
  | grep -iE 'ball|sphere|basket|foot|volley|base' | head -20 | sed "s|$WS/|  |"
echo "  --- kubasic (synthetic primitives - BANNED by iron rule 2) ---"
ls -1 "$WS/models/kubasic" 2>/dev/null | head -8 | sed 's/^/    /'
echo "  --- phyco_sim_objs ---"
ls -1 "$WS/models/phyco_sim_objs" 2>/dev/null | head -12 | sed 's/^/    /'

echo
echo "=== B) Stage GLB sizes (can we export them as scenes?) ==="
for s in "$WS/models/backgrounds/replicad/stages"/*.glb; do
  printf "  %7.1f MB  %s\n" "$(echo "scale=1; $(stat -c%s "$s")/1048576" | bc)" "$(basename "$s")"
done

echo
echo "=== existing export tool (how we built replicad_apartment) ==="
head -40 "$WS/tools/export_blend_joined.sh" 2>/dev/null | sed 's/^/  /'

echo
echo "=== does the export tool take a stage name? ==="
grep -n 'STAGE\|SCENE\|for \|usage\|Usage' "$WS/tools/export_blend_joined.sh" 2>/dev/null | head -20 | sed 's/^/  /'
