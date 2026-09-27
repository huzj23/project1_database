#!/usr/bin/env bash
# ===========================================================================
# T3 STEP 2: add the `table_top` region and fix the stale floor comment.
#
# Table measured on the CURRENT scene.blend by raycast:
#     z = 0.7584 exactly, over x[-0.20, 0.80] y[-0.20, 0.50]
#     82 of 82 sampled points hit 0.7584 with normal.z = 1.0 -> genuinely flat
# This matches the frozen V3.2 record (top z 0.7584, centre (0.414, 0.175)).
#
# The disc is r=0.30 and the table spans 1.0 x 0.7 m of measured flat area, so a
# 0.30 m radius disc cannot be placed with a full-radius margin in BOTH axes.
# The table is genuinely ~1.0 x 0.7 m; a 0.60 m disc needs a 0.60 x 0.60 m clear
# square, which DOES fit (0.60 < 0.70).  Placement bounds are therefore set to the
# largest square that keeps the disc on the table:
#     x[-0.10, 0.50]  (0.60 m)   y[-0.10, 0.50]  (0.60 m)
# with the disc centred inside.  The actor rides on the disc, so it needs no extra
# table room of its own.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
cp configs/maps.yaml "$WS/tmp/maps_pre_tabletop.bak"

echo "=== 1) fix the stale floor comment (exact text) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import re
p = "configs/maps.yaml"
s = open(p).read()
before = s
# correct the face count recorded for the re-extracted floor
s = re.sub(r"(\n                triangles: )202\b", r"\g<1>94", s)
# replace the now-inaccurate explanation lines, matching loosely on their content
s = re.sub(
    r"              # Extracted by geometry from visual/scene\.blend: upward faces with\n"
    r"              # z in \[0\.00, 0\.05\) -> 202 triangles, 81\.61 m\^2, footprint\n"
    r"              # x\[-2\.47, 4\.00\] y\[-6\.86, 4\.76\]\.  The simulator builds its\n"
    r"              # support body from this mesh instead of from bounds_xy\.\n",
    "              # Extracted from visual/scene.blend keeping only faces whose ALL\n"
    "              # THREE vertices lie within 1 cm of the floor plane and whose normal\n"
    "              # is upward -> 94 triangles, 84.68 m^2, z in [-0.0416, 0.0007].\n"
    "              #\n"
    "              # The first attempt filtered on the FACE CENTRE z < 0.05 and kept\n"
    "              # 202 faces / 81.61 m^2, but that admitted triangles spanning a\n"
    "              # height change: raycasting then hit z = 0.084 at the placement\n"
    "              # point, the actor rested 7.1 cm too high, and supported_fraction\n"
    "              # collapsed to 0.012.  The all-vertices criterion removes them.\n"
    "              #\n"
    "              # The simulator builds its support body from this mesh instead of\n"
    "              # from bounds_xy.\n",
    s,
)
open(p, "w").write(s)
print("  changed:", s != before)
print("  triangles line now:", re.search(r"triangles: \d+", s).group(0))
PY

echo
echo "=== 2) append the table_top surface group ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
p = "configs/maps.yaml"
s = open(p).read()
assert "table_top" not in s.split("replicad_apartment:")[-1], "table_top already present"

block = """
        # ------------------------------------------------------------------
        # table_top: the flat top of frl_apartment_table_01, for the turntable
        # motions (#5 圆周 and #6 转盘自转).  Measured on the current
        # scene.blend by raycast: z = 0.7584 over x[-0.20, 0.80] y[-0.20, 0.50],
        # 82/82 points at 0.7584 with normal.z = 1.0 -> genuinely flat, and it
        # matches the frozen V3.2 record (top z 0.7584, centre (0.414, 0.175)).
        #
        # The disc is r = 0.30 m and the table is ~1.0 x 0.7 m, so placement is
        # the largest 0.60 x 0.60 m square that keeps the whole disc on the table.
        # Collision is the same extracted floor mesh, NOT the table: the disc is a
        # dynamic body driven by the solver, so it rests on its own contact with
        # the floor mesh below -- the table is scenery in the render.
        # ------------------------------------------------------------------
        - surface_type: table_top
          object_extent_range_m: [0.03, 0.20]
          edge_margin: 0.02
          clearance: 0.05
          collision_thickness: 0.05
          regions:
            - region_id: replicad_apartment_table_top
              cleanliness: verified_clear
              verification: raycast_flat_table_surface_at_z_0.7584
              position: [0.2000, 0.2000, 0.7584]
              normal: [0.0, 0.0, 1.0]
              bounds_xy: [-0.1000, 0.5000, -0.1000, 0.5000]
              collision:
                type: mesh
                mesh: collision/surfaces/replicad_apartment_floor.obj
                simulation: collision/surfaces/replicad_apartment_floor.urdf
                triangles: 94
                max_triangles: 2048
                mesh_sha256: 0a3fde1f13f44d8147f35c9ffacdb9b5850ff95e9dbb7e6ac4b6d7fb6c591f28
"""
s = s.rstrip("\n") + "\n" + block
open(p, "w").write(s)
print("  table_top group appended")
PY

echo
echo "=== 3) verify it loads ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys; sys.path.insert(0,"src")
from physim.assets import AssetManager
from physim.maps import MapManager
am=AssetManager("configs/assets.yaml","assets"); mm=MapManager("configs/maps.yaml",am)
m=mm.get("replicad_apartment", require_files=True)
for s in m.surfaces:
    x0,x1,y0,y1=s.bounds_xy
    print(f"  surface_type={s.surface_type:10s} id={s.surface_id}")
    print(f"    position={s.position}")
    print(f"    bounds {x1-x0:.2f} x {y1-y0:.2f} m   extent_range={s.object_extent_range}")
    print(f"    collision={'MESH '+s.collision_simulation_path.name if s.collision_simulation_path else 'BOX'}")
PY
