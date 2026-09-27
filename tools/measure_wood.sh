#!/usr/bin/env bash
# ===========================================================================
# (a) MEASURE the completed red-wood clip's disc pixels -- this is the whole point
#     of the re-render: disc must no longer be grey (R/B 0.99) but dark_wood
#     (R/B ~1.98).  Measured from the REAL delivered video, not a probe.
# (b) Confirm the pulled-back camera actually took effect (k=1.5, disc 13.8%).
# (c) Restore configs/server.yaml's scenario_config, which MY runner clobbered with
#     sed.  Find its original value from git if available.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== red-wood clip #1 (turntable_carry seed-005001) measured from delivered frames ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -22
import glob, json
import numpy as np
from PIL import Image
R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
new = f"{R}/datasets/turntable_carry/seed-005001/x1"
old = "/data/raw/huzijian/project1_database/tmp/tt_grey_near_camera/turntable_carry-seed-005001/x1"
m = json.load(open(new + "/metadata.json"))
pos = m["render"]["camera_position"]
print(f"  camera_position = {[round(v,4) for v in pos]}")
print(f"  expected k=1.5  = [1.194, -0.815, 1.3634]")
print(f"  framing mode    = {m.get('camera',{}).get('framing',{}).get('mode')}")
print(f"  valid           = {m['validation']['valid']}  reasons={m['validation']['reasons']}")
print(f"  lighting        = {m['render'].get('environment_lighting_source')} "
      f"count={m['render'].get('environment_light_count')}")
dm = m["render"].get("declared_materials") or m.get("declared_materials")
print(f"  declared_materials = {dm}")

def disc_stats(d, tag):
    ss = sorted(glob.glob(d + "/segmentation/*.png"))
    fs = sorted(glob.glob(d + "/rgb/*.png"))
    if not ss or not fs:
        print(f"  {tag}: no frames"); return
    acc = []
    for i in (0, 20, 40, 60, 80):
        img = np.asarray(Image.open(fs[i]).convert("RGB"), dtype=np.float32)
        s = np.asarray(Image.open(ss[i]))
        if s.ndim == 3: s = s[..., 0]
        lab = [int(L) for L in np.unique(s) if L != 0]
        if not lab: continue
        L = max(lab, key=lambda l: (s == l).sum())
        msk = (s == L); px = img[msk]
        r,g,b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
        ys,xs = np.nonzero(msk)
        acc.append((100*msk.mean(), xs.max()-xs.min(), r/max(b,1e-6), r/max(g,1e-6),
                    float(np.abs(px[:,0]-px[:,2]).mean())))
    if not acc: print(f"  {tag}: nothing"); return
    a = np.array(acc).mean(axis=0)
    print(f"  {tag:26s} L{L} area={a[0]:5.1f}% w={a[1]:4.0f}px "
          f"R/B={a[2]:5.2f} R/G={a[3]:5.2f} chroma={a[4]:5.1f}")

disc_stats(new, "NEW (red wood, k1.5)")
disc_stats(old, "OLD (grey, near cam)")
print("  target frozen dark_wood: R/B 1.99  R/G 1.67   |  grey was R/B 0.99 R/G 0.99")
PY

echo
echo "=== restore configs/server.yaml (git original, if available) ==="
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  echo "  git repo present"
  git -C "$REPO" show HEAD:configs/server.yaml 2>/dev/null | grep -n 'scenario_config' | sed 's/^/    HEAD: /'
  git -C "$REPO" status --porcelain configs/server.yaml | sed 's/^/    status: /'
else
  echo "  no git repo; will restore explicitly"
fi
