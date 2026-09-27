#!/usr/bin/env bash
# Build the frame-corrected collision mesh for special_plush_elephant.
# 1. run the project generator exactly as specified -> scratch
# 2. apply the exact inverse Rx(-90) so the collision body shares the VISUAL's frame
# 3. verify against the visual's own AABB
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OBJ=assets/objects/special_plush_elephant
mkdir -p "$WS/tmp/zz_coll_final"

echo "=== [1/3] generator (raw output kept for comparison) ==="
"$BLENDER" --background --factory-startup --python scripts/generate_collision_mesh.py -- \
  --source "$OBJ/visual/model.obj" \
  --output "$WS/tmp/zz_coll_final/raw_model.obj" \
  --urdf-output "$WS/tmp/zz_coll_final/raw_model.urdf" \
  --target-faces 512 \
  --report "$WS/tmp/zz_coll_final/raw_report.json" > "$WS/tmp/zz_coll_final/gen.log" 2>&1
echo "  blender exit=$?"
grep -E 'COLLISION_REPORT' "$WS/tmp/zz_coll_final/gen.log" | head -1 | cut -c1-120
cat "$WS/tmp/zz_coll_final/raw_report.json"

echo
echo "=== [2/3] apply inverse Rx(-90) -> asset collision/ ==="
"$PY" "$WS/tools/zz_align_frame.py" \
  "$WS/tmp/zz_coll_final/raw_model.obj" \
  "$OBJ/collision/model.obj" \
  "$OBJ/collision/model.urdf" \
  "$WS/tmp/zz_coll_final/aligned_report.json"

echo
echo "=== [3/3] verify collision vs visual AABB (must match) ==="
"$PY" - <<'PY'
import numpy as np
REPO="/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
def aabb(p):
    lo=np.array([1e18]*3); hi=np.array([-1e18]*3); nv=nf=0
    for line in open(p,errors="ignore"):
        if line.startswith("v "):
            v=np.array([float(x) for x in line.split()[1:4]])
            lo=np.minimum(lo,v); hi=np.maximum(hi,v); nv+=1
        elif line.startswith("f "): nf+=1
    return lo,hi,nv,nf
for lbl,p in [("visual", f"{REPO}/assets/objects/special_plush_elephant/visual/model.obj"),
              ("collision(ALIGNED)", f"{REPO}/assets/objects/special_plush_elephant/collision/model.obj"),
              ("collision(RAW gen)", "/data/raw/huzijian/project1_database/tmp/zz_coll_final/raw_model.obj")]:
    lo,hi,nv,nf=aabb(p)
    r=max((v**2).sum()**0.5 for v in
          [np.array([float(x) for x in l.split()[1:4]]) for l in open(p,errors="ignore") if l.startswith("v ")])
    print(f"  {lbl:20s} nv={nv:5d} nf={nf:5d} dims={np.round(hi-lo,6).tolist()} "
          f"support={-lo[2]:.6f} brad={r:.6f}")
PY
