#!/usr/bin/env bash
# ===========================================================================
# Find the BICYCLE the user dislikes.
#
# The environment was joined into ONE mesh (`frl_apt_stage`) for rendering, so the
# object names are gone from the .blend.  But the ReplicaCAD source config still
# lists every instance with its template name and translation, so the bicycle's
# world position can be recovered exactly from there.
#
# Note: the stage import applies a coordinate swap (x, -z, y) -- see
# tools/tt_on_table.sh lines 69-71 -- so translations must be mapped the same way.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== ReplicaCAD source configs available ==="
ls -la "$WS/models/backgrounds/replicad/configs/scenes/" 2>/dev/null | head -12 | sed 's/^/  /'

echo
echo "=== find bicycle-like templates across the scene configs ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -40
import glob, json, os
base = "/data/raw/huzijian/project1_database/models/backgrounds/replicad"
cfgs = sorted(glob.glob(base + "/configs/scenes/*.json"))
print(f"  scene configs: {len(cfgs)}")
KEYS = ("bike", "bicycle", "cycle", "velo", "wheel")
for c in cfgs:
    try:
        d = json.load(open(c))
    except Exception as e:
        print(f"  {os.path.basename(c)}: {e}"); continue
    insts = d.get("object_instances", [])
    hits = [i for i in insts
            if any(k in str(i.get("template_name","")).lower() for k in KEYS)]
    if hits:
        print(f"  {os.path.basename(c)}: {len(insts)} instances, {len(hits)} bicycle-like")
        for h in hits:
            print(f"      template={h.get('template_name')} "
                  f"translation={h.get('translation')} "
                  f"rotation={h.get('rotation')}")
PY

echo
echo "=== which scene config does the asset actually use? ==="
cat assets/environments/replicad_apartment/asset.yaml 2>/dev/null | sed 's/^/  /'
grep -rn 'scene_instance\|apt_0\|stage' assets/environments/replicad_apartment/asset.yaml 2>/dev/null | sed 's/^/  /'

echo
echo "=== all object template names in apt_0 (to see what furniture exists) ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -30
import json, collections
p = "/data/raw/huzijian/project1_database/models/backgrounds/replicad/configs/scenes/apt_0.scene_instance.json"
d = json.load(open(p))
insts = d.get("object_instances", [])
print(f"  instances: {len(insts)}")
for i in insts:
    t = str(i.get("template_name","")).split("/")[-1]
    print(f"    {t:44s} translation={i.get('translation')}")
PY
