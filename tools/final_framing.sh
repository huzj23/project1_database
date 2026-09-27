#!/usr/bin/env bash
# Final framing adjustment.
#
# The trajectory needs a 3.49 m stand-off but the cap was 3.10 m.  Raising the cap
# alone is risky because the camera policy samples `side: random`, and one side of
# this corridor (x = 2.70 + 3.5 = 6.2) falls OUTSIDE the room (which ends at
# x = 4.58).  Pin the side so the lens always stays indoors, then re-run.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml
repo = pathlib.Path(sys.argv[1])
p = repo / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()
t = re.sub(r"max_distance:\s*[0-9.]+", "max_distance: 4.00", t)
t = re.sub(r"(\n\s*side:\s*)\w+", r"\g<1>left", t)
p.write_text(t)
c = yaml.safe_load(open(p))
print("  camera side :", c["camera"].get("side"))
print("  max_distance:", c["camera"]["framing"].get("max_distance"))
print("  policy      :", c["camera"].get("policy"))
PY

echo
echo "=== run ==="
bash "$WS/tools/p1_smoke_final.sh" 2>&1 | tail -30
