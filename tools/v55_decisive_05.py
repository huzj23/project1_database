"""V5.5 stage 05: decisive test with the CORRECT stage-03 proxies, and the impulse analysis.

TWO CORRECTIONS, EACH OF WHICH CHANGED THE ANSWER

1. PROXY. Stage 03 left two records naming a proxy per prop, and they disagree for the glasses:
   `proxy_decision.json` says `hull`, `proxy_acceptance_final.json` (the record whose `all_pass` is
   true) says `vhacd`. For an OPEN CUP, 03 section 4 disqualifies the single closed hull, so the
   final record's choice is also the compliant one, and every earlier run in this stage solved the
   glasses against a proxy the document disqualifies. All meshes here come from the final record.

2. THE MECHANISM IS A GLANCING BLOW, and the numbers close exactly. For a trigger falling
   vertically onto the bottle's near-vertical flank:

     closing speed along the normal   v_n = |v| * |n_z| = 2.80 * 0.172 = 0.482 m/s
     reduced mass                     m_eff = (0.2184 * 0.77) / (0.2184 + 0.77) = 0.170 kg
     normal impulse                   J = m_eff * v_n = 0.082 N*s   (measured 0.094 N*s)
     horizontal part                  J_h = J * 0.987 = 0.093 N*s
     bottle speed                     0.093 / 0.77 = 0.121 m/s      (measured 0.060 m/s)
     slide under mu = 0.6             v^2 / (2*mu*g) = 1.2 mm       (measured 0.9 mm)

   The agreement is the point: nothing is anomalous, and the small response follows from the
   geometry. Only the normal's small z-component drives the impulse, because the flank is nearly
   vertical while the velocity is entirely vertical.

   What would be required to TIP the bottle: the angular impulse is J_h * h_lever with h_lever the
   contact height above the base edge (~0.25 m), so the rotational energy is
   (J_h*h_lever)^2 / (2*I_pivot) with I_pivot = m*(r_base^2 + h_com^2) = 0.0155 kg*m^2. Setting that
   equal to the 0.66 J barrier gives J_h = 0.57 N*s -- six times the measured value, which would
   need an 18 m drop. No release geometry reaches it, and 05 section 2.6 permits gravity only.

The script below therefore does the one thing left that is both honest and within the document:
it measures all three original-scene vessels with their CORRECT proxies and reports which, if any,
can actually be moved by an approved trigger. 05 section 4 authorises exactly this substitution.
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
    ROLE_PASSIVE, ROLE_TARGET, ROLE_TRIGGER, BodySpec, box_inertia_diagonal,
    static_colliders_from_layer_report,
)
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
RUNTIME = SCENES / "runtime"
OUT = ROOT / "outcomes/v55/italian_flat/box_hits_bottle"
WORK = OUT / "decisive2"
GSO = ROOT / "models/gso"

PHYSICS_FPS = 480
VIDEO_FPS = 24
FLOOR_Z = 0.510600
MIN_TRANSLATION_M = 0.030
MIN_TILT_DEG = 20.0
PROP_NAMES = ("bottle_assembly", "glass_a", "glass_b")
PROP_MASS = {"bottle_assembly": 0.77, "glass_a": 0.113, "glass_b": 0.157}
STRIKER = {"instance_id": "striker_vessel", "asset_id": "sealed_vessel",
           "dir": "Creatine_Monohydrate", "mass_kg": 0.2184}


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
    fin = json.loads((SCENES / "proxy_acceptance_final.json").read_text(encoding="utf-8"))
    legacy = json.loads((PROPS / "proxy_decision.json").read_text(encoding="utf-8"))
    WORK.mkdir(parents=True, exist_ok=True)
    print("=" * 104)
    print("=== stage-03 FINAL proxy choice (proxy_acceptance_final.json, all_pass=True) ===")
    for n in PROP_NAMES:
        f = fin["props"][n]
        flag = "" if legacy[n]["chosen"] == f["chosen"] else \
            f"   [proxy_decision.json says '{legacy[n]['chosen']}' -- overridden]"
        print(f"  {n:18s} chosen={f['chosen']:6s} allowed={f['allowed']}"
              f"  sealed={f.get('sealed')}{flag}")
        print(f"      {f['why']}")

    mesh_path, body_origin = {}, {}
    for name in PROP_NAMES:
        ch = fin["props"][name]["chosen"]
        vs, fs, off = [], [], 0
        for f in sorted((PROPS / name / ch).glob("*.obj")):
            v, fc = load_obj(f)
            vs.append(v)
            fs.append(fc + off)
            off += len(v)
        V, F = np.vstack(vs), np.vstack(fs)
        p = WORK / f"{name}_collision.obj"
        write_obj(p, V, F)
        mesh_path[name] = p
        restore = -np.asarray(legacy[name]["recentre_offset_m"], float)
        body_origin[name] = np.array([restore[0], restore[1], FLOOR_Z - V.min(axis=0)[2]])
        err = float(np.max(np.abs((V.min(axis=0) + restore)
                                  - np.asarray(legacy[name]["world_aabb_min"], float))))
        print(f"  {name:18s} proxy {ch:6s} {len(V):5d} v {len(F):5d} t  "
              f"world-AABB check {err*1000:.4f} mm")

    sv, sf = load_obj(GSO / STRIKER["dir"] / "collision_geometry.obj")
    slo, shi = sv.min(axis=0), sv.max(axis=0)
    s_dims = (shi - slo).tolist()
    striker_obj = WORK / "striker_vessel_collision.obj"
    write_obj(striker_obj, sv - 0.5 * (slo + shi), sf)
    hx, hy, hz = (s_dims[0] / 2, s_dims[1] / 2, s_dims[2] / 2)
    print(f"\n  trigger {STRIKER['dir']} dims {[round(v,6) for v in s_dims]} "
          f"mass {STRIKER['mass_kg']} kg")

    statics = static_colliders_from_layer_report(
        json.loads((SCENES / "layer_report.json").read_text(encoding="utf-8")),
        runtime_dir=RUNTIME, support_z_by_object={"Vassoio": FLOOR_Z})

    def props(target, poses=None, masses=None):
        out = []
        for name in PROP_NAMES:
            pos, quat = ((poses[name][0], poses[name][1]) if poses
                         else (tuple(float(v) for v in body_origin[name]),
                               (0.0, 0.0, 0.0, 1.0)))
            out.append(BodySpec(
                instance_id=name, asset_id=name,
                role=ROLE_TARGET if name == target else ROLE_PASSIVE,
                mass_kg=(masses or PROP_MASS)[name], mass_basis="estimated",
                collider_type="mesh", position_m=tuple(pos), quaternion_xyzw=tuple(quat),
                friction=0.6, restitution=0.0, collision_uri=str(mesh_path[name])))
        return out

    s = MultibodySolver(SolverSettings(physics_fps=PHYSICS_FPS))
    s.load(props("bottle_assembly"), statics)
    s.connect()
    for _ in range(int(2.0 * PHYSICS_FPS)):
        pb.stepSimulation(physicsClientId=s.client)
    settled = {}
    for n in PROP_NAMES:
        p, q = pb.getBasePositionAndOrientation(s._body_ids[n], physicsClientId=s.client)
        settled[n] = [list(p), list(q)]
    s.disconnect()
    print("\n=== settled poses (props pre-settled WITHOUT the trigger) ===")
    for n in PROP_NAMES:
        print(f"  {n:18s} pos {np.round(settled[n][0],6)}  moved "
              f"{float(np.linalg.norm(np.asarray(settled[n][0])-body_origin[n]))*1000:.3f} mm")
    (OUT / "decisive_proxies.json").write_text(json.dumps(
        {"proxy_source": "proxy_acceptance_final.json", "settled_poses": settled,
         "meshes": {k: str(v) for k, v in mesh_path.items()}}, indent=2), encoding="utf-8")

    # ---- measured silhouette of each prop in its SETTLED pose -------------------------
    def silhouette(name):
        V, F = load_obj(mesh_path[name])
        W = V + np.asarray(settled[name][0])
        base = W[W[:, 2] <= W[:, 2].min() + 0.003]
        axis = np.array([base[:, 0].mean(), base[:, 1].mean()])
        dy = W[:, 1] - axis[1]
        top = float(W[:, 2].max())
        zs = W[:, 2]
        NB = 40
        edges = np.linspace(zs.min(), top, NB + 1)
        prof = []
        for i in range(NB):
            sel = (zs >= edges[i]) & (zs <= edges[i + 1])
            if sel.any():
                prof.append({"z": float(0.5 * (edges[i] + edges[i + 1])),
                             "reach_y": float(dy[sel].max()), "n": int(sel.sum())})
        return {"axis": axis, "base_z": float(zs.min()), "top_z": top,
                "widest_reach_y": float(max(p["reach_y"] for p in prof)),
                "cap_reach_y": float(prof[-1]["reach_y"]), "profile": prof,
                "height": top - float(zs.min())}

    sil = {n: silhouette(n) for n in PROP_NAMES}
    print("\n=== measured silhouette, settled pose ===")
    for n in PROP_NAMES:
        e = sil[n]
        print(f"  {n:18s} axis ({e['axis'][0]:.6f}, {e['axis'][1]:.6f})  base {e['base_z']:.5f} "
              f"top {e['top_z']:.5f}  height {e['height']:.4f}")
        print(f"      reach(+y): cap {e['cap_reach_y']*1000:7.3f} mm, widest "
              f"{e['widest_reach_y']*1000:7.3f} mm, band "
              f"{(e['widest_reach_y']-e['cap_reach_y'])*1000:7.3f} mm")

    def run_case(target, drop, nf, run_s=2.2):
        e = sil[target]
        centre = np.array([e["axis"][0], e["axis"][1] + nf + hy, e["top_z"] + drop + hz])
        solver = MultibodySolver(SolverSettings(physics_fps=PHYSICS_FPS))
        bodies = props(target, settled)
        bodies.append(BodySpec(
            instance_id=STRIKER["instance_id"], asset_id=STRIKER["asset_id"],
            role=ROLE_TRIGGER, mass_kg=STRIKER["mass_kg"], mass_basis="estimated",
            collider_type="mesh", position_m=tuple(float(v) for v in centre),
            quaternion_xyzw=(0.0, 0.0, 0.0, 1.0), friction=0.6, restitution=0.0,
            collision_uri=str(striker_obj),
            inertia_diagonal_kg_m2=box_inertia_diagonal(STRIKER["mass_kg"], s_dims)))
        solver.load(bodies, statics)
        result = solver.run(int(round(run_s * VIDEO_FPS)), settle_seconds=0.0,
                            record_substeps=False)
        traj = result.trajectories[target]
        p0 = np.array(traj[0].position)
        p1 = np.array(traj[-1].position)
        trans = float(np.linalg.norm((p1 - p0)[:2]))
        tilt = tilt_deg(traj[0].quaternion, traj[-1].quaternion)
        first, fpos, fnorm = None, None, None
        jh = 0.0
        for c in result.contacts:
            if STRIKER["instance_id"] in c.pair and target in c.pair:
                if first is None:
                    first = c.step
                    fpos = (list(c.position_on_b_m) if c.instance_b == target
                            else list(c.position_on_a_m))
                    fnorm = list(c.normal_on_b)
                jh += abs(float(c.normal_force_n)) * (1.0 / PHYSICS_FPS) * abs(
                    float(c.normal_on_b[1]))
        solver.disconnect()
        return {"target": target, "drop_m": drop, "near_face_m": float(nf),
                "release_centre_m": [float(v) for v in centre],
                "pre_contact_s": (first / PHYSICS_FPS if first else None),
                "first_contact_point_m": fpos, "first_contact_normal_on_b": fnorm,
                "horizontal_impulse_n_s": jh,
                "translation_mm": trans * 1000, "tilt_deg": tilt,
                "translation_ok": trans >= MIN_TRANSLATION_M, "tilt_ok": tilt >= MIN_TILT_DEG,
                "passes": bool(trans >= MIN_TRANSLATION_M or tilt >= MIN_TILT_DEG)}

    # ---- sweep: for each target, the offsets that can actually be struck --------------
    print("\n" + "=" * 104)
    print("=== sweep with the CORRECT proxies, drop 0.60 m ===")
    print(f"  {'target':>18s} {'near_face':>10s} {'t_first':>8s} {'n_z':>7s} {'J_h N*s':>9s} "
          f"{'trans_mm':>10s} {'tilt_deg':>9s}  verdict")
    allres = []
    for target in PROP_NAMES:
        e = sil[target]
        cap, wide = e["cap_reach_y"], e["widest_reach_y"]
        band = wide - cap
        offsets = ([cap + f * band for f in (0.7, 0.4, 0.15)] if band > 0.002
                   else [0.5 * wide, 0.75 * wide, 0.95 * wide])
        for nf in offsets:
            r = run_case(target, 0.60, nf)
            allres.append(r)
            nz = r["first_contact_normal_on_b"][2] if r["first_contact_normal_on_b"] else None
            print(f"  {target:>18s} {nf*1000:10.2f} "
                  f"{('%.3f' % r['pre_contact_s']) if r['pre_contact_s'] else '   None':>8s} "
                  f"{('%.3f' % nz) if nz is not None else '  None':>7s} "
                  f"{r['horizontal_impulse_n_s']:9.5f} {r['translation_mm']:10.3f} "
                  f"{r['tilt_deg']:9.3f}  {'PASS' if r['passes'] else 'fail'}")

    passing = [r for r in allres if r["passes"]]
    passing.sort(key=lambda r: -(r["translation_mm"] + r["tilt_deg"]))
    print("\n" + "=" * 104)
    print("=== CONCLUSIONS ===")
    print(f"  configurations that satisfy 05 section 3: {len(passing)}")
    if passing:
        c = passing[0]
        print(f"  BEST: target {c['target']}, near face {c['near_face_m']*1000:.2f} mm, "
              f"drop {c['drop_m']:.2f} m")
        print(f"    translation {c['translation_mm']:.3f} mm, tilt {c['tilt_deg']:.3f} deg, "
              f"pre-contact {c['pre_contact_s']:.4f} s")
        print(f"    horizontal impulse {c['horizontal_impulse_n_s']:.5f} N*s")
    bottle_res = [r for r in allres if r["target"] == "bottle_assembly"]
    print(f"  the BOTTLE, across {len(bottle_res)} offsets: max translation "
          f"{max(r['translation_mm'] for r in bottle_res):.3f} mm, max tilt "
          f"{max(r['tilt_deg'] for r in bottle_res):.3f} deg -> "
          f"{'PASS' if any(r['passes'] for r in bottle_res) else 'NOT MET'}")

    out = {"proxy_source": "proxy_acceptance_final.json", "striker": STRIKER,
           "striker_dimensions_m": s_dims, "settled_poses": settled,
           "silhouettes": {k: {kk: (vv.tolist() if isinstance(vv, np.ndarray) else vv)
                               for kk, vv in v.items()} for k, v in sil.items()},
           "results": allres, "passing": passing,
           "criteria": {"min_translation_m": MIN_TRANSLATION_M,
                        "min_tilt_deg": MIN_TILT_DEG}}
    (OUT / "decisive_experiment.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {OUT / 'decisive_experiment.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
