#!/usr/bin/env bash
# ===========================================================================
# User decision: camera C (az270_d2.2) for the 匀速 clip, and NO close-up.
#
# I flagged C as "bicycle in frame", so before spending 20 minutes I want the REAL
# screen footprint of the bicycle in C, not just an in/out boolean.  The bicycle is
# part of the joined `environment` mesh so it has no per-object id at render time,
# but its GLB gives exact bounds -- project all 8 corners and measure coverage.
#
# Also: report T3 progress and machine load (a second Cycles render contends).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== T3 status ==="
cat "$WS/tmp/t3_final_stdout.log" 2>/dev/null | tr -d '\r' | sed 's/^/  /'
echo "  running: $(pgrep -af generate.py | head -1)"
echo "  load: $(cut -d' ' -f1-3 /proc/loadavg)"

echo
echo "=== bicycle GLB bounds ==="
ls -la "$WS/models/backgrounds/replicad/objects/" 2>/dev/null | grep -i bike | sed 's/^/  /'

echo
echo "=== project the bicycle into camera C ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -30
import json, math, os, glob
import numpy as np
try:
    import trimesh
except Exception as e:
    print("  trimesh unavailable:", e); raise SystemExit

base = "/data/raw/huzijian/project1_database/models/backgrounds/replicad"
# find the bike glb
cands = glob.glob(base + "/objects/*bike*") + glob.glob(base + "/**/*bike*", recursive=True)
cands = [c for c in cands if c.lower().endswith((".glb", ".obj"))]
print("  candidate files:", [os.path.basename(c) for c in cands][:6])

# camera C
POS = np.array([-0.6744, -3.1931, 0.6127])
LOOK = np.array([-0.6744, -0.9931, 0.1027])
FOCAL, SW, SH = 50.0, 36.0, 36.0*1080/1920
fwd = LOOK-POS; fwd /= np.linalg.norm(fwd)
right = np.cross(fwd, np.array([0,0,1.0])); right /= np.linalg.norm(right)
up = np.cross(right, fwd)
fov_h = 2*math.atan(SW/(2*FOCAL)); fov_v = 2*math.atan(SH/(2*FOCAL))

def project(pt):
    v = np.asarray(pt) - POS
    z = float(v @ fwd)
    if z <= 0.05: return None
    return (math.atan2(float(v@right), z)/(fov_h/2),
            math.atan2(float(v@up), z)/(fov_v/2), z)

# bike instances from apt_0 (world = (x, -z, y))
insts = [i for i in json.load(open(base+"/configs/scenes/apt_0.scene_instance.json"))["object_instances"]
         if "bike" in str(i.get("template_name","")).lower()]
for inst in insts:
    t = str(inst["template_name"]).split("/")[-1]
    tr = inst["translation"]
    origin = np.array([float(tr[0]), -float(tr[2]), float(tr[1])])
    # bounds from the glb if available
    glb = None
    for c in cands:
        if t.split("_")[-1] in os.path.basename(c) or t in os.path.basename(c):
            glb = c; break
    if glb is None and cands:
        glb = cands[0]
    if glb:
        m = trimesh.load(glb, force="mesh")
        b = m.bounds
        print(f"  {t}: glb={os.path.basename(glb)} local bounds="
              f"{np.round(b[0],3).tolist()}..{np.round(b[1],3).tolist()}")
        lo, hi = b
    else:
        lo, hi = np.array([-0.9,-0.3,-0.6]), np.array([0.9,0.3,0.6])
        print(f"  {t}: no glb found, using a generic 1.8x0.6x1.2 m box")
    corners = [origin + np.array([x,y,z])
               for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]
    ns = [project(c) for c in corners]
    ns = [n for n in ns if n]
    if not ns:
        print(f"    -> entirely BEHIND the camera"); continue
    xs = [n[0] for n in ns]; ys = [n[1] for n in ns]
    inbox = (min(xs) < 1.0 and max(xs) > -1.0 and min(ys) < 1.0 and max(ys) > -1.0)
    # fraction of the frame the bbox spans (clipped to frame)
    cx0, cx1 = max(min(xs), -1.0), min(max(xs), 1.0)
    cy0, cy1 = max(min(ys), -1.0), min(max(ys), 1.0)
    cover = max(0.0, (cx1-cx0)/2.0) * max(0.0, (cy1-cy0)/2.0)
    print(f"    depth={min(n[2] for n in ns):.2f}..{max(n[2] for n in ns):.2f} m")
    print(f"    screen norm x[{min(xs):+.2f},{max(xs):+.2f}] y[{min(ys):+.2f},{max(ys):+.2f}]")
    print(f"    in frame={inbox}  bbox covers {cover*100:.1f}% of the image")
    print(f"    side: {'LEFT' if (min(xs)+max(xs))/2 < 0 else 'right'}")
PY
