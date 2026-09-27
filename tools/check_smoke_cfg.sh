#!/usr/bin/env bash
# The smoke run produced 81 rgb frames but no depth/segmentation and no
# trajectory.json.  Read back the SAVED config next to the output (his pipeline
# writes config.yaml per sample) to see what it actually ran with.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x1"

echo "=== everything in the sample dir ==="
find "$D" -type f | sed "s#$D/#  #" | head -20
echo "  (dirs:)"
find "$D" -type d | sed "s#$D/#  #"

echo
echo "=== saved config.yaml: output + render sections ==="
"$WS/tools/conda_env/bin/python" - "$D" <<'PY'
import sys, os, yaml
D = sys.argv[1]
p = os.path.join(D, "config.yaml")
if not os.path.isfile(p):
    print("  no config.yaml saved")
    raise SystemExit
c = yaml.safe_load(open(p))
print("  output:", c.get("output"))
print("  render:", {k: c["render"].get(k) for k in
                   ("samples_per_pixel", "device", "write_video")})
print("  scenario:", c.get("scenario"))
print("  selection:", c.get("selection"))
PY

echo
echo "=== what the writer actually emitted ==="
"$WS/tools/conda_env/bin/python" - "$D" <<'PY'
import sys, os, json
D = sys.argv[1]
for name in ("metadata.json", "trajectory.json", "collisions.json", "video.mp4"):
    p = os.path.join(D, name)
    print(f"  {name:<18} {'present  ' + str(os.path.getsize(p)) + ' B' if os.path.isfile(p) else 'MISSING'}")
m = os.path.join(D, "metadata.json")
if os.path.isfile(m):
    md = json.load(open(m))
    print("  metadata keys:", list(md)[:14])
    for k in ("validation", "validation_report", "modalities", "outputs"):
        if k in md:
            print(f"    {k}: {json.dumps(md[k])[:220]}")
PY
