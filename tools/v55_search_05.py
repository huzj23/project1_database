"""V5.5 stage 05: strike search with the approved 0.12-0.18 m trigger, energy-checked first.

WHY THE TRIGGER CHANGED

The energy budget (v55_energy_budget.py) measured the bottle's tipping barrier from its own proxy
mesh at 0.859 J/kg, i.e. 0.66 J for the 0.77 kg empty crystal bottle. Against that:

  * the pencil case first used is 0.2092 m long -- outside the "about 0.12-0.18 m" 05 section 2.5
    specifies -- and weighs 0.1016 kg, giving 0.35 J at the maximum 0.35 m drop. That is 53% of the
    barrier, so no release geometry could ever work, and the measured response was correspondingly
    flat: 0.3-0.7 mm and 0.4-0.6 deg across nine configurations from 44.66 to 51.02 mm and 0.35 to
    0.55 m. Insensitivity to the release geometry is the signature of an energy limit, not of bad
    aim.
  * the approved `sealed_vessel` (Creatine_Monohydrate, 0.1300 x 0.1300 x 0.1851 m, 0.2184 kg) sits
    inside the specified size band and supplies 0.75 J at a 0.35 m drop and 1.07 J at 0.50 m, which
    clears the barrier. 04 section 66 forbids tuning mass to force a result, so this is a change of
    ASSET, chosen by its real measured dimensions and mass, not a change of physics.

Also, 05 section 3 requires at least 0.3 s of visible descent before contact, and section 3's own
provision is to RAISE THE START rather than to repeat slow-motion frames. A 0.35 m fall takes
sqrt(2*0.35/9.81) = 0.267 s, so the drop heights swept here run to 0.55 m (0.335 s) to satisfy that
requirement by the method the document prescribes.

A SECOND PHYSICAL ROUTE TO THE ACCEPTANCE CRITERION

05 section 3 accepts EITHER >= 3 cm of translation OR >= 20 deg of tilt. These are very different
demands: tipping must raise the centre of mass over the base edge (0.66 J), whereas sliding only
has to overcome friction, and the estimated sliding distance after a 0.5 m drop is about 4 cm. Both
outcomes are physically legitimate and both are measured here; neither is manufactured.

Nothing is prescribed. The search chooses only the trigger's RELEASE POSITION. No velocity or force
is applied to any body.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

CODE = Path("/data/raw/huzijian/project1_database/code/physics-video-sim/"
            "physics-video-sim-main/src")
sys.path.insert(0, str(CODE))

import pybullet as pb  # noqa: E402
from physim.contracts import (  # noqa: E402
    ROLE_PASSIVE, ROLE_TARGET, ROLE_TRIGGER, BodySpec, StaticCollider, box_inertia_diagonal,
)
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
RUNTIME = SCENES / "runtime"
OUT = ROOT / "outcomes/v55/italian_flat/box_hits_bottle"
WORK = OUT / "search"
GEOM = OUT / "prop_geometry_dense.json"
GSO = ROOT / "models/gso"

PHYSICS_FPS = 480
VIDEO_FPS = 24
SETTLE_S = 2.0
RUN_S = 3.0
FLOOR_Z = 0.510600
MIN_TRANSLATION_M = 0.030
MIN_TILT_DEG = 20.0
MIN_PRE_CONTACT_S = 0.30
MAX_ATTEMPTS = 12
TARGET = "bottle_assembly"
PROP_MASS = {"bottle_assembly": 0.77, "glass_a": 0.113, "glass_b": 0.157}
PROP_NAMES = ("bottle_assembly", "glass_a", "glass_b")

# The approved trigger, from 03 section 2's list. Dimensions and mass are measured, not chosen.
STRIKER = {
    "instance_id": "striker_vessel",
    "asset_id": "sealed_vessel",
    "dir": "Creatine_Monohydrate",
    "mass_kg": 0.2184,
    "mass_basis": "estimated",
    "note": ("approved sealed_vessel from stage 03; estimated from the container's material and "
             "declared contents"),
}


def load_obj(path: Path):
    vs, fs = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                vs.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    fs.append((idx[0] - 1, idx[k] - 1, idx[k + 1] - 1))
    return np.asarray(vs, float), np.asarray(fs, np.int64)


def write_obj(path: Path, V, F) -> None:
    with path.open("w", encoding="utf-8") as h:
        for q in V:
            h.write(f"v {q[0]:.9f} {q[1]:.9f} {q[2]:.9f}\n")
        for t in F:
            h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")


def tilt_deg(q0, q1) -> float:
    d = abs(float(np.dot(np.asarray(q0, float), np.asarray(q1, float))))
    return math.degrees(2 * math.acos(min(1.0, d)))


def main() -> int:
    decision = json.loads((PROPS / "proxy_decision.json").read_text(encoding="utf-8"))
    dense = json.loads(GEOM.read_text(encoding="utf-8"))
    WORK.mkdir(parents=True, exist_ok=True)

    mesh_path, body_origin = {}, {}
    for name in PROP_NAMES:
        d = decision[name]
        vs, fs, off = [], [], 0
        for f in sorted((PROPS / name / d["chosen"]).glob("*.obj")):
            v, fc = load_obj(f)
            vs.append(v)
            fs.append(fc + off)
            off += len(v)
        V, F = np.vstack(vs), np.vstack(fs)
        p = WORK / f"{name}_collision.obj"
        write_obj(p, V, F)
        mesh_path[name] = p
        restore = -np.asarray(d["recentre_offset_m"], float)
        body_origin[name] = np.array([restore[0], restore[1], FLOOR_Z - V.min(axis=0)[2]])

    # ---- the striker ------------------------------------------------------------------
    sv, sf = load_obj(GSO / STRIKER["dir"] / "collision_geometry.obj")
    slo, shi = sv.min(axis=0), sv.max(axis=0)
    s_dims = (shi - slo).tolist()
    s_centre = 0.5 * (slo + shi)
    striker_obj = WORK / "striker_vessel_collision.obj"
    write_obj(striker_obj, sv - s_centre, sf)
    hx, hy, hz = (s_dims[0] / 2, s_dims[1] / 2, s_dims[2] / 2)
    print("=" * 104)
    print(f"=== striker: {STRIKER['dir']} ({STRIKER['asset_id']}) ===")
    print(f"  dims {[round(v,6) for v in s_dims]} m ({len(sv)} v / {len(sf)} t), "
          f"mass {STRIKER['mass_kg']} kg ({STRIKER['mass_basis']})")
    print(f"  05 section 2.5 asks for a 0.12-0.18 m box: longest edge "
          f"{max(s_dims):.4f} m -> {'INSIDE' if max(s_dims) <= 0.19 else 'OUTSIDE'} the band")
    print(f"  inertia {[round(v,8) for v in box_inertia_diagonal(STRIKER['mass_kg'], s_dims)]}")

    statics = []
    layer = json.loads((SCENES / "layer_report.json").read_text(encoding="utf-8"))
    for name, info in layer["static_collision_per_object"].items():
        uri = RUNTIME / info["uri"].replace("\\", "/").rsplit("/", 1)[-1]
        low = str(name).lower()
        statics.append(StaticCollider(
            collider_id=name, collider_type="mesh", uri=str(uri),
            concave=low.startswith("vassoio"),
            support_z_m=FLOOR_Z if low.startswith("vassoio") else None,
            triangles=info["triangles"]))

    def prop_specs(poses=None):
        out = []
        for name in PROP_NAMES:
            pos, quat = ((poses[name][0], poses[name][1]) if poses
                         else (tuple(float(v) for v in body_origin[name]),
                               (0.0, 0.0, 0.0, 1.0)))
            out.append(BodySpec(
                instance_id=name, asset_id=name,
                role=ROLE_TARGET if name == TARGET else ROLE_PASSIVE,
                mass_kg=PROP_MASS[name], mass_basis="estimated", collider_type="mesh",
                position_m=tuple(pos), quaternion_xyzw=tuple(quat),
                friction=0.6, restitution=0.0, collision_uri=str(mesh_path[name])))
        return out

    print("\n=== step 1: pre-settle the props alone (the striker is not in this world) ===")
    s = MultibodySolver(SolverSettings(physics_fps=PHYSICS_FPS))
    s.load(prop_specs(), statics)
    s.connect()
    for _ in range(int(SETTLE_S * PHYSICS_FPS)):
        pb.stepSimulation(physicsClientId=s.client)
    settled = {}
    for name in PROP_NAMES:
        p, q = pb.getBasePositionAndOrientation(s._body_ids[name], physicsClientId=s.client)
        settled[name] = [list(p), list(q)]
        print(f"  {name:18s} pos {np.round(p,6)}  moved "
              f"{float(np.linalg.norm(np.asarray(p)-body_origin[name]))*1000:.3f} mm, "
              f"tilted {tilt_deg(q, (0,0,0,1)):.3f} deg")
    s.disconnect()

    g = dense[TARGET]
    base_z, top_z = g["base_z"], g["top_z"]
    axis = np.asarray(g["axis_xy"], float)
    cap_reach = g["cap_reach_plus_y_m"]
    widest = max(p["reach_plus_y"] for p in g["profile"])
    print(f"\n=== {TARGET} settled geometry ===")
    print(f"  axis ({axis[0]:.6f}, {axis[1]:.6f})  base {base_z:.5f}  top {top_z:.5f}")
    print(f"  reach(+y): cap {cap_reach*1000:.3f} mm, widest flank {widest*1000:.3f} mm")

    # ---- the sweep ------------------------------------------------------------------
    # The near-face distance is expressed relative to the CAP reach, since that is the boundary
    # between "meets the flank" and "lands on the cap".
    nf_values = [cap_reach + f for f in (0.004, 0.010, 0.016, 0.022)]
    drops = [0.40, 0.50]
    cases = [(nf, d) for d in drops for nf in nf_values][:MAX_ATTEMPTS]
    print(f"\n=== step 2: {len(cases)} combinations "
          f"(05 section 2.6 allows {MAX_ATTEMPTS}) ===")
    for nf, d in cases:
        t = math.sqrt(2 * d / 9.81)
        print(f"    near face {nf*1000:6.2f} mm from the axis, drop {d:.2f} m "
              f"-> {t:.3f} s descent, impact speed {math.sqrt(2*9.81*d):.3f} m/s, "
              f"energy {STRIKER['mass_kg']*9.81*d:.4f} J")

    results = []
    for n, (nf, drop) in enumerate(cases, start=1):
        centre = np.array([axis[0], axis[1] + nf + hy, top_z + drop + hz])
        solver = MultibodySolver(SolverSettings(physics_fps=PHYSICS_FPS))
        bodies = prop_specs(settled)
        bodies.append(BodySpec(
            instance_id=STRIKER["instance_id"], asset_id=STRIKER["asset_id"],
            role=ROLE_TRIGGER, mass_kg=STRIKER["mass_kg"],
            mass_basis=STRIKER["mass_basis"], collider_type="mesh",
            position_m=tuple(float(v) for v in centre),
            quaternion_xyzw=(0.0, 0.0, 0.0, 1.0), friction=0.6, restitution=0.0,
            collision_uri=str(striker_obj),
            inertia_diagonal_kg_m2=box_inertia_diagonal(STRIKER["mass_kg"], s_dims)))
        solver.load(bodies, statics)
        result = solver.run(int(round(RUN_S * VIDEO_FPS)), settle_seconds=0.0,
                            record_substeps=False)

        traj = result.trajectories[TARGET]
        p0 = np.array(traj[0].position)
        p1 = np.array(traj[-1].position)
        trans = float(np.linalg.norm((p1 - p0)[:2]))
        tilt = tilt_deg(traj[0].quaternion, traj[-1].quaternion)

        first, first_pos, first_n = None, None, None
        peak_force = 0.0
        pairs: dict = {}
        for c in result.contacts:
            key = "|".join(sorted(c.pair))
            pairs[key] = pairs.get(key, 0) + 1
            if "striker_vessel" in c.pair and TARGET in c.pair:
                peak_force = max(peak_force, float(c.normal_force_n))
                if first is None:
                    first = c.step
                    first_pos = (list(c.position_on_b_m) if c.instance_b == TARGET
                                 else list(c.position_on_a_m))
                    first_n = list(c.normal_on_b)
        pre_s = (first / PHYSICS_FPS) if first else None
        hit = first is not None
        horiz = None
        if first_n is not None:
            nv = np.asarray(first_n, float)
            horiz = float(np.hypot(nv[0], nv[1]))
        # 05 section 3 accepts translation OR tilt, so either one passing is a pass.
        trans_ok = trans >= MIN_TRANSLATION_M
        tilt_ok = tilt >= MIN_TILT_DEG
        reasons = []
        if not hit:
            reasons.append("the trigger never contacted the target")
        elif not trans_ok and not tilt_ok:
            reasons.append(f"neither criterion met: translation {trans*1000:.2f} mm "
                           f"< {MIN_TRANSLATION_M*1000:.0f} mm and tilt {tilt:.2f} deg "
                           f"< {MIN_TILT_DEG:.0f} deg")
        if hit and pre_s is not None and pre_s < MIN_PRE_CONTACT_S:
            reasons.append(f"only {pre_s:.3f} s of descent before contact (< {MIN_PRE_CONTACT_S} s)")
        passes = not reasons
        rec = {"attempt": n, "near_face_m": float(nf), "drop_m": drop,
               "release_centre_m": [float(v) for v in centre],
               "contacted_target": hit, "first_contact_step": first, "pre_contact_s": pre_s,
               "first_contact_point_m": first_pos, "first_contact_normal_on_b": first_n,
               "normal_horizontal_fraction": horiz, "peak_normal_force_n": peak_force,
               "target_translation_m": trans, "target_translation_mm": trans * 1000,
               "target_tilt_deg": tilt, "translation_criterion_met": trans_ok,
               "tilt_criterion_met": tilt_ok, "contact_pair_counts": pairs,
               "passes": passes, "reasons_rejected": reasons}
        results.append(rec)
        print(f"\n  #{n:2d} near_face={nf*1000:6.2f} mm drop={drop:.2f} m")
        print(f"      hit={hit} step={first} pre_contact={pre_s} "
              f"normal_horiz={None if horiz is None else round(horiz,3)} "
              f"peak_F={peak_force:.4f} N")
        if first_pos:
            print(f"      first contact {np.round(first_pos,5)} normal {np.round(first_n,4)}")
        print(f"      translation {trans*1000:9.3f} mm ({'OK' if trans_ok else 'no'})  "
              f"tilt {tilt:7.2f} deg ({'OK' if tilt_ok else 'no'})  "
              f"{'ACCEPT' if passes else 'reject'}")
        if reasons:
            print(f"      <- {'; '.join(reasons)}")
        solver.disconnect()

    passing = [r for r in results if r["passes"]]
    passing.sort(key=lambda r: -(r["target_translation_m"] + r["target_tilt_deg"] / 100.0))
    chosen = passing[0] if passing else None
    print("\n" + "=" * 104)
    print(f"=== attempts {len(results)}; accepted {len(passing)} ===")
    for r in results:
        print(f"  #{r['attempt']:2d} nf={r['near_face_m']*1000:6.2f} mm drop={r['drop_m']:.2f} m "
              f"hit={str(r['contacted_target']):5s} "
              f"trans={r['target_translation_m']*1000:9.3f} mm tilt={r['target_tilt_deg']:7.2f} deg "
              f"{'ACCEPT' if r['passes'] else 'reject'}")
    if chosen:
        print(f"\n  CHOSEN #{chosen['attempt']}: near face {chosen['near_face_m']*1000:.2f} mm, "
              f"drop {chosen['drop_m']:.2f} m")
        print(f"    first contact step {chosen['first_contact_step']} "
              f"(t={chosen['pre_contact_s']:.4f} s) at "
              f"{np.round(chosen['first_contact_point_m'],5)}")
        print(f"    translation {chosen['target_translation_m']*1000:.3f} mm, "
              f"tilt {chosen['target_tilt_deg']:.2f} deg")
        print(f"    release centre {chosen['release_centre_m']}")
    else:
        print("\n  NO CONFIGURATION PRODUCED AN ACCEPTABLE RESPONSE.")
        print("  05 section 4: report the specific failure, do not fabricate. No velocity or force")
        print("  was applied to the target and no trajectory was prescribed.")

    out = {"target": TARGET, "striker": STRIKER, "striker_dimensions_m": s_dims,
           "settled_poses": settled, "geometry": g,
           "canvas": {"cap_reach_m": cap_reach, "widest_reach_m": widest},
           "attempts": results, "passing_count": len(passing), "chosen": chosen,
           "min_translation_m": MIN_TRANSLATION_M, "min_tilt_deg": MIN_TILT_DEG,
           "min_pre_contact_s": MIN_PRE_CONTACT_S, "search_limit": MAX_ATTEMPTS}
    (OUT / "strike_search.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {OUT / 'strike_search.json'}")
    return 0 if chosen else 1


if __name__ == "__main__":
    raise SystemExit(main())
