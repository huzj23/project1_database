#!/usr/bin/env bash
# ===========================================================================
# Verify all 4 red-wood turntable clips: disc is dark_wood (not grey), camera is the
# pulled-back k=1.5 pose, and the physics is unchanged from the approved run.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== all 4 clips: metadata + disc colour measured from delivered frames ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -24
import glob, json, math
import numpy as np
from PIL import Image
R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
OLD = "/data/raw/huzijian/project1_database/tmp/tt_grey_near_camera"
JOBS = [("turntable_carry", 5001), ("turntable_carry", 5002),
        ("turntable_spin", 5001), ("turntable_spin", 5002)]

def disc(d):
    ss = sorted(glob.glob(d + "/segmentation/*.png")); fs = sorted(glob.glob(d + "/rgb/*.png"))
    if not ss or not fs: return None
    acc = []
    for i in (0, 20, 40, 60, 80):
        img = np.asarray(Image.open(fs[i]).convert("RGB"), dtype=np.float32)
        s = np.asarray(Image.open(ss[i]))
        if s.ndim == 3: s = s[..., 0]
        lab = [int(L) for L in np.unique(s) if L != 0]
        if not lab: continue
        L = max(lab, key=lambda l: (s == l).sum()); m = (s == L); px = img[m]
        r,g,b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
        ys,xs = np.nonzero(m)
        acc.append((100*m.mean(), xs.max()-xs.min(), r/max(b,1e-6), r/max(g,1e-6)))
    return np.array(acc).mean(axis=0) if acc else None

print(f"  {'clip':26s} {'area%':>6s} {'w':>5s} {'R/B':>5s} {'R/G':>5s} | {'old R/B':>8s} {'valid':>6s} {'cam':>26s}")
for scen, seed in JOBS:
    d = f"{R}/datasets/{scen}/seed-{seed:06d}/x1"
    m = json.load(open(d + "/metadata.json"))
    pos = m["render"]["camera_position"]
    a = disc(d)
    o = disc(f"{OLD}/{scen}-seed-{seed:06d}/x1")
    name = f"{scen}/{seed}"
    print(f"  {name:26s} {a[0]:6.1f} {a[1]:5.0f} {a[2]:5.2f} {a[3]:5.2f} | "
          f"{(o[2] if o is not None else float('nan')):8.2f} "
          f"{str(m['validation']['valid']):>6s} "
          f"({pos[0]:.3f},{pos[1]:.3f},{pos[2]:.3f})")
    dm = m["render"].get("declared_materials", {})
    so = dm.get("support_object", {})
    print(f"      pbr={so.get('pbr')} uv={so.get('uv_scale')} "
          f"maps={sorted((so.get('maps') or {}).keys())} "
          f"lighting={m['render'].get('environment_lighting_source')}")
PY

echo
echo "=== video specs ==="
for f in $(find datasets/turntable_* -name 'video.mp4' | sort); do
  printf "  %-46s %s\n" "$f" "$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames -of csv=p=0 $f 2>/dev/null)"
done
