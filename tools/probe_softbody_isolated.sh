#!/usr/bin/env bash
# Isolate the PyBullet soft-body load: run each attempt in its OWN subprocess so a
# native crash reports as an exit code instead of silently killing the harness.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"

cat > /tmp/_sb_one.py <<'PY'
import sys, pybullet as pb, pybullet_data
pb.connect(pb.DIRECT)
pb.setGravity(0, 0, -9.81)
pb.setAdditionalSearchPath(pybullet_data.getDataPath())
try:
    body = pb.loadSoftBody("sphere.obj", basePosition=[0, 0, 1.0], scale=0.2, mass=0.5)
    print(f"LOADED id={body}", flush=True)
    for _ in range(40):
        pb.stepSimulation()
    pos, _ = pb.getBasePositionAndOrientation(body)
    print(f"STEPPED final z={pos[2]:.4f}", flush=True)
except Exception as e:
    print(f"PY-EXC {type(e).__name__}: {str(e)[:100]}", flush=True)
pb.disconnect()
PY

echo "=== 子进程隔离测试（sphere.obj）==="
"$PY" /tmp/_sb_one.py
rc=$?
echo "  exit code = $rc"
case $rc in
  0)   echo "  => 软体可用" ;;
  139) echo "  => 段错误（SIGSEGV）：loadSoftBody 在这个构建里会崩溃" ;;
  *)   echo "  => 异常退出" ;;
esac

echo
echo "=== 检查 pybullet_data 里有哪些适合软体的网格 ==="
"$PY" - <<'PY'
import pybullet_data, os
d = pybullet_data.getDataPath()
cands = [f for f in os.listdir(d) if f.endswith((".obj", ".vtk"))]
print("  ", ", ".join(sorted(cands)[:14]))
PY
