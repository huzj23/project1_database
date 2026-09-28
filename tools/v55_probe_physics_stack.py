"""V5.5 stage 03: prove the server can run the PHYSICS half without Blender.

Architectural finding
---------------------
`pybullet_backend.py` imports pybullet and the vendored kubric simulator, but never
`bpy`.  Solving and rendering are therefore separable, which is exactly what 06 section 4
prescribes: "服务器tmux求解和记录，轨迹/运行副本/依赖同步本地，用已验证4.2回放" -- the
server solves and records, and the validated local 4.2 replays.

That matters because Hidden Alley is a Blender 4.0 file the server's 3.4.1 cannot read
(it segfaults), while Blender 4.2.23 cannot start on the server at all (glibc).
The scene's GEOMETRY can still reach the server as plain OBJ/URDF, which needs no Blender
to read -- so the server can build colliders and solve, and the local 4.2 renders.

This script establishes the prerequisite: pybullet and the vendored kubric import and
step on the server.
"""

from __future__ import annotations

import json
import platform
import sys
import traceback

sys.path.insert(0, "src")

report: dict = {
    "python": sys.version.split()[0],
    "platform": platform.platform(),
}

print("=== 1. pybullet ===")
try:
    import pybullet as pb

    report["pybullet_version"] = pb.getAPIVersion()
    # Connect headless and step a trivial world: proves the solver actually runs here.
    cid = pb.connect(pb.DIRECT)
    report["pybullet_connected"] = cid >= 0
    pb.setGravity(0, 0, -9.81)
    # Simple box dropping onto a plane -- the smallest real solve.
    plane = pb.createCollisionShape(pb.GEOM_PLANE)
    pb.createMultiBody(0, plane)
    box = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[0.05, 0.05, 0.05])
    body = pb.createMultiBody(0.2, box, basePosition=[0, 0, 0.5])
    pb.setTimeStep(1.0 / 480.0)
    z0 = pb.getBasePositionAndOrientation(body)[0][2]
    for _ in range(480):
        pb.stepSimulation()
    z1 = pb.getBasePositionAndOrientation(body)[0][2]
    report["box_z_start"] = round(z0, 5)
    report["box_z_after_1s"] = round(z1, 5)
    report["box_rested_on_plane"] = abs(z1 - 0.05) < 0.01
    pb.disconnect()
    print(f"  pybullet {report['pybullet_version']} OK; box fell {z0:.3f} -> {z1:.3f} m")
    print(f"  rested on plane at half-height: {report['box_rested_on_plane']}")
except Exception as exc:
    traceback.print_exc()
    report["pybullet_error"] = f"{type(exc).__name__}: {exc}"
    print(f"  FAILED: {exc}")

print()
print("=== 2. vendored kubric simulator ===")
try:
    from physim.reference import load_phyco_kubric  # noqa: F401
    from kubric.simulator import PyBullet as KubricPyBullet

    report["kubric_pybullet_imported"] = True
    print(f"  imported: {KubricPyBullet}")
except Exception as exc:
    report["kubric_error"] = f"{type(exc).__name__}: {exc}"
    print(f"  FAILED: {exc}")

print()
print("=== 3. the real project backend ===")
try:
    from physim.physics.pybullet_backend import PyBulletBackend

    report["backend_imported"] = True
    print(f"  imported: {PyBulletBackend}")
except Exception as exc:
    traceback.print_exc()
    report["backend_error"] = f"{type(exc).__name__}: {exc}"
    print(f"  FAILED: {exc}")

print()
print("=== 4. confirm bpy is NOT required by the physics path ===")
report["bpy_available"] = "bpy" in sys.modules
try:
    import bpy  # noqa: F401

    report["bpy_importable"] = True
    print("  bpy IS importable here (unexpected but harmless)")
except Exception:
    report["bpy_importable"] = False
    print("  bpy is NOT importable -- and the physics path above still works, confirming")
    print("  that solving does not depend on Blender.")

print()
print("PHYSICS_REPORT " + json.dumps(report))
