"""V5.5 stage 05: find the box offset by PHYSICS search, as 05 section 2.6 requires.

Why the geometric design was not enough, and why this is the right instrument:

The design placed the box's near face at `r(z*)` from the bottle's axis, where `r` was the MAXIMUM
RADIAL distance in that height band. But the quantity that decides a strike is the bottle's reach
ALONG THE APPROACH DIRECTION: measured from the real meshes, the bottle reaches 55.40 mm along +y
at its widest and only 33.47 mm at the intended contact height, while the design used 49.46 mm.
The box therefore descended past the bottle through a 16 mm gap and came to rest on the table
(z = 0.5646, i.e. its own bottom at the table top), with the bottle untouched.

A geometric proxy cannot settle this, because it has to predict a contact that depends on the
convex hull of two real meshes at a specific height. 05 section 2.6 explicitly provides for this:
at most 12 offset/height searches, each with its reason recorded. The physics is still solved
entirely by PyBullet -- this search chooses only the box's INITIAL RELEASE POSITION, which is an
initial condition, not a prescribed trajectory.

For each candidate the script reports, from the solver's own output:
  * whether the box contacted the bottle, and at which substep and height;
  * the bottle's translation and tilt in response;
  * the box's final resting height, which shows what it landed on.

A candidate is ACCEPTED only if the box contacts the bottle AND the bottle's response reaches 05's
acceptance thresholds (>= 30 mm translation OR >= 20 deg tilt). The reason every rejected
candidate failed is written out; the reasons are not inferred after the fact.
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

from physim.contracts import (  # noqa: E402
    ROLE_PASSIVE, ROLE_TARGET, ROLE_TRIGGER, BodySpec, StaticCollider, box_inertia_diagonal,
)
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
RUNTIME = SCENES / "runtime"
DESIGN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/design.json"
OUT = ROOT / "outcomes/v55/italian_flat/box_hits_bottle"
BUILD = ROOT / "models/gso/Big_Dot_Aqua_Pencil_Case"

PHYSICS_FPS = 480
VIDEO_FPS = 24
FLOOR_Z = 0.510600
MIN_TRANSLATION_M = 0.030
MIN_TILT_DEG = 20.0


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


def merged(files):
    vs, fs, off = [], [], 0
    for f in files:
        v, fc = load_obj(f)
        vs.append(v)
        fs.append(fc + off)
        off += len(v)
    return np.vstack(vs), np.vstack(fs)


def quat_angle_deg(a, b) -> float:
    """Rotation angle between two quaternions in the SAME convention (wxyz here)."""
    d = abs(float(np.dot(np.asarray(a, float), np.asarray(b, float))))
    return math.degrees(2 * math.acos(min(1.0, d)))


def main() -> int:
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    work = OUT / "search"
    work.mkdir(parents=True, exist_ok=True)

    # ---- the meshes ------------------------------------------------------------------
    decision = json.loads((PROPS / "proxy_decision.json").read_text(encoding="utf-8"))
    prop_files, prop_origin, prop_mesh = {}, {}, {}
    for name in ("bottle_assembly", "glass_a", "glass_b"):
        files = sorted((PROPS / name / decision[name]["chosen"]).glob("*.obj"))
        V, F = merged(files)
        p = work / f"{name}_collision.obj"
        with p.open("w", encoding="utf-8") as h:
            for q in V:
                h.write(f"v {q[0]:.9f} {q[1]:.9f} {q[2]:.9f}\n")
            for t in F:
                h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")
        restore = -np.asarray(decision[name]["recentre_offset_m"], float)
        prop_files[name] = p
        prop_mesh[name] = V
        prop_origin[name] = np.array([restore[0], restore[1],
                                      FLOOR_Z - V.min(axis=0)[2]])

    bv, bf = load_obj(BUILD / "collision_geometry.obj")
    blo, bhi = bv.min(axis=0), bv.max(axis=0)
    box_dims = (bhi - blo).tolist()
    bv_c = bv - 0.5 * (blo + bhi)
    box_obj = work / "striker_box_collision.obj"
    with box_obj.open("w", encoding="utf-8") as h:
        for q in bv_c:
            h.write(f"v {q[0]:.9f} {q[1]:.9f} {q[2]:.9f}\n")
        for t in bf:
            h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")

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

    # ---- the actual reach of the bottle along the approach direction -----------------
    # Measured from the world-space mesh, per height band, so the search starts from real numbers
    # instead of the radial maximum that misled the geometric design.
    axis = np.asarray(design["bottle_axis_xy"], float)
    top = float(design["bottle_top_z"])
    Wbot = prop_mesh["bottle_assembly"] + prop_origin["bottle_assembly"]
    Zb = Wbot[:, 2]
    NB = 80
    edges = np.linspace(Zb.min(), Zb.max(), NB + 1)

    def reach(ux, uy, z):
        i = min(int((z - edges[0]) / (edges[1] - edges[0])), NB - 1)
        sel = (Zb >= edges[i]) & (Zb <= edges[i + 1])
        if not sel.any():
            return 0.0
        proj = ((Wbot[sel, 0] - axis[0]) * ux + (Wbot[sel, 1] - axis[1]) * uy)
        return float(proj.max())

    print("=" * 94)
    print("=== bottle reach along +y by height (the quantity that decides a strike) ===")
    for z in np.arange(FLOOR_Z + 0.02, top, 0.03):
        print(f"  z={z:.4f}  reach(+y)={reach(0, 1, z)*1000:8.3f} mm  "
              f"reach(-y)={reach(0, -1, z)*1000:8.3f} mm  "
              f"reach(+x)={reach(1, 0, z)*1000:8.3f} mm")

    # ---- physics search over the release offset ---------------------------------------
    # 05 section 2.6 allows at most 12. The near-face distances are swept from well inside the
    # bottle to just outside its widest reach, in the +y direction, and the box's centre x is
    # aligned with the bottle's axis so the broad face approaches the bottle's flank.
    r_wide = max(reach(0, 1, z) for z in np.arange(FLOOR_Z, top, 0.005))
    print(f"\n  bottle's widest reach along +y above the floor: {r_wide*1000:.3f} mm")
    half_along = box_dims[1] / 2          # the box's y half-extent (authored orientation)
    near_faces = [0.045, 0.035, 0.025, 0.015, 0.005, -0.005]
    drop_clearances = [0.25, 0.25, 0.25, 0.25, 0.25, 0.25]
    print(f"  box y half-extent {half_along*1000:.3f} mm; sweeping the near-face distance "
          f"{[round(v*1000) for v in near_faces]} mm")

    results = []
    n = 0
    best = None
    for nf, dc in zip(near_faces, drop_clearances):
        n += 1
        centre = np.array([axis[0], axis[1] + nf + half_along, top + dc + box_dims[2] / 2])
        quat = (0.0, 0.0, 0.0, 1.0)

        settings = SolverSettings(physics_fps=PHYSICS_FPS)
        solver = MultibodySolver(settings)
        bodies = []
        for name in ("bottle_assembly", "glass_a", "glass_b"):
            bodies.append(BodySpec(
                instance_id=name, asset_id=name,
                role=ROLE_TARGET if name == "bottle_assembly" else ROLE_PASSIVE,
                mass_kg={"bottle_assembly": 0.77, "glass_a": 0.113,
                         "glass_b": 0.157}[name],
                mass_basis="estimated", collider_type="mesh",
                position_m=tuple(float(v) for v in prop_origin[name]),
                quaternion_xyzw=(0.0, 0.0, 0.0, 1.0),
                friction=0.6, restitution=0.0, collision_uri=str(prop_files[name]),
            ))
        bodies.append(BodySpec(
            instance_id="striker_box", asset_id="small_box", role=ROLE_TRIGGER,
            mass_kg=0.1016, mass_basis="estimated", collider_type="mesh",
            position_m=tuple(float(v) for v in centre), quaternion_xyzw=quat,
            friction=0.6, restitution=0.0, collision_uri=str(box_obj),
            inertia_diagonal_kg_m2=box_inertia_diagonal(0.1016, box_dims),
        ))
        solver.load(bodies, statics)
        result = solver.run(int(round(2.0 * VIDEO_FPS)), settle_seconds=2.0,
                            record_substeps=True)

        bot = result.trajectories["bottle_assembly"]
        box = result.trajectories["striker_box"]
        p0 = np.array(bot[0].position)
        p1 = np.array(bot[-1].position)
        trans = float(np.linalg.norm((p1 - p0)[:2]))
        tilt = quat_angle_deg(bot[0].quaternion, bot[-1].quaternion)
        pairs = {}
        first_box_bottle = None
        for c in result.contacts:
            key = "|".join(sorted(c.pair))
            pairs[key] = pairs.get(key, 0) + 1
            if (first_box_bottle is None and "striker_box" in c.pair
                    and "bottle_assembly" in c.pair):
                first_box_bottle = c.step
        hit = first_box_bottle is not None
        box_bottom_final = float(box[-1].position[2]) - box_dims[2] / 2
        reasons = []
        if not hit:
            reasons.append("the box never contacted the bottle")
        if trans < MIN_TRANSLATION_M and tilt < MIN_TILT_DEG:
            reasons.append(f"bottle response below threshold (translation "
                           f"{trans*1000:.2f} mm < {MIN_TRANSLATION_M*1000:.0f} mm and tilt "
                           f"{tilt:.2f} deg < {MIN_TILT_DEG:.0f} deg)")
        passes = hit and not reasons
        rec = {"attempt": n, "near_face_m": nf, "drop_clearance_m": dc,
               "box_centre": [float(v) for v in centre],
               "box_near_face_from_axis_m": float(nf),
               "contacted_bottle": hit,
               "first_contact_step": first_box_bottle,
               "first_contact_time_s": (first_box_bottle / PHYSICS_FPS
                                        if first_box_bottle else None),
               "bottle_translation_m": trans, "bottle_tilt_deg": tilt,
               "box_final_bottom_z": box_bottom_final,
               "contact_pair_counts": pairs,
               "passes": passes, "reasons_rejected": reasons}
        results.append(rec)
        mark = "ACCEPT" if passes else "reject"
        print(f"  #{n} near_face={nf*1000:+7.1f} mm  hit={str(hit):5s} "
              f"trans={trans*1000:8.3f} mm tilt={tilt:7.2f} deg "
              f"box_bottom_z={box_bottom_final:7.4f} {mark}"
              + ("" if passes else f"  <- {'; '.join(reasons)}"))
        score = (1 if hit else 0, trans + tilt / 100.0)
        if best is None or score > best[0]:
            best = (score, rec)
        solver.disconnect()
        if n >= 12:
            break

    passing = [r for r in results if r["passes"]]
    # Prefer the largest response, since 05 wants a clearly visible topple/slide.
    passing.sort(key=lambda r: -(r["bottle_translation_m"] + r["bottle_tilt_deg"] / 100.0))
    chosen = passing[0] if passing else None
    print(f"\n  candidates: {n}; accepted: {len(passing)}")
    if chosen:
        print(f"  CHOSEN #{chosen['attempt']}: near face {chosen['near_face_m']*1000:+.1f} mm, "
              f"drop clearance {chosen['drop_clearance_m']*1000:.0f} mm")
        print(f"    first contact at step {chosen['first_contact_step']} "
              f"(t={chosen['first_contact_time_s']:.4f} s)")
        print(f"    bottle translation {chosen['bottle_translation_m']*1000:.3f} mm, "
              f"tilt {chosen['bottle_tilt_deg']:.2f} deg")
        print(f"    box centre {chosen['box_centre']}")
        print(f"    contact pairs: {chosen['contact_pair_counts']}")
    else:
        print("  NO CANDIDATE PRODUCED AN ACCEPTABLE STRIKE.")
        print("  05 section 4 requires the failure to be reported, not hidden: the box did not")
        print("  move the bottle in any of the search attempts, and no force was ever applied to")
        print("  the bottle to manufacture a result.")

    out = {"search_attempts": n, "candidates": results, "passing_count": len(passing),
           "chosen": chosen, "bottle_widest_reach_plusy_m": r_wide,
           "box_dimensions_m": box_dims,
           "min_translation_m": MIN_TRANSLATION_M, "min_tilt_deg": MIN_TILT_DEG}
    (OUT / "strike_search.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {OUT / 'strike_search.json'}")
    return 0 if chosen else 1


if __name__ == "__main__":
    raise SystemExit(main())
