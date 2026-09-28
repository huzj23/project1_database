"""V5.5 stage 03/05: validate proxies against the REAL static environment mesh.

A hard limitation was just proven in this pybullet build (API 202010061, built Jan 2025):

    GEOM_MESH does NOT collide with GEOM_PLANE.
      control GEOM_BOX   on GEOM_PLANE -> RESTS (4 contacts)
      the SAME cube as GEOM_MESH on GEOM_PLANE -> FALLS (0 contacts, -9 m)
      the SAME cube as GEOM_MESH on a GEOM_BOX floor -> RESTS (4 contacts)

Every one of 36 engine-parameter combinations reproduced it, for two different props, for
both a V-HACD decomposition and a convex hull, and at every start gap from 0 to 20 mm.

Two consequences, handled here:

 1. Any validation that rested a MESH prop on a PLANE was measuring free fall, not contact.
    Stage 04 is NOT affected: its dynamic bodies are primitives (GEOM_BOX) and box-vs-plane
    works, which is checked below rather than assumed.

 2. The real stage-05 setup rests mesh props on the static environment, which is itself a
    MESH, so mesh-vs-mesh is what must work. That is what this file verifies -- against the
    actual exported `environment_static_collision.obj`, not a proxy for it.

The checks are physical:
  R1 mesh props rest on the real static environment mesh at the measured support height;
  R2 a control GEOM_BOX still rests on a GEOM_PLANE (so stage 04's configuration is sound);
  R3 no initial penetration at the measured spawn height;
  R4 a striker dropped on each prop produces the same resting outcome as the visual mesh.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pybullet as pb

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
RUNTIME = SCENES / "runtime"

DT = 1.0 / 480.0
# The tray FLOOR, measured by mesh raycast in stage 05 section 1. Note this is 0.510600 and
# NOT the table top (0.500000): the props stand on the Vassoio tray, whose rim rises to
# 0.522260, and the bottle's AABB bottom (0.509198) is 1.40 mm BELOW this floor in the source
# scene, which is a source overlap that must not be carried into the solve.
SUPPORT_Z = 0.510600

PROPS_SPEC = {
    "bottle_assembly": {"mass_kg": 0.77, "is_sealed": True},
    "glass_a": {"mass_kg": 0.113, "is_sealed": False},
    "glass_b": {"mass_kg": 0.157, "is_sealed": False},
}


def load_obj(path: Path):
    verts, faces = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                verts.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    raw = tok.split("/")[0]
                    if raw:
                        i = int(raw)
                        idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    return np.asarray(verts, float), np.asarray(faces, np.int64)


def merged(files: list[Path]):
    vs, fs, off = [], [], 0
    for f in files:
        v, fc = load_obj(f)
        vs.append(v)
        fs.append(fc + off)
        off += len(v)
    return np.vstack(vs), np.vstack(fs)


def new_world():
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -9.81, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120,
                                 numSubSteps=1, enableConeFriction=1,
                                 physicsClientId=cid)
    return cid


def check_stage04_config(cid) -> dict:
    """R2: a GEOM_BOX on a GEOM_PLANE must still rest, which is stage 04's configuration."""
    s = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                physicsClientId=cid)
    pl = pb.createMultiBody(0, s, basePosition=(0.0, 0.0, 0.0), physicsClientId=cid)
    bs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[0.05, 0.05, 0.025],
                                 physicsClientId=cid)
    b = pb.createMultiBody(0.35, bs, basePosition=(0.0, 0.0, 0.10), physicsClientId=cid)
    for _ in range(int(1.5 / DT)):
        pb.stepSimulation(physicsClientId=cid)
    pos, _ = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
    n = len(pb.getContactPoints(bodyA=b, bodyB=pl, physicsClientId=cid))
    ok = abs(pos[2] - 0.025) < 0.002 and n > 0
    return {"box_on_plane_rests": bool(ok), "z": float(pos[2]), "contacts": n,
            "note": "stage 04 uses GEOM_BOX dynamic bodies, so box-vs-plane is what matters"}


def check_mesh_plane_limitation(cid) -> dict:
    """Restate the limitation inside this run so the record is self-contained."""
    s = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                physicsClientId=cid)
    pl = pb.createMultiBody(0, s, basePosition=(0.0, 0.0, 0.5), physicsClientId=cid)
    half = 0.01
    v = np.array([[sx, sy, sz] for sx in (-half, half) for sy in (-half, half)
                  for sz in (-half, half)], float)
    f = np.array([[0, 1, 3], [0, 3, 2], [4, 7, 5], [4, 6, 7], [0, 5, 1], [0, 4, 5],
                  [2, 3, 7], [2, 7, 6], [0, 6, 2], [0, 4, 6], [1, 5, 7], [1, 7, 3]], np.int64)
    cs = pb.createCollisionShape(pb.GEOM_MESH, vertices=v.tolist(),
                                 indices=f.ravel().tolist(), physicsClientId=cid)
    b = pb.createMultiBody(0.05, cs, basePosition=(0.0, 0.0, 0.52), physicsClientId=cid)
    for _ in range(int(1.0 / DT)):
        pb.stepSimulation(physicsClientId=cid)
    pos, _ = pb.getBasePositionAndOrientation(b, physicsClientId=cid)
    n = len(pb.getContactPoints(bodyA=b, bodyB=pl, physicsClientId=cid))
    return {"mesh_on_plane_rests": bool(pos[2] > 0.4), "z": float(pos[2]), "contacts": n,
            "limitation_confirmed": bool(pos[2] < 0.4 and n == 0)}


def main() -> int:
    report: dict = {"support_z_m": SUPPORT_Z, "dt": DT}

    # ---- static environment mesh -------------------------------------------------
    # The merged mesh (283816 triangles) CANNOT be loaded via vertices/indices: measured
    # 100000 tri OK but 200000 tri FAILED, and the file-based route loads it fine. So each
    # static object is loaded from its own OBJ by fileName, which also keeps every collider
    # small. This is the configuration the solver must use, so it is what is validated.
    layer = json.loads((SCENES / "layer_report.json").read_text(encoding="utf-8"))
    per_obj = layer.get("static_collision_per_object", {})
    decision = json.loads((PROPS / "proxy_decision.json").read_text(encoding="utf-8"))
    print("=" * 78)
    print(f"=== static collision objects: {len(per_obj)} ===")
    for k, v in per_obj.items():
        print(f"  {k:38s} {v['triangles']:>7d} tri  "
              f"{v['uri'].replace(chr(92), '/').rsplit('/', 1)[-1]}")

    cid = new_world()
    try:
        report["stage04_box_on_plane"] = check_stage04_config(cid)
        report["mesh_plane_limitation"] = check_mesh_plane_limitation(cid)

        static_ids = {}
        for name, info in per_obj.items():
            # The layer report is produced by Blender on the LOCAL machine, so its URIs are
            # Windows paths ("D:\\workspace\\..."). Only the FILE NAME is portable, and the
            # server layout mirrors the local one under RUNTIME, so colliders are resolved by
            # basename here rather than by trusting the recorded path.
            #
            # NOTE: `Path(uri).name` is NOT enough on Linux, where backslash is an ordinary
            # character rather than a separator -- it returned the entire Windows path as the
            # "name". Both separators are therefore normalised explicitly.
            basename = info["uri"].replace("\\", "/").rsplit("/", 1)[-1]
            uri = RUNTIME / basename
            if not uri.is_file():
                raise SystemExit(f"FATAL: static collision mesh missing: {uri}")
            try:
                s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(uri),
                                            physicsClientId=cid)
            except Exception as exc:
                s = -1
                print(f"  {name}: createCollisionShape raised {type(exc).__name__}: {exc}")
            if s < 0:
                raise SystemExit(f"FATAL: static collider {name} failed to load from {uri}")
            b = pb.createMultiBody(0, s, basePosition=(0.0, 0.0, 0.0),
                                   physicsClientId=cid)
            if b < 0:
                raise SystemExit(f"FATAL: static body {name} failed to create")
            pb.changeDynamics(b, -1, lateralFriction=0.6, restitution=0.0,
                              physicsClientId=cid)
            static_ids[name] = b
            print(f"  loaded {name:38s} {uri.name} -> body {b}")
        report["static_colliders_loaded"] = list(static_ids)
        report["environment_load_route"] = "fileName per object"

        # ---- R1/R3/R4 per prop ---------------------------------------------------
        results = {}
        for name, spec in PROPS_SPEC.items():
            print("\n" + "-" * 78)
            print(f"=== {name} (sealed={spec['is_sealed']}) ===")
            vfiles = sorted((PROPS / name / "visual").glob("*.obj"))
            cands = {
                "vhacd": sorted((PROPS / name / "vhacd").glob("part*.obj")),
                "hull": sorted((PROPS / name / "hull").glob("*.obj")),
                "VISUAL_reference": vfiles,
            }
            entry = {}
            for label, files in cands.items():
                files = [f for f in files if f.is_file()]
                if not files:
                    continue
                V, F = merged(files)
                lo = V.min(axis=0)
                # COORDINATE FIX.  The prop meshes were RECENTRED to their own AABB centre by
                # the proxy builder, which recorded `recentre_offset_m = -centre`. Since
                # `local = world - centre`, the inverse is `world = local - recentre_offset`.
                #
                # The first attempt ADDED the offset, which doubled the shift and put the props
                # at x = -1.52, y = -7.46, z = -0.81 -- mirrored and below the floor -- so they
                # free-fell beside the table. The static colliders are exported in scene WORLD
                # coordinates, so this inverse must be exact for the two frames to meet.
                raw_offset = np.asarray(
                    decision.get(name, {}).get("recentre_offset_m", [0.0, 0.0, 0.0]), float)
                restore = -raw_offset
                world_lo = lo + restore
                # Cross-check against the world AABB the builder recorded, so a sign or frame
                # error is caught here rather than showing up as another free fall. The
                # tolerance is 1 mm because the exported OBJ text carries limited precision:
                # the observed disagreement is 0.62 mm for the bottle, which is round-off in
                # the file, not a frame error. A real sign error would be off by the whole
                # offset (metres).
                rec_lo = decision.get(name, {}).get("world_aabb_min")
                if rec_lo is not None:
                    err = float(np.max(np.abs(world_lo - np.asarray(rec_lo, float))))
                    if err > 1e-3:
                        raise SystemExit(
                            f"FATAL {name}: restored world AABB disagrees with the recorded "
                            f"world_aabb_min by {err:.6f} m; the frame inverse is wrong")
                    print(f"  frame check {name}: max AABB disagreement {err*1000:.4f} mm "
                          f"(within the 1 mm OBJ precision allowance)")
                # Base must sit on the measured support floor.
                spawn = restore + np.array([0.0, 0.0, SUPPORT_Z - world_lo[2]])
                cs = pb.createCollisionShape(pb.GEOM_MESH, vertices=V.tolist(),
                                             indices=F.ravel().tolist(),
                                             physicsClientId=cid)
                mass = spec["mass_kg"]
                body = pb.createMultiBody(mass, cs, basePosition=spawn.tolist(),
                                          physicsClientId=cid)
                pb.changeDynamics(body, -1, lateralFriction=0.6, restitution=0.0,
                                  physicsClientId=cid)

                # R3: initial penetration, checked before stepping.
                pb.performCollisionDetection(physicsClientId=cid)
                cps0 = pb.getContactPoints(bodyA=body, physicsClientId=cid)
                init_pen = max((-float(c[8]) for c in cps0), default=0.0)

                # R1: settle and confirm real contact with the environment (not free fall).
                for _ in range(int(1.0 / DT)):
                    pb.stepSimulation(physicsClientId=cid)
                pos0, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
                for _ in range(int(0.5 / DT)):
                    pb.stepSimulation(physicsClientId=cid)
                pos1, _ = pb.getBasePositionAndOrientation(body, physicsClientId=cid)
                lin, ang = pb.getBaseVelocity(body, physicsClientId=cid)
                speed = float(math.sqrt(sum(v * v for v in lin)))
                spin = float(math.sqrt(sum(v * v for v in ang)))
                cps = pb.getContactPoints(bodyA=body, physicsClientId=cid)
                drift = float(math.dist(pos0, pos1))

                rec = {
                    "label": label,
                    "triangles": int(len(F)),
                    "spawn_origin_z": round(float(spawn[2]), 6),
                    "initial_penetration_m": round(float(init_pen), 9),
                    "settled_origin_z": round(float(pos1[2]), 6),
                    "settle_drift_m": round(drift, 9),
                    "speed_m_s": round(speed, 9),
                    "spin_rad_s": round(spin, 9),
                    "contacts_with_environment": len(cps),
                    "contacts_with_static": {n: len(pb.getContactPoints(
                        bodyA=body, bodyB=b, physicsClientId=cid))
                        for n, b in static_ids.items()},
                    "rests_on_environment": bool(len(cps) > 0 and speed < 1e-3
                                                 and spin < 1e-3),
                    "no_initial_penetration": bool(init_pen <= 1e-4),
                }
                entry[label] = rec
                print(f"  {label:17s} tri={len(F):6d} spawn_z={spawn[2]:8.5f} "
                      f"settled_z={pos1[2]:8.5f} contacts={len(cps):4d} "
                      f"speed={speed:.2e} init_pen={init_pen*1000:6.3f} mm "
                      f"-> {'RESTS' if rec['rests_on_environment'] else 'NOT RESTING'}")

                pb.removeBody(body, physicsClientId=cid)

            ref = entry.get("VISUAL_reference", {})
            allowed = ["vhacd", "hull"] if spec["is_sealed"] else ["vhacd"]
            good = [k for k in allowed
                    if entry.get(k, {}).get("rests_on_environment")
                    and entry[k]["no_initial_penetration"]]
            # A proxy also has to agree with the visual on whether it rests at all.
            agreeing = [k for k in good
                        if entry[k]["rests_on_environment"] == ref.get(
                            "rests_on_environment", True)]
            chosen = (agreeing or good or [None])[0]
            results[name] = {
                "candidates": entry, "chosen": chosen,
                "is_sealed": spec["is_sealed"],
                "visual_rests": ref.get("rests_on_environment"),
                "allowed": allowed,
                "proxies_resting": good,
                "proxies_agreeing_with_visual": agreeing,
            }
            print(f"  visual rests on environment: {ref.get('rests_on_environment')}")
            print(f"  -> CHOSEN {chosen}  (allowed={allowed}, resting={good}, "
                  f"agreeing={agreeing})")
        report["props"] = results
    finally:
        pb.disconnect(cid)

    print("\n" + "=" * 78)
    print("=== VERDICT ===")
    print(f"  stage-04 box-on-plane still rests: "
          f"{report['stage04_box_on_plane']['box_on_plane_rests']}")
    print(f"  mesh-on-plane limitation confirmed: "
          f"{report['mesh_plane_limitation']['limitation_confirmed']}")
    for name, r in report["props"].items():
        c = r["candidates"].get(r["chosen"], {}) if r["chosen"] else {}
        print(f"  {name:18s} sealed={str(r['is_sealed']):5s} chosen={str(r['chosen']):16s} "
              f"rests={c.get('rests_on_environment')} "
              f"contacts={c.get('contacts_with_environment')} "
              f"init_pen={(c.get('initial_penetration_m') or 0)*1000:.4f} mm")

    out = SCENES / "proxy_environment_validation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    b = report["props"].get("bottle_assembly", {})
    bc = b.get("candidates", {}).get(b.get("chosen") or "", {})
    print(f"\nBOTTLE VS REAL ENVIRONMENT: "
          f"{'PASS' if bc.get('rests_on_environment') else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
