#!/usr/bin/env bash
# ===========================================================================
# Verify ALL FOUR turntable clips and export them.
#
# T3 FINAL DONE: #5 carry 5001/5002 and #6 spin 5001/5002, all rc=0 rgb=81 PASS.
#
# Checks per clip (measurement, not assumption):
#   * 81 rgb + 81 depth + 81 segmentation + video.mp4 at 1920x1080 / 81 frames
#   * 81/81 unique frames (a frozen clip would still report 81 files)
#   * disc rotation UNWRAPPED from support_trajectory.json (a raw endpoint
#     difference wraps at +/-180 and under-reports a near-full turn as ~14 deg)
#   * actor arc swept + orbit radius (constant radius = a true circle, not a spiral)
#   * camera == the approved pose, and lighting still authored (iron rule 4)
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_t3"
mkdir -p "$OUT"

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -60
import glob, json, math, os, hashlib, subprocess
import numpy as np
from PIL import Image
REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
OUT = "/data/raw/huzijian/project1_database/outcomes/_t3"

def yaw_unwrapped(q):
    q = np.asarray(q, dtype=np.float64)
    raw = np.array([math.atan2(2.0*(w*z + x*y), 1.0 - 2.0*(y*y + z*z))
                    for w, x, y, z in q])
    return np.unwrap(raw)

CLIPS = [
    ("turntable_carry", "005001", "RING"),   # #5 环形转动
    ("turntable_carry", "005002", "RING2"),
    ("turntable_spin",  "005001", "SPIN"),   # #6 转盘上的转动
    ("turntable_spin",  "005002", "SPIN2"),
]
summary = []
for scen, seed, tag in CLIPS:
    D = f"{REPO}/datasets/{scen}/seed-{seed}/x1"
    if not os.path.isdir(D):
        print(f"{tag:6s} {scen}/seed-{seed}: MISSING"); continue
    n = {k: len(glob.glob(f"{D}/{k}/*")) for k in ("rgb", "depth", "segmentation")}
    mp4 = os.path.isfile(D + "/video.mp4")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,nb_frames,r_frame_rate", "-of", "csv=p=0",
         D + "/video.mp4"], capture_output=True, text=True).stdout.strip()
    fs = sorted(glob.glob(D + "/rgb/*.png"))
    uniq = len({hashlib.md5(open(f, "rb").read()).hexdigest() for f in fs}) if fs else 0

    meta = json.load(open(D + "/metadata.json"))
    R = meta["render"]; pos = R.get("camera_position")
    cam_ok = (pos is not None and abs(pos[0]-0.9340) < 1e-2
              and abs(pos[1]+0.4850) < 1e-2 and abs(pos[2]-1.1784) < 1e-2)
    light_ok = R.get("environment_lighting_source") == "source_blend"
    lights = f"{R.get('environment_light_count')}x{R.get('environment_light_types')}"

    st = json.load(open(D + "/support_trajectory.json"))
    srows = st if isinstance(st, list) else st.get("trajectory", st)
    q = [r["quaternion"] for r in srows]
    sp = np.array([r["position"] for r in srows])
    uw = yaw_unwrapped(q)
    disc_deg = math.degrees(uw[-1] - uw[0])
    disc_span = math.degrees(uw.max() - uw.min())
    disc_drift = float(np.abs(sp - sp[0]).max())

    tr = json.load(open(D + "/trajectory.json"))
    trows = tr if isinstance(tr, list) else tr.get("trajectory", tr)
    p = np.array([r["position"] for r in trows])
    cx, cy = sp[0, 0], sp[0, 1]
    r = np.hypot(p[:, 0]-cx, p[:, 1]-cy)
    ang = np.unwrap(np.arctan2(p[:, 1]-cy, p[:, 0]-cx))
    arc = math.degrees(ang[-1]-ang[0])

    v = meta.get("validation", {})
    print(f"\n=== {tag}  ({scen} seed-{seed}) ===")
    print(f"  rgb/depth/seg = {n['rgb']}/{n['depth']}/{n['segmentation']}   video={mp4}")
    print(f"  video probe   = {probe}")
    print(f"  unique frames = {uniq}/{len(fs)}")
    print(f"  DISC yaw unwrapped net = {disc_deg:+.2f} deg  span={disc_span:.2f}  "
          f"drift={disc_drift:.6f} m")
    print(f"  ACTOR arc = {arc:+.1f} deg   orbit r = {r.min():.4f}..{r.max():.4f} m")
    print(f"  actor z = {p[:,2].min():.5f}..{p[:,2].max():.5f}")
    print(f"  camera C-ok = {cam_ok}  pos={[round(x,4) for x in pos] if pos else None}")
    print(f"  lighting = {R.get('environment_lighting_source')} {lights} (authored={light_ok})")
    print(f"  valid = {v.get('valid')}  reasons={list(v.get('reasons', []))}")
    summary.append((tag, n['rgb'], uniq, disc_deg, arc, r.min(), r.max(),
                    cam_ok, light_ok, v.get('valid')))

    # export
    subprocess.run(["cp", D + "/video.mp4", f"{OUT}/{tag}_clip.mp4"], check=False)

print("\n=== SUMMARY ===")
print(f"{'tag':6s} {'rgb':>4s} {'uniq':>5s} {'disc_deg':>9s} {'arc':>7s} "
      f"{'r_min':>7s} {'r_max':>7s} {'cam':>5s} {'light':>6s} {'valid':>6s}")
for s in summary:
    print(f"{s[0]:6s} {s[1]:4d} {s[2]:5d} {s[3]:+9.2f} {s[4]:+7.1f} "
          f"{s[5]:7.4f} {s[6]:7.4f} {str(s[7]):>5s} {str(s[8]):>6s} {str(s[9]):>6s}")
PY

echo
echo "=== contact sheets ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -10
import glob, os
import numpy as np
from PIL import Image
REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
OUT = "/data/raw/huzijian/project1_database/outcomes/_t3"
for scen, seed, tag in (("turntable_carry","005001","RING"),
                        ("turntable_carry","005002","RING2"),
                        ("turntable_spin","005001","SPIN"),
                        ("turntable_spin","005002","SPIN2")):
    fs = sorted(glob.glob(f"{REPO}/datasets/{scen}/seed-{seed}/x1/rgb/*.png"))
    if not fs: continue
    idx = [0, 10, 20, 30, 40, 50, 60, 80]
    w, h = 480, 270
    sheet = Image.new("RGB", (w*4, h*2), (20,20,20))
    for k, i in enumerate(idx):
        sheet.paste(Image.open(fs[i]).convert("RGB").resize((w,h)), ((k%4)*w, (k//4)*h))
    p = f"{OUT}/{tag}_CONTACT.png"; sheet.save(p)
    print(f"  wrote {p}")
PY
ls -la "$OUT" | sed 's/^/  /'
