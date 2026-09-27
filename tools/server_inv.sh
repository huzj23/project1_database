#!/usr/bin/env bash
# ===========================================================================
# (a) Which asset/camera did the other rolling clips use?
#     The user said "最多再跑一条匀速" (at most ONE more 匀速 clip) and rejected the
#     frictionless-sliding actor, so the extra rolling clips may need to be dropped
#     from the deliverable rather than shared.
# (b) Dump the SERVER's file inventory (path + md5) for src/ and configs/ so the
#     upstream diff can be redone against the tree that actually produced the
#     videos, instead of the stale local checkout the V3.7 subagent used.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== rolling clips: asset, camera, physics ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import glob, json, os
REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
for d in sorted(glob.glob(REPO + "/datasets/rolling/seed-*/x1")):
    m = os.path.join(d, "metadata.json")
    if not os.path.isfile(m):
        print(f"  {d}: no metadata"); continue
    j = json.load(open(m))
    pos = j["render"].get("camera_position")
    mode = j.get("camera", {}).get("framing", {}).get("mode")
    ph = j.get("physics", {})
    print(f"  {d.replace(REPO+'/datasets/',''):26s} asset={j['asset'].get('asset_id')}")
    print(f"      camera={[round(v,3) for v in pos] if pos else None} mode={mode}")
    print(f"      friction={ph.get('friction')} rolling_friction={ph.get('rolling_friction')}")
PY

echo
echo "=== free_fall 009000/009100: what are they? ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import json, os
REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
for s in ("009000", "009100"):
    d = f"{REPO}/datasets/free_fall/seed-{s}/x1"
    m = os.path.join(d, "metadata.json")
    if not os.path.isfile(m):
        print(f"  seed-{s}: no metadata"); continue
    j = json.load(open(m))
    print(f"  seed-{s}: scenario={j.get('scenario')} asset={j['asset'].get('asset_id')} "
          f"frames={j.get('frame_count')} sample_id={j.get('sample_id')}")
PY

echo
echo "=== SERVER inventory dump (src + configs + scripts) ==="
OUT="$WS/tmp/server_inventory.txt"
: > "$OUT"
for base in src configs scripts assets/objects/turntable; do
  find "$base" -type f \( -name '*.py' -o -name '*.yaml' -o -name '*.yml' -o -name '*.obj' \
       -o -name '*.urdf' -o -name '*.mtl' \) 2>/dev/null | grep -v __pycache__ | sort | while read -r f; do
    printf "%s  %s\n" "$(md5sum "$f" | awk '{print $1}')" "$f" >> "$OUT"
  done
done
wc -l "$OUT" | sed 's/^/  lines: /'
head -5 "$OUT" | sed 's/^/  /'
echo "  written to $OUT"
