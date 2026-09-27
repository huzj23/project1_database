#!/usr/bin/env bash
# Inspect the smoke sample: is the motion REALLY integrated, and did validation pass?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x1"

echo "=== files ==="
find "$D" -maxdepth 1 -type f | sed "s#$D/#  #"
echo "  rgb frames   : $(ls "$D/rgb" 2>/dev/null | wc -l)"
echo "  depth frames : $(ls "$D/depth" 2>/dev/null | wc -l)"
echo "  seg frames   : $(ls "$D/segmentation" 2>/dev/null | wc -l)"
echo "  total size   : $(du -sh "$D" 2>/dev/null | cut -f1)"

echo
echo "=== trajectory: is this a real integration? ==="
"$WS/tools/conda_env/bin/python" - "$D" <<'PY'
import json, sys, os
import numpy as np
D = sys.argv[1]
p = os.path.join(D, "trajectory.json")
if not os.path.isfile(p):
    print("  no trajectory.json"); raise SystemExit
t = json.load(open(p))
states = t if isinstance(t, list) else t.get("states", t.get("trajectory", []))
print(f"  states: {len(states)}")
if not states:
    print("  keys:", list(t)[:8]); raise SystemExit
z = np.array([s["position"][2] for s in states])
vz = np.array([s["linear_velocity"][2] for s in states])
tsec = np.array([s.get("time_seconds", i/16.0) for i, s in enumerate(states)])
print(f"  z: start={z[0]:.4f}  min={z.min():.4f}  end={z[-1]:.4f}")
print(f"  vz: start={vz[0]:.4f}  min={vz.min():.4f}  max_after_min={vz[z.argmin():].max():.4f}")

# free fall check: during the fall, dz/dt should accelerate at ~ -g
if len(z) > 6:
    d = np.diff(z)
    fall = d[d < 0]
    n = min(len(fall), 6)
    print(f"  first {n} downward steps: {np.round(fall[:n], 5).tolist()}")
    inc = np.all(np.diff(fall[:n]) < 0) if n > 2 else None
    print(f"  steps grow (accelerating under gravity): {inc}")

turns = int(np.sum(np.diff(np.sign(np.diff(z))) > 0))
print(f"  direction reversals (bounce count): {turns}")
print(f"  REAL PHYSICS: {'yes' if z.min() < z[0] - 0.1 else 'no fall detected'}")

c = os.path.join(D, "collisions.json")
if os.path.isfile(c):
    coll = json.load(open(c))
    items = coll if isinstance(coll, list) else coll.get("collisions", [])
    print(f"  collision events: {len(items)}")
    if items:
        print(f"    first: frame={items[0].get('frame')} "
              f"force={items[0].get('force', 0):.3f} "
              f"normal={[round(v,2) for v in items[0].get('contact_normal', [])]}")

m = os.path.join(D, "metadata.json")
if os.path.isfile(m):
    md = json.load(open(m))
    val = md.get("validation") or md.get("validation_report") or {}
    print(f"  validation: valid={val.get('valid')} reasons={val.get('reasons')}")
    for k in ("travel_distance", "trajectory_extent_object_ratio",
              "max_linear_speed", "supported_fraction",
              "drop_distance", "max_surface_penetration",
              "max_post_contact_upward_speed"):
        if k in val:
            v = val[k]
            print(f"    {k:<34} {v if not isinstance(v,float) else round(v,5)}")
        elif isinstance(val.get("metrics"), dict) and k in val["metrics"]:
            v = val["metrics"][k]
            print(f"    {k:<34} {v if not isinstance(v,float) else round(v,5)}")
PY
