#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Fix the URDF inside each registered GSO asset.
#
# GSO's shipped object.urdf references bare filenames:
#     <mesh filename="visual_geometry.obj"/>
#     <mesh filename="collision_geometry.obj"/>
# but our asset layout renames them to visual/model.obj and collision/model.obj,
# so PyBullet cannot resolve the mesh and fails with "Cannot load URDF file".
#
# PyBullet resolves mesh paths relative to the URDF's own directory, so the
# rewritten URDF lives in collision/ and points at model.obj there, with the
# visual reaching across to ../visual/model.obj.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
OBJ="$REPO/assets/objects"

echo "=== rewriting URDFs ==="
"$PY" - "$OBJ" <<'PY'
import os, sys, re, json
OBJ = sys.argv[1]
for aid in sorted(os.listdir(OBJ)):
    d = os.path.join(OBJ, aid)
    if not os.path.isdir(d) or not os.path.isfile(os.path.join(d, "asset.yaml")):
        continue
    src = os.path.join(d, "collision/model.urdf")
    if not os.path.isfile(src):
        continue
    txt = open(src).read()
    # point at the files that actually exist in our layout
    txt = re.sub(r'filename="[^"]*visual_geometry\.obj"',
                 'filename="../visual/model.obj"', txt)
    txt = re.sub(r'filename="[^"]*collision_geometry\.obj"',
                 'filename="model.obj"', txt)
    txt = re.sub(r'filename="[^"]*model\.obj"', 'filename="model.obj"', txt)
    txt = re.sub(r'filename="\.\./visual/model\.obj"',
                 'filename="../visual/model.obj"', txt)
    open(src, "w").write(txt)
    has_vis = "../visual/model.obj" in txt
    has_col = 'filename="model.obj"' in txt
    print(f"  {aid:<48} collision={'ok' if has_col else 'MISSING'} "
          f"visual={'ok' if has_vis else 'none'}")
PY

echo
echo "=== verify each URDF actually loads in PyBullet ==="
"$PY" - "$OBJ" <<'PY'
import os, sys
import pybullet as pb
OBJ = sys.argv[1]
pb.connect(pb.DIRECT)
ok = bad = 0
for aid in sorted(os.listdir(OBJ)):
    u = os.path.join(OBJ, aid, "collision/model.urdf")
    if not os.path.isfile(u):
        continue
    try:
        body = pb.loadURDF(u)
        n = pb.getNumJoints(body)
        print(f"  OK   {aid:<48} body={body} joints={n}")
        ok += 1
    except Exception as e:
        print(f"  FAIL {aid:<48} {type(e).__name__}: {str(e)[:60]}")
        bad += 1
print(f"  -> {ok} loadable, {bad} failed")
pb.disconnect()
PY
