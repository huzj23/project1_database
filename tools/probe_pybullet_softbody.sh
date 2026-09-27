#!/usr/bin/env bash
# Does PyBullet itself support soft (deformable) bodies?
#
# This decides a design question: the mentor's pipeline has exactly ONE solver --
# PyBullet integrates the motion, and Blender only replays the baked trajectory
# as keyframes ("It does not run another physics solver").  Using Blender's Soft
# Body would therefore introduce a SECOND, unsynchronised solver, and the
# exported trajectory.json would no longer describe what is on screen.
#
# If PyBullet can do deformables itself, the single-solver invariant survives and
# soft objects stay legitimate.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"

"$PY" -u - <<'PY' 2>&1 | grep -E '^SB|^  '
import pybullet as pb
import pybullet_data
import inspect

print(f"SB pybullet version: {pb.getAPIVersion()}")

# 1) is there a soft-body loader at all?
loaders = [n for n in dir(pb) if "oft" in n or "eform" in n]
print(f"SB soft/deform API surface: {loaders}")

for name in ("loadSoftBody", "loadDeformableBody"):
    fn = getattr(pb, name, None)
    if fn is None:
        print(f"  {name}: NOT PRESENT")
        continue
    try:
        sig = str(inspect.signature(fn))
    except (TypeError, ValueError):
        sig = "(builtin; no signature)"
    print(f"  {name}: present  {sig[:150]}")

# 2) do the related runtime calls exist (they are needed to drive one)?
for name in ("setInternalFixedTimeStep", "setPhysicsEngineParameter",
             "resetSimulation", "getMeshData", "setVascularCollision",
             "createSoftBodyAnchor", "setSoftBodyAnchor"):
    print(f"  {name}: {'yes' if hasattr(pb, name) else 'no'}")

# 3) a real functional probe: build a soft body from a primitive and step it
cid = pb.connect(pb.DIRECT)
pb.setGravity(0, 0, -9.81)
pb.setAdditionalSearchPath(pybullet_data.getDataPath())

made = None
for kwargs in (
    dict(basePosition=[0, 0, 1.0], scale=0.2, mass=0.5, collisionMargin=0.01),
    dict(basePosition=[0, 0, 1.0], scale=0.2, mass=0.5),
    dict(basePosition=[0, 0, 1.0], scale=0.2),
):
    try:
        made = pb.loadSoftBody("sphere.obj", **kwargs)
        print(f"SB loadSoftBody(sphere.obj, {list(kwargs)}) -> id={made}")
        break
    except Exception as e:
        print(f"  attempt {list(kwargs)} failed: {type(e).__name__}: {str(e)[:80]}")

if made is not None:
    zs = []
    for _ in range(60):
        pb.stepSimulation()
        pos, _ = pb.getBasePositionAndOrientation(made)
        zs.append(round(pos[2], 4))
    print(f"SB position z over 60 steps: {zs[0]} -> {zs[-1]}  (fell={zs[-1] < zs[0] - 0.01})")
    try:
        md = pb.getMeshData(made)
        print(f"SB mesh vertex count: {md[0] if md else 'n/a'}")
    except Exception as e:
        print(f"  getMeshData: {type(e).__name__}: {str(e)[:60]}")
    print("SB VERDICT: PyBullet SOFT BODY works -> single-solver design can hold")
else:
    print("SB VERDICT: no usable soft body loader in this build")

pb.disconnect()
PY
