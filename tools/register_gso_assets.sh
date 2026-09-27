#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# P1.1  Register our GSO objects in the mentor pipeline's asset format.
#
# His AssetManager needs, per object:
#   assets/objects/<id>/visual/model.<ext>       visual mesh
#   assets/objects/<id>/collision/model.obj      collision mesh
#   assets/objects/<id>/collision/model.urdf     simulation file
#   assets/objects/<id>/asset.yaml               manifest
#
# GSO already ships everything required:
#   visual_geometry.obj + .mtl + texture.png  -> visual/
#   collision_geometry.obj                    -> collision/
#   object.urdf                               -> collision/
#   data.json                                 -> bounds + mass for the manifest
#
# Derived quantities are computed from the mesh bounds in the RESTING pose:
#   support_height  = -min_z          (COM height above the support surface)
#   half_extents    = span / 2
#   footprint_radius= half of the larger horizontal extent
#   bounding_radius = half of the box diagonal
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
GSO="$WS/models/gso"

OBJECTS="${*:-Sootheze_Cold_Therapy_Elephant Room_Essentials_Fabric_Cube_Lavender Mad_Gab_Refresh_Card_Game Ecoforms_Plant_Container_GP16A_Coral Down_To_Earth_Orchid_Pot_Ceramic_Lime Whey_Protein_Vanilla}"

mkdir -p "$REPO/assets/objects"

for name in $OBJECTS; do
  src="$GSO/$name"
  [ -d "$src" ] || { echo "  MISSING $name"; continue; }

  # short, filesystem-safe id: drop the vendor prefix, keep it recognisable
  short=$(printf '%s' "$name" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9' '_' | sed 's/__*/_/g; s/_$//')
  short=$(printf '%s' "$short" | cut -c1-40)
  aid="gso_${short}"

  dst="$REPO/assets/objects/$aid"
  mkdir -p "$dst/visual" "$dst/collision" "$dst/license"

  cp -f "$src/visual_geometry.obj" "$dst/visual/model.obj"
  cp -f "$src/visual_geometry.mtl" "$dst/visual/model.mtl"
  cp -f "$src/texture.png"         "$dst/visual/texture.png"
  cp -f "$src/collision_geometry.obj" "$dst/collision/model.obj" 2>/dev/null || \
    cp -f "$src/visual_geometry.obj" "$dst/collision/model.obj"
  cp -f "$src/object.urdf" "$dst/collision/model.urdf" 2>/dev/null || true

  "$PY" - "$src" "$dst" "$aid" "$name" <<'PY'
import json, os, sys
src, dst, aid, name = sys.argv[1:5]
d = json.load(open(os.path.join(src, "data.json")))
b = d["kwargs"]["bounds"]
lo, hi = b[0], b[1]
size = [hi[i] - lo[i] for i in range(3)]
support = -lo[2]                       # resting: lowest point on the floor
half = [s / 2.0 for s in size]
foot = max(size[0], size[1]) / 2.0
brad = sum(v * v for v in half) ** 0.5
mass = float(d["kwargs"].get("mass", 0.05)) or 0.05
cat = (d.get("metadata", {}).get("category") or "scanned").lower().replace(" ", "_")

# vertex/triangle counts for the quality block
nv = nt = 0
p = os.path.join(dst, "visual/model.obj")
with open(p, "r", errors="ignore") as fh:
    for line in fh:
        if line.startswith("v "):
            nv += 1
        elif line.startswith("f "):
            nt += 1

yaml = f"""version: 1
id: {aid}
kind: object
category: {cat}

source: Google Scanned Objects (GSO)
source_filename: {name}
license: CC BY-SA 4.0
license_note: attribution + ShareAlike; see license/SOURCE.md

quality:
  vertices: {nv}
  triangles: {nt}
  normalized_max_dimension_m: {max(size):.6f}

visual:
  mesh: visual/model.obj
  size: [{size[0]:.6f}, {size[1]:.6f}, {size[2]:.6f}]
  scale: [1.0, 1.0, 1.0]

visual_transform:
  x_rotation_degrees: 0.0
  center_mesh_origin: false

initial_orientation:
  policy: fixed_authored_upright
  quaternion_wxyz: [1.0, 0.0, 0.0, 0.0]

collision:
  type: convex_hull
  mesh: collision/model.obj
  simulation: collision/model.urdf
  bounding_radius: {brad:.6f}
  footprint_radius: {foot:.6f}
  support_height: {support:.6f}
  half_extents: [{half[0]:.6f}, {half[1]:.6f}, {half[2]:.6f}]

physics:
  mass_range: [{mass * 0.8:.6f}, {mass * 1.2:.6f}]
  friction_range: [0.30, 0.60]
  restitution_range: [0.05, 0.35]

allowed_scenarios: [rolling, constant_force, free_fall]
"""
open(os.path.join(dst, "asset.yaml"), "w").write(yaml)

lic = f"""# {name}

Source: Google Scanned Objects (GSO)
License: CC BY-SA 4.0  (https://creativecommons.org/licenses/by-sa/4.0/)

Attribution: Google LLC, Scanned Objects dataset.

ShareAlike: derivative datasets that redistribute this asset or renders of it
must be released under a compatible license. Academic use is permitted.
"""
open(os.path.join(dst, "license/SOURCE.md"), "w").write(lic)

print(f"  {aid:<46} size={max(size):.3f}m support={support:.3f} "
      f"foot={foot:.3f} mass={mass:.4f} verts={nv}")
PY
done

echo
echo "=== registered assets ==="
ls "$REPO/assets/objects" | sed 's/^/  /'
