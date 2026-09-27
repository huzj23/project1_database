#!/usr/bin/env bash
# ===========================================================================
# Is the elephant's VISUAL actually textured, and is the asset self-contained?
#
# The OBJ says `mtllib visual_geometry.mtl`, but the visual/ directory contains
# `model.mtl` -- a name mismatch.  If Blender cannot find the referenced MTL, the
# elephant renders with NO texture.  Determine:
#   A. the exact OBJ/MTL reference integrity in visual/
#   B. what scripts/prepare_visual_asset.py does (it produced visual/)
#   C. how Kubric loads a FileBasedObject OBJ (does it read the MTL at all?)
#   D. the reference mean colour of texture.png
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
E="assets/objects/special_plush_elephant"

echo "=== A. visual/ reference integrity ==="
ls -la "$E/visual/" | sed 's/^/  /'
echo "  OBJ mtllib/usemtl:"
grep -n 'mtllib\|usemtl' "$E/visual/model.obj" | head | sed 's/^/    /'
echo "  MTL map_Kd:"
grep -n 'map_Kd\|newmtl' "$E/visual/model.mtl" | sed 's/^/    /'
MTL=$(grep -m1 '^mtllib' "$E/visual/model.obj" | awk '{print $2}')
echo "  OBJ references MTL: '$MTL'"
if [ -f "$E/visual/$MTL" ]; then echo "    -> EXISTS"; else echo "    -> MISSING  <-- broken reference"; fi
echo "  files present in visual/: $(ls "$E/visual/" | tr '\n' ' ')"
echo "  source/ has the MTL the OBJ names? $(ls "$E/source/visual_geometry.mtl" 2>/dev/null && echo YES || echo NO)"

echo
echo "=== B. what does prepare_visual_asset.py do with the MTL? ==="
grep -n 'mtl\|MTL\|rename\|model\.obj\|visual_geometry' scripts/prepare_visual_asset.py | head -25 | sed 's/^/  /'

echo
echo "=== C. how does Kubric load a FileBasedObject? ==="
FB=$(find third_party/phyco-sim -name 'file_based_object.py' 2>/dev/null | head -1)
echo "  loader: $FB"
[ -n "$FB" ] && grep -n 'obj\|mtl\|material\|import_scene\|load' "$FB" | head -25 | sed 's/^/    /'

echo
echo "=== D. texture.png reference colour ==="
"$PY" - <<PY 2>&1 | sed 's/^/  /'
import numpy as np
from PIL import Image
im = Image.open("$E/visual/texture.png").convert("RGB")
a = np.asarray(im, dtype=np.float32) / 255.0
print("size:", im.size)
print("mean RGB :", np.round(a.reshape(-1,3).mean(axis=0), 4).tolist())
print("std  RGB :", np.round(a.reshape(-1,3).std(axis=0), 4).tolist())
print("R/B      :", round(float(a[...,0].mean()/max(a[...,2].mean(),1e-9)), 3))
PY

echo
echo "=== E. MEASURE the delivered frame inside the elephant's projected box ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import json, numpy as np
from PIL import Image
R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
S = f"{R}/datasets/turntable_spin/seed-005002/x1"
meta = json.load(open(f"{S}/metadata.json"))
cam = meta["camera"]
pos = np.array(cam["position"], float); look = np.array(cam["look_at"], float)
f = float(cam["focal_length_mm"]); sw = float(cam.get("sensor_width_mm", 36.0))
traj = json.load(open(f"{S}/trajectory.json"))
st = traj[0]
p = np.array(st["position"], float); q = st["quaternion"]
# quaternion (w,x,y,z) -> rotation matrix
w,x,y,z = q
Rm = np.array([
 [1-2*(y*y+z*z), 2*(x*y-z*w),   2*(x*z+y*w)],
 [2*(x*y+z*w),   1-2*(x*x+z*z), 2*(y*z-x*w)],
 [2*(x*z-y*w),   2*(y*z+x*w),   1-2*(x*x+y*y)]])
lo = np.array([-0.132393,-0.115208,-0.073659]); hi = np.array([0.135539,0.105461,0.133787])
corners = np.array([[a,b,c] for a in (lo[0],hi[0]) for b in (lo[1],hi[1]) for c in (lo[2],hi[2])])
world = (Rm @ corners.T).T + p
fwd = look-pos; fwd/=np.linalg.norm(fwd)
up0 = np.array([0,0,1.0])
right = np.cross(fwd, up0); right/=np.linalg.norm(right)
up = np.cross(right, fwd)
d = world - pos
zc = d@fwd; xc = d@right; yc = d@up
img = Image.open(f"{S}/rgb/rgb_00000.png").convert("RGB")
W,H = img.size
sh = sw*H/W
ndx = (xc/np.maximum(zc,1e-6))*f/(sw/2)
ndy = (yc/np.maximum(zc,1e-6))*f/(sh/2)
px = (ndx+1)/2*W; py = (1-ndy)/2*H
x0,x1 = int(max(px.min(),0)), int(min(px.max(),W-1))
y0,y1 = int(max(py.min(),0)), int(min(py.max(),H-1))
print(f"actor world pos   : {np.round(p,4).tolist()}")
print(f"projected box     : x[{x0},{x1}] y[{y0},{y1}]  ({x1-x0}x{y1-y0} px)")
a = np.asarray(img, dtype=np.float32)/255.0
crop = a[y0:y1+1, x0:x1+1].reshape(-1,3)
print(f"crop mean RGB     : {np.round(crop.mean(axis=0),4).tolist()}   R/B={crop[:,0].mean()/max(crop[:,2].mean(),1e-9):.3f}")
# centre 40% of the box is most likely pure actor
cy0 = y0 + int(0.3*(y1-y0)); cy1 = y1 - int(0.3*(y1-y0))
cx0 = x0 + int(0.3*(x1-x0)); cx1 = x1 - int(0.3*(x1-x0))
core = a[cy0:cy1+1, cx0:cx1+1].reshape(-1,3)
print(f"core mean RGB     : {np.round(core.mean(axis=0),4).tolist()}   R/B={core[:,0].mean()/max(core[:,2].mean(),1e-9):.3f}")
print(f"core std  RGB     : {np.round(core.std(axis=0),4).tolist()}")
PY
