#!/usr/bin/env bash
# Definitive PyBullet soft-body test. ASCII-only output so the local Windows
# console (GBK) can print it without a UnicodeEncodeError.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"

cat > /tmp/_sb_final.py <<'PY'
import os, pybullet as pb, pybullet_data
import numpy as np

d = pybullet_data.getDataPath()
pb.connect(pb.DIRECT)
pb.setAdditionalSearchPath(d)
pb.setGravity(0, 0, -9.81)
pb.setPhysicsEngineParameter(fixedTimeStep=1.0/240.0, numSolverIterations=50)

mesh = os.path.join(d, "sphere_smooth.obj")
body = pb.loadSoftBody(
    mesh,
    basePosition=[0, 0, 0.8],
    scale=0.25,
    mass=0.4,
    collisionMargin=0.004,
    useNeoHookean=1,
)
print("LOADED", flush=True)

pb.loadURDF("plane.urdf")
pb.changeDynamics(-1, -1, lateralFriction=0.8, restitution=0.05)

zs, exts = [], []
for i in range(240):
    pb.stepSimulation()
    pos, _ = pb.getBasePositionAndOrientation(body)
    zs.append(float(pos[2]))
    md = pb.getMeshData(body)
    if md and md[0]:
        arr = np.array([list(v) for v in md[1]], dtype=float)
        exts.append(float(arr[:, 2].max() - arr[:, 2].min()))

print(f"Z start={zs[0]:.4f} min={min(zs):.4f} last={zs[-1]:.4f}", flush=True)
print(f"Z trace={[round(v,3) for v in zs[::40]]}", flush=True)
if exts:
    print(f"EXTENT first={exts[0]:.4f} min={min(exts):.4f} last={exts[-1]:.4f}", flush=True)
    print(f"SQUSH pct={100*(1-min(exts)/exts[0]):.1f}", flush=True)

fell = min(zs) < zs[0] - 0.05
deformed = bool(exts) and min(exts) < exts[0] * 0.97
print(f"FELL={fell} DEFORMED={deformed}", flush=True)
print("DONE", flush=True)
pb.disconnect()
PY

"$PY" /tmp/_sb_final.py > /tmp/sbf.out 2>/tmp/sbf.err
rc=$?
echo "PYTHON EXIT CODE = $rc"
echo "--- stdout ---"
sed 's/^/  /' /tmp/sbf.out
echo "--- stderr tail ---"
tail -2 /tmp/sbf.err | sed 's/^/  /'
if [ "$rc" = "0" ]; then echo "RESULT: soft body ran end to end"; else echo "RESULT: failed rc=$rc"; fi
