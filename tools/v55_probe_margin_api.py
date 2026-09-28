"""V5.5 stage 03: determine how THIS pybullet build accepts a collision margin.

`createCollisionShape(..., collisionMargin=...)` failed with
"'collisionMargin' is an invalid keyword argument for this function", so the margin
mechanism must be established from the installed build rather than assumed.  03 requires
this to be verified THROUGH THE API: "实际支持情况通过API验证，不能写了配置就声称生效".

This inspects the real signatures and empirically tests every plausible mechanism.
"""

from __future__ import annotations

import inspect
import json

import pybullet as pb

print(f"pybullet API version: {pb.getAPIVersion()}")
print(f"pybullet build time : {pb.getBuildTime() if hasattr(pb, 'getBuildTime') else 'n/a'}")
print()

FN = pb.createCollisionShape
print("=== createCollisionShape signature ===")
try:
    print(f"  doc: {FN.__doc__}")
except Exception as exc:
    print(f"  no docstring: {exc}")

print()
print("=== which GEOM_ constants exist? ===")
for name in dir(pb):
    if name.startswith("GEOM_"):
        print(f"  {name} = {getattr(pb, name)}")

print()
print("=== does the physical-parameter API expose a margin? ===")
try:
    params = pb.getPhysicsEngineParameters()
    print(f"  getPhysicsEngineParameters keys: {sorted(params.keys())}")
    margin_keys = [k for k in params if "argin" in k]
    print(f"  margin-related engine params: {margin_keys}")
except Exception as exc:
    print(f"  failed: {exc}")

print()
print("=== empirical test: box half-extent vs raycast hit, with and without margin ===")
cid = pb.connect(pb.DIRECT)
results = {}

HALF = [0.02, 0.02, 0.005]     # 5 mm thinnest half-extent -> 10 mm thin box
BASE_Z = 0.5
EXPECTED_TOP = BASE_Z + HALF[2]

def probe(label, **kwargs):
    """Build a box with the given kwargs and measure where a downward ray first hits."""
    try:
        shape = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=HALF, **kwargs)
    except TypeError as exc:
        results[label] = {"accepted": False, "error": str(exc)}
        print(f"  {label:38s} REJECTED: {exc}")
        return
    body = pb.createMultiBody(0.05, shape, basePosition=[0, 0, BASE_Z])
    pb.performCollisionDetection()
    hit = pb.rayTest([0, 0, 1.0], [0, 0, 0.0])[0]
    # rayTest returns (objectUniqueId, linkIndex, hitFraction, hitPosition, hitNormal);
    # hitPosition is a 3-tuple, so the z coordinate is [3][2], not [3].
    top = None
    if hit[0] >= 0:
        pos = hit[3]
        top = float(pos[2]) if isinstance(pos, (tuple, list)) else float(pos)
    delta = round(top - EXPECTED_TOP, 9) if top is not None else None
    results[label] = {
        "accepted": True,
        "shape_id": int(shape),
        "raycast_hit_z": round(top, 9) if top is not None else None,
        "expected_top_z": EXPECTED_TOP,
        "delta_from_expected_m": delta,
        "margin_took_effect": bool(delta is not None and abs(delta) > 1e-9),
    }
    print(f"  {label:38s} accepted; hit_z={top} delta={delta} "
          f"margin_effect={results[label]['margin_took_effect']}")
    pb.removeBody(body)

probe("baseline (no margin arg)")
probe("collisionMargin=0.001", collisionMargin=0.001)
probe("margin=0.001", margin=0.001)

print()
print("=== GEOM_MESH margin (the mechanism used for mesh colliders) ===")
# Build a tiny closed tetrahedron OBJ to test mesh margin.
import tempfile, os
tet = tempfile.NamedTemporaryFile("w", suffix=".obj", delete=False, dir="/tmp")
tet.write("v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 3 2\nf 1 2 4\nf 1 4 3\nf 2 3 4\n")
tet.close()
for label, kwargs in (("mesh baseline", {}), ("mesh collisionMargin", {"collisionMargin": 0.001})):
    try:
        shape = pb.createCollisionShape(pb.GEOM_MESH, fileName=tet.name, **kwargs)
        results[f"mesh:{label}"] = {"accepted": True, "shape_id": int(shape)}
        print(f"  {label:38s} accepted")
    except TypeError as exc:
        results[f"mesh:{label}"] = {"accepted": False, "error": str(exc)}
        print(f"  {label:38s} REJECTED: {exc}")
os.unlink(tet.name)

print()
print("=== does loadURDF expose a margin through flags? ===")
print(f"  loadURDF doc: {(pb.loadURDF.__doc__ or '')[:300]}")

pb.disconnect()

print()
print("MARGIN_REPORT " + json.dumps(results, indent=2, default=str))
