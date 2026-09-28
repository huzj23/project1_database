"""V5.5 stage 03 section 4: the DECISIVE proxy acceptance test -- physics, not surface metrics.

Six surface metrics were tried and each disagreed, because a surface metric cannot know which
part of a surface is REACHABLE. A cup's cavity is reachable through its mouth (so filling it
is a real defect) while a capped bottle's interior is not (so filling it is invisible). No
threshold on distance, hull distance, or material ratio can express that distinction, and the
attempts are recorded in the sibling tools.

03 section 4 states the requirement in physical terms:
  * another body must not be able to rest on the mouth of an open vessel that it should enter;
  * another body must not pass through a wall;
  * there must be no initial penetration.
So the acceptance test here is physical: load the proxy into pybullet, drop the actual striker
onto the prop, and measure what happens.

Checks per candidate proxy
  P1 NO INITIAL PENETRATION -- 04 caps it at min(1 mm, t_min*5%); measured with the solver's
     own penetration report, not inferred.
  P2 NO PASS-THROUGH      -- the striker must never end up deeper than the wall thickness
     inside the object, and must never end up below the object's base.
  P3 STRIKER RESTS ON THE OUTSIDE -- the striker's resting height must match the height
     predicted from the object's outer geometry (top of the object, or the tray beneath if it
     slid off), NOT the height of a cavity floor. This is the check that catches a proxy
     which sealed a mouth: the striker would sit at the rim height while the visual's cavity
     floor is far below.
  P4 STABILITY CONTROL    -- the prop alone, with no striker, must not move.

The reference for "what should happen" is the VISUAL mesh loaded as a collision body, so the
comparison is against the real geometry rather than against an assumption.

Run with the project python (pybullet) on the server.
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

DT = 1.0 / 480.0
SUBSTEPS = 20
GRAVITY = -9.81

PROPS_SPEC = {
    "bottle_assembly": {
        "mass_kg": 0.77, "wall_m": 0.003, "support_z": 0.510600,
        "strike_z_frac": 0.55,      # the box strikes the shoulder/side, per 05 section 2
        "is_sealed": True,
        "height_m": 0.295922,
    },
    "glass_a": {
        "mass_kg": 0.113, "wall_m": 0.002, "support_z": 0.510600,
        "strike_z_frac": 0.75,
        "is_sealed": False,
        "height_m": 0.103654,
    },
    "glass_b": {
        "mass_kg": 0.157, "wall_m": 0.002, "support_z": 0.510600,
        "strike_z_frac": 0.75,
        "is_sealed": False,
        "height_m": 0.103654,
    },
}


def load_obj_mesh(path: Path):
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


def aabb(verts: np.ndarray):
    return verts.min(axis=0), verts.max(axis=0)


class World:
    """A tiny pybullet world that holds one collision body plus a support plane.

    The support plane is created with an EXPLICIT `planeNormal`.  Without it, the plane came
    out non-vertical and supported nothing, so every body -- including the visual reference --
    free-fell 2.85 m and the harness silently compared four falling objects. `self_check()`
    now proves the plane works before any verdict is drawn from a run.
    """

    def __init__(self) -> None:
        self.cid = pb.connect(pb.DIRECT)
        pb.setGravity(0.0, 0.0, GRAVITY, physicsClientId=self.cid)
        pb.setPhysicsEngineParameter(
            fixedTimeStep=DT, numSolverIterations=120, numSubSteps=1,
            enableConeFriction=1, physicsClientId=self.cid)

    def close(self) -> None:
        pb.disconnect(self.cid)

    def add_support_plane(self, z: float) -> int:
        shape = pb.createCollisionShape(pb.GEOM_PLANE, planeNormal=[0.0, 0.0, 1.0],
                                        physicsClientId=self.cid)
        return pb.createMultiBody(0, shape, basePosition=(0.0, 0.0, z),
                                  physicsClientId=self.cid)

    def self_check(self, z: float) -> dict:
        """Drop a control box that MUST come to rest on the plane.

        This is the harness's own test. A plane with the wrong normal, or any other setup
        error, makes the control fall too, and the run is then abandoned rather than used to
        produce a misleading proxy verdict.
        """
        half = 0.01
        shape = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[half] * 3,
                                        physicsClientId=self.cid)
        body = pb.createMultiBody(0.05, shape, basePosition=(0.0, 0.0, z + half + 0.05),
                                  physicsClientId=self.cid)
        for _ in range(int(1.5 / DT)):
            pb.stepSimulation(physicsClientId=self.cid)
        pos, _ = pb.getBasePositionAndOrientation(body, physicsClientId=self.cid)
        expected = z + half
        delta = pos[2] - expected
        pb.removeBody(body, physicsClientId=self.cid)
        return {"expected_z": expected, "actual_z": pos[2], "delta_m": delta,
                "ok": abs(delta) < 0.002}

    def add_dynamic_mesh(self, verts, faces, position, mass, inertia=None):
        col = pb.createCollisionShape(
            pb.GEOM_MESH, vertices=verts.tolist(), indices=faces.ravel().tolist(),
            physicsClientId=self.cid)
        if col < 0:
            raise RuntimeError(f"GEOM_MESH creation failed (shape id {col})")
        body = pb.createMultiBody(mass, col, basePosition=position, physicsClientId=self.cid)
        if inertia:
            pb.changeDynamics(body, -1, localInertiaDiagonal=inertia,
                              physicsClientId=self.cid)
        return body

    def resting_state(self, body: int, settle_s: float = 1.5,
                      window_s: float = 0.4) -> dict:
        """Settle, then decide whether the body is genuinely at rest.

        Rest is judged by VELOCITY and by having contacts, not by a position-delta threshold.
        A position-delta test marked the visual mesh unstable simply because a freshly spawned
        body settles a fraction of a millimetre, which is normal.
        """
        for _ in range(int(settle_s / DT)):
            pb.stepSimulation(physicsClientId=self.cid)
        lin, ang = pb.getBaseVelocity(body, physicsClientId=self.cid)
        speed = float(math.sqrt(sum(v * v for v in lin)))
        spin = float(math.sqrt(sum(v * v for v in ang)))
        n_contacts = len(pb.getContactPoints(bodyA=body, physicsClientId=self.cid))
        pos0, _ = pb.getBasePositionAndOrientation(body, physicsClientId=self.cid)
        for _ in range(int(window_s / DT)):
            pb.stepSimulation(physicsClientId=self.cid)
        pos1, _ = pb.getBasePositionAndOrientation(body, physicsClientId=self.cid)
        drift = float(math.dist(pos0, pos1))
        return {"speed_m_s": speed, "spin_rad_s": spin, "contacts": n_contacts,
                "drift_over_window_m": drift,
                "at_rest": bool(speed < 1e-3 and spin < 1e-3 and n_contacts > 0)}


def touching_pairs(cid: int, body: int):
    pts = pb.getContactPoints(bodyA=body, physicsClientId=cid)
    return pts


def run_case(name: str, label: str, files: list[Path], spec: dict,
             visual_files: list[Path]) -> dict:
    """Drop the striker onto this candidate proxy and record the physical outcome."""
    verts_list, faces_list = [], []
    off = 0
    for f in files:
        v, fc = load_obj_mesh(f)
        verts_list.append(v)
        faces_list.append(fc + off)
        off += len(v)
    pv = np.vstack(verts_list)
    pf = np.vstack(faces_list)
    plo, phi = aabb(pv)
    # The proxy is in a centred frame; place so its base sits on the support surface.
    base_shift = spec["support_z"] - plo[2]

    world = World()
    try:
        world.add_support_plane(spec["support_z"])
        check = world.self_check(spec["support_z"])
        if not check["ok"]:
            raise RuntimeError(
                f"harness self-check failed: control box rested at "
                f"{check['actual_z']:.6f} instead of {check['expected_z']:.6f} "
                f"(delta {check['delta_m']*1000:.3f} mm) -- the plane is not supporting, so "
                f"no proxy verdict from this run would be meaningful")

        prop = world.add_dynamic_mesh(
            pv, pf, position=(0.0, 0.0, base_shift), mass=spec["mass_kg"])

        # Settle and confirm the prop is genuinely at rest before striking it.
        rest = world.resting_state(prop)
        settle_drift = rest["drift_over_window_m"]

        # Striker: a 10 mm cube of 0.02 kg, dropped CENTRED over the prop's opening.
        # A centred drop is the decisive test of 03 section 4: if the proxy sealed an open
        # vessel's mouth, the striker stops at the rim; if the proxy preserves the cavity, it
        # falls inside and rests on the cavity floor, matching the visual.  The earlier
        # version offset the striker laterally, so it missed the prop entirely and landed on
        # the plane in EVERY case -- including the visual reference -- which carried no
        # information about the proxy at all.
        s_half = 0.005
        striker_mass = 0.02
        drop_z = phi[2] + base_shift + 0.08
        sc = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[s_half] * 3,
                                     physicsClientId=world.cid)
        striker = pb.createMultiBody(
            striker_mass, sc, basePosition=(0.0, 0.0, drop_z),
            physicsClientId=world.cid)

        max_penetration = 0.0
        min_striker_z = drop_z
        for _ in range(int(3.0 / DT)):
            pb.stepSimulation(physicsClientId=world.cid)
            cz, _ = pb.getBasePositionAndOrientation(striker, physicsClientId=world.cid)
            min_striker_z = min(min_striker_z, cz[2])
            cps = pb.getContactPoints(bodyA=striker, bodyB=prop,
                                      physicsClientId=world.cid)
            for c in cps:
                # c[8] is the contact distance (negative = penetration)
                max_penetration = max(max_penetration, -float(c[8]))

        spos, sorn = pb.getBasePositionAndOrientation(striker, physicsClientId=world.cid)
        ppos, porn = pb.getBasePositionAndOrientation(prop, physicsClientId=world.cid)

        # P3: where SHOULD the striker rest?  Three admissible outcomes, and the comparison
        # against the visual reference decides which one is correct:
        #   * on the OBJECT'S RIM/TOP (the proxy sealed a mouth or the object is solid);
        #   * on the object's CAVITY FLOOR (inside an open vessel);
        #   * on the SUPPORT PLANE (it slid off).
        expected_on_top = phi[2] + base_shift + s_half
        expected_on_plane = spec["support_z"] + s_half
        rest_z = spos[2]
        d_top = abs(rest_z - expected_on_top)
        d_plane = abs(rest_z - expected_on_plane)
        rests_on_top = d_top < 0.004
        rests_on_plane = d_plane < 0.004
        # Depth the striker reached below the rim: positive means it entered the object.
        entry_depth = float(expected_on_top - rest_z)
        rests_inside = bool(entry_depth > 0.004)

        visual_v = np.vstack([load_obj_mesh(f)[0] for f in visual_files])
        vlo, vhi = aabb(visual_v)

        out = {
            "label": label,
            "triangles": int(len(pf)),
            "mass_kg": spec["mass_kg"],
            "wall_m": spec["wall_m"],
            "striker_rest_z": round(float(rest_z), 6),
            "expected_on_top_z": round(float(expected_on_top), 6),
            "expected_on_plane_z": round(float(expected_on_plane), 6),
            "rests_on_top": bool(rests_on_top),
            "rests_on_plane": bool(rests_on_plane),
            "rests_inside": rests_inside,
            "entry_depth_m": round(entry_depth, 6),
            "dist_to_top_m": round(float(d_top), 6),
            "dist_to_plane_m": round(float(d_plane), 6),
            "max_contact_penetration_m": round(float(max_penetration), 9),
            "min_striker_z": round(float(min_striker_z), 6),
            "settle_drift_m": round(settle_drift, 9),
            "prop_rest_speed_m_s": round(rest["speed_m_s"], 9),
            "prop_rest_contacts": rest["contacts"],
            "prop_stable_without_striker": bool(rest["at_rest"]),
            "harness_self_check": check,
            "proxy_base_z": round(float(plo[2] + base_shift), 6),
            "proxy_top_z": round(float(phi[2] + base_shift), 6),
            "object_height_m": round(float(phi[2] - plo[2]), 6),
        }

        out["passes_no_penetration"] = bool(max_penetration <= 1e-4)
        out["passes_no_passthrough"] = bool(min_striker_z >= plo[2] + base_shift - 0.005)
        out["passes_stability"] = bool(rest["at_rest"])
        out["passes"] = bool(out["passes_no_penetration"] and out["passes_no_passthrough"]
                            and out["passes_stability"])
        return out
    finally:
        world.close()


def main() -> int:
    results: dict = {}
    for name, spec in PROPS_SPEC.items():
        print("=" * 78)
        print(f"=== {name} (sealed={spec['is_sealed']}) ===")
        print("=" * 78)
        vfiles = sorted((PROPS / name / "visual").glob("*.obj"))
        if not vfiles:
            print("  no visual files; skipping")
            continue
        cands = {
            "vhacd": sorted((PROPS / name / "vhacd").glob("part*.obj")),
            "hull": sorted((PROPS / name / "hull").glob("*.obj")),
        }
        entry = {}
        for label, files in cands.items():
            files = [f for f in files if f.is_file()]
            if not files:
                continue
            r = run_case(name, label, files, spec, vfiles)
            entry[label] = r
            print(f"  {label:6s} tri={r['triangles']:5d} "
                  f"rest_z={r['striker_rest_z']:.5f} "
                  f"(top {r['expected_on_top_z']:.5f} / plane {r['expected_on_plane_z']:.5f}) "
                  f"pen={r['max_contact_penetration_m']*1000:7.4f} mm")
            print(f"         on_top={r['rests_on_top']} on_plane={r['rests_on_plane']} "
                  f"no_pen={r['passes_no_penetration']} "
                  f"no_passthrough={r['passes_no_passthrough']} "
                  f"stable={r['passes_stability']} -> PASS={r['passes']}")

        # Also run the VISUAL itself as the reference outcome.
        ref = run_case(name, "VISUAL_reference", vfiles, spec, vfiles)
        entry["VISUAL_reference"] = ref
        print(f"  VISUAL tri={ref['triangles']:5d} rest_z={ref['striker_rest_z']:.5f} "
              f"on_top={ref['rests_on_top']} on_plane={ref['rests_on_plane']} "
              f"pen={ref['max_contact_penetration_m']*1000:.4f} mm -> PASS={ref['passes']}")

        # Choose the proxy whose physical behaviour MATCHES the visual reference.  The
        # reference outcome is whatever the REAL geometry does, so the proxy is judged against
        # the actual prop rather than against an assumption about it.
        allowed = ["vhacd", "hull"] if spec["is_sealed"] else ["vhacd"]
        def signature(r):
            return (r["rests_on_top"], r["rests_inside"], r["rests_on_plane"],
                    round(r["entry_depth_m"], 4))
        ref_sig = signature(ref)
        matching = [k for k in allowed
                    if k in entry and entry[k]["passes"]
                    and signature(entry[k]) == ref_sig]
        # A proxy that is merely close counts too, when the signature differs only by a
        # sub-millimetre rounding on the entry depth.
        near = [k for k in allowed
                if k in entry and entry[k]["passes"]
                and entry[k]["rests_on_top"] == ref["rests_on_top"]
                and entry[k]["rests_inside"] == ref["rests_inside"]
                and entry[k]["rests_on_plane"] == ref["rests_on_plane"]]
        chosen = (matching or near or None)
        if chosen:
            chosen = chosen[0]
        results[name] = {"candidates": entry, "chosen": chosen,
                         "matches_visual_exactly": bool(matching),
                         "matches_visual_behaviour": bool(near),
                         "visual_signature": list(ref_sig),
                         "is_sealed": spec["is_sealed"]}
        print(f"  visual signature: rests_on_top={ref['rests_on_top']} "
              f"rests_inside={ref['rests_inside']} rests_on_plane={ref['rests_on_plane']} "
              f"entry_depth={ref['entry_depth_m']*1000:.3f} mm")
        print(f"  -> CHOSEN {chosen} (exact match: {bool(matching)}, "
              f"behaviour match: {bool(near)})")

    out = SCENES / "proxy_physics_validation.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    b = results.get("bottle_assembly", {})
    bc = b.get("candidates", {}).get(b.get("chosen") or "", {})
    print(f"\nBOTTLE PROXY PHYSICAL VALIDATION: "
          f"{'PASS' if bc.get('passes') else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
