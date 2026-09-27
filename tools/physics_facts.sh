#!/usr/bin/env bash
# The remaining facts needed to answer "why does the teddy behave like plastic".
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
D="$REPO/datasets/free_fall/seed-001000/x1"

echo "=== teddy collision + physics manifest ==="
"$PY" - "$REPO" <<'PY'
import sys, pathlib, yaml
p = pathlib.Path(sys.argv[1]) / "assets/objects/gso_sootheze_cold_therapy_elephant/asset.yaml"
c = yaml.safe_load(open(p))
print("  collision.type      :", c["collision"].get("type"))
print("  collision.mesh      :", c["collision"].get("mesh"))
print("  collision.simulation:", c["collision"].get("simulation"))
print("  mass_range          :", c["physics"].get("mass_range"))
print("  restitution_range   :", c["physics"].get("restitution_range"))
print("  friction_range      :", c["physics"].get("friction_range"))
print("  material_class      :", c.get("material_class"))
print("  allowed_scenarios   :", c.get("allowed_scenarios"))
PY

echo
echo "=== sampled restitution / mass for this run ==="
"$PY" - "$D" <<'PY'
import json, sys, os
D = sys.argv[1]
md = json.load(open(os.path.join(D, "metadata.json")))
ph = md.get("physics") or {}
for k in ("mass", "friction", "restitution", "rolling_friction",
          "spinning_friction", "gravity", "position", "linear_velocity",
          "angular_velocity", "support_height", "radius"):
    if k in ph:
        print(f"  {k:<20} {ph[k]}")
print("  (keys present):", ", ".join(sorted(ph)))
PY

echo
echo "=== is there ANY soft-body path in the pipeline? ==="
grep -rn "loadSoftBody\|soft_body\|soft body\|deformable" \
  "$REPO/src" 2>/dev/null | head -6 | sed 's/^/  /' || echo "  none"

echo
echo "=== what mesh do we have? (surface only -> no volume) ==="
"$PY" - "$REPO" <<'PY'
import sys, pathlib
repo = pathlib.Path(sys.argv[1])
obj = repo / "assets/objects/gso_sootheze_cold_therapy_elephant"
for f in ("visual/model.obj", "collision/model.obj"):
    p = obj / f
    if not p.is_file():
        print(f"  {f}: MISSING"); continue
    v = t = 0
    with open(p, errors="ignore") as fh:
        for line in fh:
            if line.startswith("v "): v += 1
            elif line.startswith("f "): t += 1
    print(f"  {f:<22} verts={v:<8} faces={t}")
print("  -> both are SURFACE meshes; a soft body needs a tetrahedral VOLUME")
PY
