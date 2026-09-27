#!/usr/bin/env bash
# Answer the physics question precisely: WHAT engine, WHAT representation, and
# why does the plush toy behave like a rigid plastic object?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x1"

echo "=== 1. collision representation of the teddy ==="
"$PY" - "$REPO" <<'PY'
import sys, pathlib, yaml
p = pathlib.Path(sys.argv[1]) / "assets/objects/gso_sootheze_cold_therapy_elephant/asset.yaml"
c = yaml.safe_load(open(p))
print("  collision type :", c["collision"].get("type"))
print("  collision mesh :", c["collision"].get("mesh"))
print("  simulation     :", c["collision"].get("simulation"))
print("  half_extents   :", c["collision"].get("half_extents"))
print("  mass_range     :", c["physics"].get("mass_range"))
print("  restitution    :", c["physics"].get("restitution_range"))
print("  friction       :", c["physics"].get("friction_range"))
print("  material_class :", c.get("material_class"))
PY

echo
echo "=== 2. what the engine actually is ==="
"$PY" - "$REPO" <<'PY'
import sys, pathlib, re
repo = pathlib.Path(sys.argv[1])
src = (repo / "src/physim/physics/pybullet_backend.py").read_text()
for pat in ("from kubric.simulator import PyBullet", "simulator.run(", "useMaximalCoordinates",
            "loadURDF", "loadSoftBody", "changeDynamics"):
    hits = [l.strip() for l in src.splitlines() if pat in l]
    print(f"  {pat:<40} {len(hits)} hit(s)")
    for h in hits[:2]:
        print(f"      {h[:96]}")
PY

echo
echo "=== 3. chosen physical parameters for THIS sample ==="
"$PY" - "$D" <<'PY'
import json, sys, os
D = sys.argv[1]
md = json.load(open(os.path.join(D, "metadata.json")))
ph = md.get("physics") or {}
print("  physics block:", json.dumps(ph, indent=2)[:600])
PY

echo
echo "=== 4. timeline: how many frames is the object actually MOVING? ==="
"$PY" - "$D" <<'PY'
import json, sys, os
import numpy as np
D = sys.argv[1]
tr = json.load(open(os.path.join(D, "trajectory.json")))
states = tr if isinstance(tr, list) else tr.get("states", tr.get("trajectory", []))
z = np.array([s["position"][2] for s in states])
v = np.array([s["linear_velocity"][2] for s in states])
speed = np.linalg.norm(np.array([s["linear_velocity"] for s in states]), axis=1)
n = len(states)
moving = speed > 0.02
print(f"  total frames          : {n}  ({n/16.0:.2f} s at 16 fps)")
print(f"  frames with motion    : {int(moving.sum())}  ({100*moving.mean():.0f}% of the clip)")
print(f"  frames essentially still: {int((~moving).sum())}")
print(f"  z: {z[0]:.3f} -> {z.min():.3f} -> {z[-1]:.3f}")
first_still = None
for i in range(n):
    if not moving[i]:
        first_still = i
        break
if first_still is not None:
    print(f"  motion ends at frame  : {first_still}  ({first_still/16.0:.2f} s)")
    print(f"  -> {100*(n-first_still)/n:.0f}% of the clip shows a motionless object")
PY
