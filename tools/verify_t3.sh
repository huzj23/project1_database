#!/usr/bin/env bash
# ===========================================================================
# Verify the first T3 clip by MEASUREMENT and export it for review.
#
# Rendering being "complete" is not evidence the clip is good.  Check:
#   1. 81 rgb + 81 depth(.tiff) + 81 segmentation + video at 1920x1080/81f
#   2. frames genuinely DIFFER (a static clip would still report 81 frames)
#   3. the ELEPHANT is actually visible and MOVING in the image, and the
#      approved camera is the one recorded in metadata
#   4. the disc's own rotation is present in support_trajectory.json
#   5. lighting is still the AUTHORED one (iron rule 4)
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/turntable_carry/seed-005001/x1"
OUT="$WS/outcomes/_t3"
mkdir -p "$OUT"

echo "=== counts ==="
for sub in rgb depth segmentation; do echo "  $sub: $(ls $D/$sub 2>/dev/null | wc -l)"; done
ls "$D"/*.mp4 "$D"/support_trajectory.json 2>/dev/null | sed 's/^/  /'

echo
echo "=== video probe ==="
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,r_frame_rate,duration \
  -of default=noprint_wrappers=1 "$D/video.mp4" 2>&1 | sed 's/^/  /'

echo
echo "=== frame uniqueness + elephant motion + camera + lighting ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, json, os
import numpy as np
from PIL import Image
D = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/turntable_carry/seed-005001/x1"

fs = sorted(glob.glob(D + "/rgb/*.png"))
print(f"  rgb frames: {len(fs)}")
import hashlib
h = {hashlib.md5(open(f,'rb').read()).hexdigest() for f in fs}
print(f"  unique frames: {len(h)}/{len(fs)}")

# background = temporal median (static camera)
stack = np.stack([np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) for f in fs[::8]])
bg = np.median(stack, axis=0)
print("  elephant detected + tracked (foreground vs static background):")
for i in (0, 20, 40, 60, 80):
    a = np.asarray(Image.open(fs[i]).convert("RGB"), dtype=np.float32)
    m = np.abs(a - bg).max(axis=2) > 25
    if m.sum() < 50:
        print(f"    f{i:03d}: NOT DETECTED"); continue
    ys, xs = np.nonzero(m)
    print(f"    f{i:03d}: px={int(m.sum()):6d} bbox x[{xs.min():4d},{xs.max():4d}] "
          f"y[{ys.min():4d},{ys.max():4d}] centre=({xs.mean():.0f},{ys.mean():.0f})")

meta = json.load(open(D + "/metadata.json"))
cam = meta["render"]
print(f"  camera position : {cam.get('camera_position')}")
print(f"  camera focal    : {cam.get('camera_focal_length_mm')}")
print(f"  lighting source : {cam.get('environment_lighting_source')}")
print(f"  authored lights : {cam.get('environment_light_count')} "
      f"types={cam.get('environment_light_types')}")
print(f"  supplemental    : {cam.get('supplemental_light_count', cam.get('area_light_count'))}")
print(f"  validation      : valid={meta['validation']['valid']} reasons={meta['validation']['reasons']}")

st = json.load(open(D + "/support_trajectory.json"))
rows = st if isinstance(st, list) else st.get("trajectory", st.get("support_trajectory"))
print(f"  support(disc) rows: {len(rows)}")
import math
q = [r["quaternion"] for r in rows]
def yaw(qq):
    w,x,y,z = qq
    return math.degrees(math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z)))
print(f"  disc yaw: {yaw(q[0]):.1f} -> {yaw(q[-1]):.1f} deg "
      f"(net {abs(yaw(q[-1])-yaw(q[0])):.1f})")
p = np.array([r["position"] for r in rows])
print(f"  disc position drift: {np.abs(p-p[0]).max():.6f} m (must be ~0: pinned axis)")
PY

echo
echo "=== export ==="
cp "$D/video.mp4" "$OUT/RING_clip.mp4"
"$WS/tools/conda_env/bin/python" - <<'PY'
import glob, os
import numpy as np
from PIL import Image
D = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/turntable_carry/seed-005001/x1/rgb"
OUT = "/data/raw/huzijian/project1_database/outcomes/_t3"
fs = sorted(glob.glob(D + "/*.png"))
idx = [0, 10, 20, 30, 40, 50, 60, 80]
w, h = 640, 360
sheet = Image.new("RGB", (w*4, h*2), (20,20,20))
for k, i in enumerate(idx):
    sheet.paste(Image.open(fs[i]).convert("RGB").resize((w,h)), ((k%4)*w, (k//4)*h))
sheet.save(os.path.join(OUT, "RING_CONTACT.png"))
print("  wrote RING_CONTACT.png frames", idx)
stack = np.stack([np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) for f in fs[::8]])
bg = np.median(stack, axis=0)
crops = []
for i in range(0, 81, 10):
    a = np.asarray(Image.open(fs[i]).convert("RGB"), dtype=np.float32)
    m = np.abs(a-bg).max(axis=2) > 25
    if m.sum() < 50: continue
    ys, xs = np.nonzero(m)
    cy, cx = int(ys.mean()), int(xs.mean())
    r = 170
    crops.append(Image.open(fs[i]).convert("RGB").crop(
        (max(0,cx-r), max(0,cy-r), min(1920,cx+r), min(1080,cy+r))).resize((240,240)))
if crops:
    strip = Image.new("RGB", (240*len(crops), 240), (20,20,20))
    for k, im in enumerate(crops): strip.paste(im, (k*240, 0))
    strip.save(os.path.join(OUT, "RING_MOTION.png"))
    print("  wrote RING_MOTION.png", len(crops), "crops")
PY
ls -la "$OUT" | sed 's/^/  /'
