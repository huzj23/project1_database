#!/usr/bin/env bash
# ===========================================================================
# Corrected verification for the turntable clip.
#
# TWO MEASUREMENT BUGS IN MY PREVIOUS CHECK:
# 1. Disc yaw: I took atan2 of the first and last quaternion and differenced them.
#    A 345 deg rotation wraps through +/-180, so the endpoints can differ by only
#    ~14 deg while the disc actually turned most of a circle.  Must UNWRAP the
#    sequence.
# 2. "Elephant detected": a temporal-median background mask also catches the
#    ROTATING DISC and its shadows, so it reported 377k pixels spanning the whole
#    frame -- that is the disc, not the actor.  The segmentation layer is the
#    authoritative per-pixel label, so use it: background=1, object=2 (the disc
#    and actor get their own ids).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/turntable_carry/seed-005001/x1"

echo "=== segmentation label inventory (who is who) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob
import numpy as np
from PIL import Image
D = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/turntable_carry/seed-005001/x1"
fs = sorted(glob.glob(D + "/segmentation/*.png"))
print(f"  seg frames: {len(fs)}  sample: {fs[0].split('/')[-1]}")
for i in (0, 40, 80):
    a = np.asarray(Image.open(fs[i]))
    if a.ndim == 3:
        a = a[..., 0]
    vals, cnts = np.unique(a, return_counts=True)
    top = sorted(zip(cnts.tolist(), vals.tolist()), reverse=True)[:6]
    print(f"  f{i:03d}: shape={a.shape} labels(top)=" +
          ", ".join(f"{v}:{c}" for c, v in top))
PY

echo
echo "=== disc yaw, UNWRAPPED from the quaternions ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, math
import numpy as np
D = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/turntable_carry/seed-005001/x1"
st = json.load(open(D + "/support_trajectory.json"))
rows = st if isinstance(st, list) else st.get("trajectory", st)
q = np.array([r["quaternion"] for r in rows], dtype=np.float64)
print(f"  rows={len(q)}  first q={np.round(q[0],5).tolist()}")
# quaternion is stored wxyz (Kubric convention)
def yaw_wxyz(qq):
    w, x, y, z = qq
    return math.atan2(2.0*(w*z + x*y), 1.0 - 2.0*(y*y + z*z))
raw = np.array([yaw_wxyz(r) for r in q])
unw = np.unwrap(raw)
print(f"  raw yaw first/last : {math.degrees(raw[0]):+8.2f} / {math.degrees(raw[-1]):+8.2f} deg")
print(f"  UNWRAPPED net      : {math.degrees(unw[-1]-unw[0]):+8.2f} deg")
print(f"  unwrapped span     : {math.degrees(unw.max()-unw.min()):8.2f} deg")
# total absolute path length: immune to wrap and to sign
d = np.diff(unw)
print(f"  total |travel|     : {math.degrees(np.abs(d).sum()):8.2f} deg")
print(f"  monotonic?         : {bool((d >= -1e-9).all() or (d <= 1e-9).all())}")
print("  per-frame yaw (every 10th, unwrapped deg):")
for i in range(0, len(unw), 10):
    print(f"    f{i:03d}: {math.degrees(unw[i]):+9.2f}")
PY

echo
echo "=== elephant track from the SEGMENTATION layer ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, json
import numpy as np
from PIL import Image
D = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/turntable_carry/seed-005001/x1"
fs = sorted(glob.glob(D + "/segmentation/*.png"))
# find the label that MOVES most across the clip -> that is the actor
a0 = np.asarray(Image.open(fs[0]));  a0 = a0[...,0] if a0.ndim==3 else a0
a1 = np.asarray(Image.open(fs[len(fs)//2])); a1 = a1[...,0] if a1.ndim==3 else a1
labels = [v for v in np.unique(a0).tolist() if v != 0]
print(f"  labels present: {labels}")
best = None
for L in labels:
    c0 = np.argwhere(a0 == L); c1 = np.argwhere(a1 == L)
    if len(c0) == 0 or len(c1) == 0: continue
    move = float(np.linalg.norm(c0.mean(axis=0) - c1.mean(axis=0)))
    print(f"    label {L}: px={len(c0):7d} centroid={np.round(c0.mean(axis=0),0)} "
          f"moved={move:7.1f} px")
    if best is None or move > best[1]: best = (L, move)
print(f"  -> actor label = {best[0]} (moves most)")

L = best[0]
print("  actor track over the clip:")
for i in range(0, len(fs), 10):
    a = np.asarray(Image.open(fs[i])); a = a[...,0] if a.ndim==3 else a
    c = np.argwhere(a == L)
    if len(c) == 0:
        print(f"    f{i:03d}: absent"); continue
    print(f"    f{i:03d}: px={len(c):6d} centroid=(y={c[:,0].mean():6.0f}, x={c[:,1].mean():6.0f})")
PY

echo
echo "=== the physics trajectory (authoritative) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, math
import numpy as np
D = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/turntable_carry/seed-005001/x1"
tr = json.load(open(D + "/trajectory.json"))
rows = tr if isinstance(tr, list) else tr.get("trajectory", tr)
p = np.array([r["position"] for r in rows])
st = json.load(open(D + "/support_trajectory.json"))
srows = st if isinstance(st, list) else st.get("trajectory", st)
sp = np.array([r["position"] for r in srows])
cx, cy = sp[0,0], sp[0,1]
ang = np.unwrap(np.arctan2(p[:,1]-cy, p[:,0]-cx))
print(f"  frames={len(p)}  disc axis=({cx:.4f},{cy:.4f})")
print(f"  orbit r: {np.hypot(p[:,0]-cx, p[:,1]-cy).min():.4f} .. "
      f"{np.hypot(p[:,0]-cx, p[:,1]-cy).max():.4f} m")
print(f"  actor angle swept (unwrapped): {math.degrees(ang[-1]-ang[0]):+.1f} deg")
print(f"  actor z: {p[:,2].min():.5f} .. {p[:,2].max():.5f}")
print(f"  first pos={np.round(p[0],4).tolist()}")
print(f"  last  pos={np.round(p[-1],4).tolist()}")
PY
