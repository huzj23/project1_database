#!/usr/bin/env bash
# Test ONE rolling run with the friction fix, then report the metrics.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

sed -i 's|^  scenario_config: .*|  scenario_config: configs/scenarios/rolling_gso.yaml|' configs/server.yaml
rm -rf datasets/rolling/seed-1001

"$WS/tools/conda_env/bin/python" scripts/generate.py --config configs/server.yaml \
    --seed 1001 --variant x1 --asset-id gso_whey_protein_vanilla \
    > "$WS/tmp/one.log" 2>&1
echo "rc=$?"

if [ -f datasets/rolling/seed-1001/x1/metadata.json ]; then
  "$WS/tools/conda_env/bin/python" - <<'PY'
import json
d = "datasets/rolling/seed-1001/x1"
m = json.load(open(d + "/metadata.json"))
v = m["validation"]
print("  valid   =", v["valid"])
print("  reasons =", v["reasons"])
mt = v["metrics"]
for k in ("travel_distance", "supported_fraction", "max_speed_relative_change",
          "max_linear_speed", "trajectory_extent_object_ratio"):
    print(f"  {k} = {mt.get(k)}")
tr = json.load(open(d + "/trajectory.json"))["trajectory"]
print(f"  frames  = {len(tr)}")
p0, p1 = tr[0]["position"], tr[-1]["position"]
print(f"  start   = {[round(x,4) for x in p0]}")
print(f"  end     = {[round(x,4) for x in p1]}")
PY
else
  echo "  no metadata; last error:"
  grep -E 'Error|RuntimeError|reasons=' "$WS/tmp/one.log" | tail -4 | sed 's/^/    /'
fi
