#!/usr/bin/env bash
# Capture the exact failure mode of the PyBullet soft-body step.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"

cat > /tmp/_sb_three.py <<'PY'
import os, sys, pybullet as pb, pybullet_data
d = pybullet_data.getDataPath()
pb.connect(pb.DIRECT)
pb.setAdditionalSearchPath(pybullet_data.getDataPath())
pb.setGravity(0, 0, -9.81)
pb.setPhysicsEngineParameter(fixedTimeStep=1.0/240.0, numSolverIterations=50)
body = pb.loadSoftBody(os.path.join(d, "sphere_smooth.obj"),
                       basePosition=[0, 0, 0.8], scale=0.25, mass=0.4,
                       collisionMargin=0.004, useNeoHookean=1)
print("LOADED", flush=True)
pb.loadURDF("plane.urdf")
print("PLANE", flush=True)
for i in range(200):
    pb.stepSimulation()
    if i % 40 == 0:
        pos, _ = pb.getBasePositionAndOrientation(body)
        print(f"STEP {i} z={pos[2]:.4f}", flush=True)
import numpy as np
md = pb.getMeshData(body)
if md:
    n = md[0]
    arr = np.array([v for v in md[1]], dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 3)
    dz = float(arr[:, 2].max() - arr[:, 2].min())
    print(f"MESH verts={n} extent_z={dz:.4f}", flush=True)
print("DONE", flush=True)
pb.disconnect()
PY

"$PY" /tmp/_sb_three.py > /tmp/sb3.out 2>/tmp/sb3.err
rc=$?
echo "PYTHON EXIT CODE = $rc"
echo "--- stdout ---"
cat /tmp/sb3.out | sed 's/^/  /'
echo "--- stderr (tail) ---"
tail -4 /tmp/sb3.err | sed 's/^/  /'
case $rc in
  0)   echo "RESULT: 杞綋瀹屾暣璺戦€? ;;
  139) echo "RESULT: 娈甸敊璇?SIGSEGV 鈥斺€?姝ヨ繘鏃跺師鐢熷穿婧? ;;
  134) echo "RESULT: SIGABRT" ;;
  *)   echo "RESULT: 鍏朵粬寮傚父 ($rc)" ;;
esac
