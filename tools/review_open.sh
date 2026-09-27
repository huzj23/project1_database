#!/usr/bin/env bash
# ===========================================================================
# Continue the review.  Four open items, each answered by measurement:
#   R1  segmentation layer -- was reported entirely black.  Still?
#   R2  motion-frame fraction -- the V3.0 acceptance gate is >= 50%.
#       Does the benchmark sample actually meet it?
#   R3  does the produced video actually MOVE?  (the stale-frame / keyframe trap)
#   R4  is the 2.89 m^2 support box a real limitation in practice?
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
S="$REPO/datasets/free_fall/seed-009000/x1"

"$WS/tools/conda_env/bin/python" - "$S" <<'PY' 2>&1 | sed 's/^/  /'
import sys, os, json, glob
import numpy as np
import cv2
S = sys.argv[1]

print("=== R1 segmentation layer ===")
segs = sorted(glob.glob(os.path.join(S, "segmentation", "*.png")))
print(f"  frames: {len(segs)}")
if segs:
    a = cv2.imread(segs[0], cv2.IMREAD_UNCHANGED)
    print(f"  shape={a.shape} dtype={a.dtype} min={a.min()} max={a.max()} unique={len(np.unique(a))}")
    for i in (0, len(segs)//2, len(segs)-1):
        b = cv2.imread(segs[i], cv2.IMREAD_UNCHANGED)
        u = np.unique(b)
        print(f"    frame {i}: unique={len(u)} values={u[:8].tolist()}")

print()
print("=== R3 does the video actually move? ===")
rgbs = sorted(glob.glob(os.path.join(S, "rgb", "*.png")))
print(f"  rgb frames: {len(rgbs)}")
if len(rgbs) > 1:
    base = cv2.imread(rgbs[0]).astype(np.int16)
    prev = base
    changed = []
    for f in rgbs[1:]:
        im = cv2.imread(f).astype(np.int16)
        d = int((np.abs(im - prev).max(axis=2) > 3).sum())
        changed.append(d)
        prev = im
    print(f"  per-frame changed px vs previous: {changed}")
    nz = sum(1 for c in changed if c > 500)
    print(f"  frames with real change: {nz}/{len(changed)}")
    # md5 check for identical frames
    import hashlib
    h = [hashlib.md5(open(f,'rb').read()).hexdigest()[:8] for f in rgbs]
    print(f"  distinct md5: {len(set(h))}/{len(h)}")

print()
print("=== R2 motion-frame fraction (V3.0 gate >= 50%) ===")
tj = json.load(open(os.path.join(S, "trajectory.json")))
tr = tj["trajectory"] if isinstance(tj, dict) else tj
zs = [float(s["position"][2]) for s in tr]
zmax, zmin = max(zs), min(zs)
print(f"  frames: {len(tr)}  z range: {zmin:.4f} .. {zmax:.4f}  span={zmax-zmin:.4f}")
# a frame "has motion" if the object moved since the previous frame
moved = 0
for i in range(1, len(tr)):
    p0 = np.array(tr[i-1]["position"], dtype=float)
    p1 = np.array(tr[i]["position"], dtype=float)
    if np.linalg.norm(p1 - p0) > 1e-4:
        moved += 1
print(f"  frames where the object moved: {moved}/{len(tr)-1} = {100*moved/max(len(tr)-1,1):.1f}%")
print(f"  ==> gate >=50%: {'PASS' if moved/max(len(tr)-1,1) >= 0.5 else 'FAIL'}")

print()
print("=== R4 support box actually used ===")
cfg = json.load(open(os.path.join(S, "metadata.json")))
print(f"  surface_id = {cfg.get('sample',{}).get('surface_id')}")
print(f"  position   = {cfg.get('sample',{}).get('position')}")
PY

echo
echo "=== R3b video.mp4 properties ==="
ffprobe -v error -show_entries stream=width,height,nb_frames,r_frame_rate,duration \
    -of default=noprint_wrappers=1 "$S/video.mp4" 2>/dev/null | sed 's/^/  /'
