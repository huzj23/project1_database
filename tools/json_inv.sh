#!/usr/bin/env bash
# What JSON "physics annotation" files exist per sample, and what is in them?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== json files in one sample of each kind ==="
for d in datasets/rolling/seed-001001/x1 datasets/turntable_carry/seed-005001/x1 \
         datasets/free_fall/seed-003001/x1 datasets/damping/seed-007001/x1; do
  echo "  --- $d ---"
  ls -la "$d" 2>/dev/null | grep -vE '^total|^d' | awk '{printf "    %-34s %8.1f KB\n", $9, $5/1024}'
done

echo
echo "=== structure of the physics annotation files ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import json, os
REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
d = REPO + "/datasets/turntable_carry/seed-005001/x1"
for name in sorted(os.listdir(d)):
    if not name.endswith(".json"):
        continue
    p = os.path.join(d, name)
    try:
        obj = json.load(open(p))
    except Exception as e:
        print(f"  {name}: unreadable {e}"); continue
    kind = type(obj).__name__
    if isinstance(obj, dict):
        keys = list(obj.keys())[:14]
        print(f"  {name:28s} dict keys={keys}")
        for k in ("position", "quaternion", "linear_velocity", "angular_velocity"):
            if k in obj:
                v = obj[k]
                print(f"      {k}: {type(v).__name__} len={len(v) if hasattr(v,'__len__') else '?'}")
    elif isinstance(obj, list):
        print(f"  {name:28s} list len={len(obj)}")
        if obj and isinstance(obj[0], dict):
            print(f"      row keys={list(obj[0].keys())}")
PY
