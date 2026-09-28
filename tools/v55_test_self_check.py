"""V5.5 stage 03/04: prove the solver's self_check CATCHES the silent collider failure.

`MultibodySolver.self_check()` only has value if it actually fails on a broken collider. This
drives the real solver API and requires:

  S1 a plane collider                                    -> ok=True
  S2 the concave tray declared `concave=True` but LEFT UNFLAGGED, i.e. the declaration and the
     geometry disagree                                  -> ok=False, because the control probe
                                                             rests 12.6 mm too high on the
                                                             silently hulled collider
  S3 the same tray, correctly flagged concave            -> ok=True

S2 is deliberately a MIS-DECLARATION, not a missing flag, because that is the failure mode that
actually occurred and the one no flag-consistency check can see. It is caught by pinning the
collider's recorded support height: stage 03 measured the tray floor by raycast at
z = 0.510600, so the probe must come to rest there within 2 mm, and on a hulled collider it
cannot. The check therefore verifies the collider against an INDEPENDENT measurement rather than
against its own declaration.

It also pins the ``vertices=``/``indices=`` route failure that began this investigation, so it
cannot quietly return.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pybullet as pb

CODE = Path("/data/raw/huzijian/project1_database/code/physics-video-sim/"
            "physics-video-sim-main/src")
sys.path.insert(0, str(CODE))

from physim.contracts import BodySpec, StaticCollider  # noqa: E402
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
TRAY = SCENES / "runtime/static_Vassoio.obj"
FLOOR_Z = 0.510600
RIM_Z = 0.522260


def make_solver(static: StaticCollider):
    """Only the static collider under test is meaningful here; `self_check` masks the dynamic
    body itself so the probe cannot be contaminated by it."""
    solver = MultibodySolver(SolverSettings(physics_fps=480))
    body = BodySpec(
        instance_id="probe_001", asset_id="probe", role="trigger",
        mass_kg=0.35, mass_basis="estimated", collider_type="box",
        position_m=(1.55, 7.42, 1.20), quaternion_xyzw=(0, 0, 0, 1),
    )
    solver.load([body], [static],
                primitives={"probe_001": {"half_extents_m": (0.05, 0.05, 0.025)}})
    return solver


def report(label: str, r: dict, key: str = "tray") -> dict:
    c = r["static_colliders"].get(key, {})
    print(f"  {label:34s} ok={str(r['ok']):5s} rest_bottom={c.get('rest_bottom_z')} "
          f"aabb_top={c.get('aabb_top_z')} supported={c.get('supported')} "
          f"concavity={c.get('concavity_represented')} "
          f"height_ok={c.get('support_height_verified')} "
          f"err={c.get('support_height_error_m')}")
    return c


def main() -> int:
    out: dict = {}
    print("=" * 86)

    # ---- S1: a plane must pass ------------------------------------------------------
    s1 = make_solver(StaticCollider(collider_id="plane", collider_type="plane"))
    r1 = s1.self_check()
    print(f"  {'S1 plane':34s} ok={str(r1['ok']):5s} controls={r1['controls']}")
    out["S1_plane_ok"] = r1["ok"]
    s1.disconnect()

    # ---- S2: declared concave but NOT flagged -> must be caught ----------------------
    # The recorded support height is the independent measurement that exposes this.
    s2 = make_solver(StaticCollider(
        collider_id="tray", collider_type="mesh", uri=str(TRAY),
        concave=False, support_z_m=FLOOR_Z))
    r2 = s2.self_check()
    c2 = report("S2 declared concave, unflagged", r2)
    out["S2_misdeclared_caught"] = bool(not r2["ok"])
    out["S2_detail"] = c2
    s2.disconnect()

    # ---- S3: correctly flagged concave -> must pass ----------------------------------
    s3 = make_solver(StaticCollider(
        collider_id="tray", collider_type="mesh", uri=str(TRAY),
        concave=True, support_z_m=FLOOR_Z))
    r3 = s3.self_check()
    c3 = report("S3 correctly flagged concave", r3)
    out["S3_flagged_ok"] = r3["ok"]
    out["S3_detail"] = c3
    out["S3_support_error_m"] = c3.get("support_height_error_m")
    s3.disconnect()

    # ---- S4: pin the vertices/indices route failure ----------------------------------
    print("-" * 86)
    cv = np.array([[a, b, c] for a in (-0.01, 0.01) for b in (-0.01, 0.01)
                   for c in (-0.01, 0.01)], float)
    cf = np.array([[0, 1, 3], [0, 3, 2], [4, 7, 5], [4, 6, 7], [0, 5, 1], [0, 4, 5],
                   [2, 3, 7], [2, 7, 6], [0, 6, 2], [0, 4, 6], [1, 5, 7], [1, 7, 3]],
                  np.int64)
    cid = pb.connect(pb.DIRECT)
    try:
        pb.setGravity(0, 0, -9.81, physicsClientId=cid)
        pb.setPhysicsEngineParameter(fixedTimeStep=1 / 480.0, physicsClientId=cid)
        ps = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                     physicsClientId=cid)
        pl = pb.createMultiBody(0, ps, basePosition=(0, 0, 0.5), physicsClientId=cid)
        cs = pb.createCollisionShape(pb.GEOM_MESH, vertices=cv.tolist(),
                                     indices=cf.ravel().tolist(), physicsClientId=cid)
        b = pb.createMultiBody(0.05, cs, basePosition=(0, 0, 0.52), physicsClientId=cid)
        for _ in range(480):
            pb.stepSimulation(physicsClientId=cid)
        pos, _ = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
        n = len(pb.getContactPoints(bodyA=b, bodyB=pl, physicsClientId=cid))
        fell = pos[2] < 0.4
        print(f"  vertices/indices route on a plane: z={pos[2]:.6f} contacts={n} "
              f"-> {'STILL BROKEN (documented)' if fell else 'now works'}")
        out["S4_vertices_indices_route_broken"] = bool(fell)
    finally:
        pb.disconnect(cid)

    print("=" * 86)
    print("=== VERDICT ===")
    ok = (out["S1_plane_ok"] and out["S2_misdeclared_caught"]
          and out["S3_flagged_ok"] and out["S4_vertices_indices_route_broken"])
    print(f"  plane passes                          : {out['S1_plane_ok']}")
    print(f"  mis-declared concave caught           : {out['S2_misdeclared_caught']}")
    print(f"  correctly flagged concave passes      : {out['S3_flagged_ok']} "
          f"(support error {(out['S3_support_error_m'] or 0)*1000:.4f} mm)")
    print(f"  route bug still reproducible          : "
          f"{out['S4_vertices_indices_route_broken']}")
    out["self_check_is_effective"] = bool(ok)
    p = SCENES / "self_check_effectiveness.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {p}")
    print(f"\nSELF-CHECK EFFECTIVENESS: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
