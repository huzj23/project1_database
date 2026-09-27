#!/usr/bin/env bash
# ===========================================================================
# T3 STEP 2 (final): fix the stale comment at its ACTUAL indentation (12 spaces)
# and append table_top as a sibling of the floor group (6 spaces).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY'
import re
p = "configs/maps.yaml"
lines = open(p).read().split("\n")
out = []
i = 0
fixed = 0
while i < len(lines):
    ln = lines[i]
    if ln.strip() == "# The scene's own floor slab replaces the old 2.89 m^2 box proxy.":
        ind = ln[:len(ln) - len(ln.lstrip())]
        out += [
            ind + "# The scene's own floor slab replaces the old 2.89 m^2 box proxy.",
            ind + "# Extracted from visual/scene.blend keeping only faces whose ALL",
            ind + "# THREE vertices lie within 1 cm of the floor plane and whose",
            ind + "# normal is upward -> 94 triangles, 84.68 m^2, z in",
            ind + "# [-0.0416, 0.0007].",
            ind + "#",
            ind + "# The first attempt filtered on the FACE CENTRE z < 0.05 and kept",
            ind + "# 202 faces / 81.61 m^2, but that admitted triangles spanning a",
            ind + "# height change: raycasting then hit z = 0.084 at the placement",
            ind + "# point, the actor rested 7.1 cm too high, and supported_fraction",
            ind + "# collapsed to 0.012.  The all-vertices criterion removes them.",
            ind + "#",
            ind + "# The simulator builds its support body from this mesh instead of",
            ind + "# from bounds_xy.",
        ]
        # skip the 4 stale continuation lines
        i += 5
        fixed += 1
        continue
    if ln.strip() == "triangles: 202":
        out.append(ln.replace("202", "94"))
        i += 1
        continue
    out.append(ln)
    i += 1

s = "\n".join(out)
assert fixed == 1, f"expected 1 comment block, fixed {fixed}"
# NOTE: `table_top` is also a surface_type in the CLASSROOM map (student desks),
# so the check must be scoped to the replicad_apartment section only.
_rep = s.split("replicad_apartment:")[-1]
assert "table_top" not in _rep, "table_top already present in replicad_apartment"

block = (
"\n"
"      # ------------------------------------------------------------------\n"
"      # table_top: the flat top of frl_apartment_table_01, for the turntable\n"
"      # motions (#5 circular carry and #6 disc spin).  Measured on the current\n"
"      # scene.blend by raycast: z = 0.7584 over x[-0.20, 0.80] y[-0.20, 0.50],\n"
"      # 82 of 82 sampled points at 0.7584 with normal.z = 1.0, so it is\n"
"      # genuinely flat; it matches the frozen V3.2 record (top z 0.7584,\n"
"      # centre (0.414, 0.175)).\n"
"      #\n"
"      # The disc is r = 0.30 m and the table is about 1.0 x 0.7 m, so placement\n"
"      # is the largest 0.60 x 0.60 m square that keeps the whole disc on the\n"
"      # table.  Collision is the extracted floor mesh, not the table: the disc is\n"
"      # a dynamic body resting on its own contact with the floor mesh below, and\n"
"      # the table is scenery in the render.\n"
"      # ------------------------------------------------------------------\n"
"      - surface_type: table_top\n"
"        object_extent_range_m: [0.03, 0.20]\n"
"        edge_margin: 0.02\n"
"        clearance: 0.05\n"
"        collision_thickness: 0.05\n"
"        regions:\n"
"          - region_id: replicad_apartment_table_top\n"
"            cleanliness: verified_clear\n"
"            verification: raycast_flat_table_surface_at_z_0.7584\n"
"            position: [0.2000, 0.2000, 0.7584]\n"
"            normal: [0.0, 0.0, 1.0]\n"
"            bounds_xy: [-0.1000, 0.5000, -0.1000, 0.5000]\n"
"            collision:\n"
"              type: mesh\n"
"              mesh: collision/surfaces/replicad_apartment_floor.obj\n"
"              simulation: collision/surfaces/replicad_apartment_floor.urdf\n"
"              triangles: 94\n"
"              max_triangles: 2048\n"
"              mesh_sha256: 0a3fde1f13f44d8147f35c9ffacdb9b5850ff95e9dbb7e6ac4b6d7fb6c591f28\n"
)
s = s.rstrip("\n") + "\n" + block
open(p, "w").write(s)
print("  comment fixed, table_top appended")
PY

echo
echo "=== verify ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys; sys.path.insert(0,"src")
from physim.assets import AssetManager
from physim.maps import MapManager
am=AssetManager("configs/assets.yaml","assets"); mm=MapManager("configs/maps.yaml",am)
m=mm.get("replicad_apartment", require_files=True)
print(f"  {len(m.surfaces)} surfaces")
for s in m.surfaces:
    x0,x1,y0,y1=s.bounds_xy
    print(f"  type={s.surface_type:10s} id={s.surface_id}")
    print(f"    position={s.position}  bounds {x1-x0:.2f} x {y1-y0:.2f} m")
    print(f"    extent_range={s.object_extent_range}  collision="
          f"{'MESH '+s.collision_simulation_path.name if s.collision_simulation_path else 'BOX'}")
# make sure the other maps still parse
for mid in ("basketball_court","classroom","street"):
    mm.get(mid, require_files=False)
print("  all maps parse OK")
PY
