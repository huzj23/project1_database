#!/usr/bin/env bash
# Inventory every rendered sample: which motions are complete, which are missing.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== render status ==="
echo "  --- camC rolling (camera C) ---"
cat "$WS/tmp/camC_stdout.log" 2>/dev/null | tr -d '\r' | tail -8 | sed 's/^/    /'
echo "  running: $(pgrep -af 'scripts/generate.py' | grep -v 'bash -c' | head -1)"

echo
echo "=== ALL completed samples ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import glob, json, os
REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
rows = []
for d in sorted(glob.glob(REPO + "/datasets/*/seed-*/x1")):
    n = len(glob.glob(d + "/rgb/*.png"))
    if n == 0:
        continue
    mp4 = os.path.isfile(d + "/video.mp4")
    meta = os.path.join(d, "metadata.json")
    verdict, cam = "NO-META", ""
    if os.path.isfile(meta):
        m = json.load(open(meta))
        v = m.get("validation", {})
        verdict = "PASS" if v.get("valid") else f"FAIL {list(v.get('reasons', []))}"
        pos = m.get("render", {}).get("camera_position")
        cam = f"({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f})" if pos else "?"
    rel = d.replace(REPO + "/datasets/", "")
    rows.append((rel, n, mp4, verdict, cam))
print(f"  {'sample':40s} {'rgb':>4s} {'mp4':>4s} {'cam':>22s}  verdict")
for rel, n, mp4, verdict, cam in rows:
    print(f"  {rel:40s} {n:4d} {str(mp4):>4s} {cam:>22s}  {verdict}")
print(f"\n  total samples: {len(rows)}")
PY

echo
echo "=== which motion configs exist ==="
ls configs/scenarios/*.yaml | sed 's/^/  /'
