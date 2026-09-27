#!/usr/bin/env bash
# PyBullet soft body, take 2: pass an ABSOLUTE mesh path.
#
# The previous attempt failed on a relative-path lookup
# ("cannot find '../../../../data//.../sphere.obj' in any directory"), not on a
# missing feature.  pybullet_data ships bunny.obj, duck.obj, sphere_smooth.obj and
# teddy2_VHACD_CHs.obj -- the last two are directly useful for a falling plush.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"

cat > /tmp/_sb_two.py <<'PY'
import os, pybullet as pb, pybullet_data
d = pybullet_data.getDataPath()
pb.connect(pb.DIRECT)
pb.setGravity(0, 0, -9.81)
pb.setPhysicsEngineParameter(fixedTimeStep=1.0/240.0, numSolverIterations=50)

mesh = os.path.join(d, "sphere_smooth.obj")
print(f"MESH {mesh} exists={os.path.isfile(mesh)}", flush=True)

try:
    body = pb.loadSoftBody(
        mesh,
        basePosition=[0, 0, 0.8],
        scale=0.25,
        mass=0.4,
        collisionMargin=0.004,
        useNeoHookean=1,          # Neo-Hookean material: soft, near-incompressible
        useBendingSprings=1,
        useMassSpring=1,
        springElasticStiffness=0.6,
        springDampingStiffness=0.05,
        springDampingAllDirections=1,
    )
    print(f"LOADED id={body}", flush=True)
except Exception as e:
    print(f"FAIL {type(e).__name__}: {str(e)[:120]}", flush=True)
    raise SystemExit(1)

# a static floor so the soft body has something to land on
pb.loadURDF("plane.urdf")
pb.changeDynamics(-1, -1, lateralFriction=0.8, restitution=0.05)

zs, spreads = [], []
for _ in range(200):
    pb.stepSimulation()
    pos, _ = pb.getBasePositionAndOrientation(body)
    md = pb.getMeshData(body)
    n = md[0] if md else 0
    if n:
        import numpy as np
        verts = np.array(md[1]).reshape(-1, 3) if not isinstance(md[1][0], (list, tuple)) else np.array(md[1])
        dz = float(verts[:, 2].max() - verts[:, 2].min())
    else:
        dz = float("nan")
    zs.append(round(float(pos[2]), 4))
    spreads.append(round(dz, 4))

print(f"Z  first={zs[0]}  min={min(zs)}  last={zs[-1]}", flush=True)
print(f"Z  samples: {zs[::25]}", flush=True)
print(f"EXTENT first={spreads[0]}  min={min(spreads)}  last={spreads[-1]}", flush=True)
fell = min(zs) < zs[0] - 0.05
deformed = min(spreads) < spreads[0] * 0.95
print(f"FELL={fell}  DEFORMED={deformed}", flush=True)
print(f"VERDICT: {'soft body simulates AND deforms' if (fell and deformed) else ('simulates, deformation unclear' if fell else 'no motion')}", flush=True)
pb.disconnect()
PY

echo "=== 绝对路径 + Neo-Hookean 材质 ==="
"$PY" /tmp/_sb_two.py 2>&1 | grep -E '^(MESH|LOADED|FAIL|Z |EXTENT|FELL|VERDICT)|b3Warning.*soft'
echo "  exit=$?"
