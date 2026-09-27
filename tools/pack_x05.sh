#!/usr/bin/env bash
# Package the x0.5 free_fall sample for review.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
D="$WS/code/physics-video-sim/physics-video-sim-main/datasets/free_fall/seed-001000/x0.5"
OUT="$WS/outcomes/_P1_smoke"
rm -rf "$OUT"; mkdir -p "$OUT"
cp -f "$D/video.mp4" "$D/trajectory.json" "$D/collisions.json" \
      "$D/metadata.json" "$D/config.yaml" "$OUT/" 2>/dev/null

"$WS/tools/conda_env/bin/python" - "$D" "$OUT" <<'PY'
import json, os, shutil, sys
D, OUT = sys.argv[1], sys.argv[2]
md = json.load(open(os.path.join(D, "metadata.json")))
cam = (md.get("camera") or {}).get("position")
print(f"  camera      : {[round(v,2) for v in cam] if cam else None}")
print(f"  resolution  : {(md.get('render') or {}).get('resolution')}")
print(f"  frames      : {md.get('frame_count')}")
print(f"  validation  : {(md.get('validation') or {}).get('valid')}")

frames = sorted(f for f in os.listdir(os.path.join(D, "rgb")) if f.endswith(".png"))
n = len(frames)
picks = [0, n//8, n//4, n//2, 3*n//4, n-1]
for k, i in enumerate(picks):
    shutil.copy2(os.path.join(D, "rgb", frames[min(i, n-1)]),
                 os.path.join(OUT, f"f{k}_{frames[min(i,n-1)]}"))
print("  frames copied:", ", ".join(frames[min(i, n-1)] for i in picks))
PY

echo
ls "$OUT" | sed 's/^/  /'
echo "  total: $(du -sh "$OUT" | cut -f1)"
