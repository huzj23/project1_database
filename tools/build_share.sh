#!/usr/bin/env bash
# ===========================================================================
# Build the SHARE FOLDER on the server: videos + physics annotations + contact
# sheets, organised by motion, then report the exact archive size.
#
# Budget: 50 MB.  Measured raw content: 17.2 MB of mp4 + 23.5 MB of json = ~40.7 MB,
# which is too close to the cap once the README and contact sheets are added, so the
# bulky per-frame `collisions.json` files are the thing to watch.  This script
# measures first, then decides, rather than guessing.
#
# Motion mapping (seeds were assigned per motion in the V3.4 plan):
#   #1 rolling          seed 001001                (camera C, whey can rolling)
#   #2 constant_force   002001/2/3
#   #3 free_fall        003001/2/3   (h_speed 0.03-0.10)
#   #4 projectile       004001/2/3   (h_speed 0.30-0.40)
#   #5 turntable_carry  005001/005002
#   #6 turntable_spin   005001/005002  <-- NOTE: same seed numbers as carry!
#   #7 damping          007001/007002
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
SHARE="$WS/share_build"
rm -rf "$SHARE"
mkdir -p "$SHARE"

echo "=== copy videos + annotations ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import glob, json, os, shutil
REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
SHARE = "/data/raw/huzijian/project1_database/share_build"

MOTIONS = [
    ("01_uniform_rolling",       [("rolling", "001001", "uniform_rolling")]),
    ("02_constant_acceleration", [("constant_force", f"00200{i}", f"constant_acceleration_{i}") for i in (1,2,3)]),
    ("03_free_fall",             [("free_fall", f"00300{i}", f"free_fall_{i}") for i in (1,2,3)]),
    ("04_projectile",            [("free_fall", f"00400{i}", f"projectile_{i}") for i in (1,2,3)]),
    ("05_circular_orbit",        [("turntable_carry", f"00500{i}", f"circular_orbit_{i}") for i in (1,2)]),
    ("06_turntable_spin",        [("turntable_spin", f"00500{i}", f"turntable_spin_{i}") for i in (1,2)]),
    ("07_damping",               [("damping", f"00700{i}", f"damping_{i}") for i in (1,2)]),
]
ANNOT = ("trajectory.json", "support_trajectory.json", "collisions.json",
         "metadata.json", "config.yaml")

n_v = n_a = 0
tot = 0
for folder, items in MOTIONS:
    vd = os.path.join(SHARE, "videos", folder)
    ad = os.path.join(SHARE, "annotations", folder)
    os.makedirs(vd, exist_ok=True)
    for scen, seed, name in items:
        src = f"{REPO}/datasets/{scen}/seed-{seed}/x1"
        if not os.path.isdir(src):
            print(f"  MISSING {scen}/seed-{seed}"); continue
        mp4 = os.path.join(src, "video.mp4")
        if os.path.isfile(mp4):
            shutil.copy2(mp4, os.path.join(vd, f"{name}.mp4"))
            n_v += 1; tot += os.path.getsize(mp4)
        # annotations: one subdir per video
        dst = os.path.join(ad, name)
        os.makedirs(dst, exist_ok=True)
        for f in ANNOT:
            p = os.path.join(src, f)
            if os.path.isfile(p):
                shutil.copy2(p, os.path.join(dst, f))
                tot += os.path.getsize(p); n_a += 1
print(f"  videos={n_v}  annotation files={n_a}  running total={tot/1e6:.2f} MB")
PY

echo
echo "=== sizes by part ==="
du -sh "$SHARE/videos" "$SHARE/annotations" 2>/dev/null | sed 's/^/  /'
echo "  --- biggest annotation files ---"
find "$SHARE/annotations" -type f -printf '%s %p\n' 2>/dev/null | sort -rn | head -8 | \
  awk '{printf "    %7.1f KB  %s\n", $1/1024, $2}'

echo
echo "=== contact sheets ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import glob, os
import numpy as np
from PIL import Image
REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
SHARE = "/data/raw/huzijian/project1_database/share_build"
MOTIONS = [
    ("01_uniform_rolling",       [("rolling", "001001", "uniform_rolling")]),
    ("02_constant_acceleration", [("constant_force", f"00200{i}", f"constant_acceleration_{i}") for i in (1,2,3)]),
    ("03_free_fall",             [("free_fall", f"00300{i}", f"free_fall_{i}") for i in (1,2,3)]),
    ("04_projectile",            [("free_fall", f"00400{i}", f"projectile_{i}") for i in (1,2,3)]),
    ("05_circular_orbit",        [("turntable_carry", f"00500{i}", f"circular_orbit_{i}") for i in (1,2)]),
    ("06_turntable_spin",        [("turntable_spin", f"00500{i}", f"turntable_spin_{i}") for i in (1,2)]),
    ("07_damping",               [("damping", f"00700{i}", f"damping_{i}") for i in (1,2)]),
]
out = os.path.join(SHARE, "contact_sheets")
os.makedirs(out, exist_ok=True)
w, h = 480, 270
for folder, items in MOTIONS:
    for scen, seed, name in items:
        fs = sorted(glob.glob(f"{REPO}/datasets/{scen}/seed-{seed}/x1/rgb/*.png"))
        if not fs: continue
        idx = [0, 10, 20, 30, 40, 50, 60, 80]
        sheet = Image.new("RGB", (w*4, h*2), (20,20,20))
        for k, i in enumerate(idx):
            if i < len(fs):
                sheet.paste(Image.open(fs[i]).convert("RGB").resize((w,h)), ((k%4)*w, (k//4)*h))
        sheet.save(os.path.join(out, f"{name}.png"))
print(f"  wrote {len(os.listdir(out))} contact sheets")
PY

echo
echo "=== FINAL share_build size ==="
du -sh "$SHARE" | sed 's/^/  /'
du -sh "$SHARE"/* | sed 's/^/  /'
