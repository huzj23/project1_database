"""V5.5 stage 05: solve box-hits-bottle and write the full stage-02 evidence package.

Configuration, all of it carried over from measurements rather than chosen here:

  * bodies: the accepted proxies for `bottle_assembly` (hull), `glass_a` and `glass_b` (vhacd),
    and the approved `small_box` collision mesh for the striker;
  * static support: the exact authored tray `Vassoio` flagged `GEOM_FORCE_CONCAVE_TRIMESH`,
    plus `Table`, `Table.001` and the lamp, each loaded by `fileName` (the vertices/indices route
    is broken in this PyBullet build);
  * roles: the box is the single TRIGGER; the BOTTLE is the TARGET; the two cups are PASSIVE
    obstacles, present so the fall path is honestly constrained;
  * the box starts 0.25 m above the bottle top with the edge strike from the approved design,
    and is released under GRAVITY ALONE. No velocity, force, or constraint is ever applied to
    any body -- 05 section 3 makes that an acceptance condition.

The settle stage exists because 04 requires no initial penetration and the props were authored
1.40 mm below the tray floor. Settling BEFORE t=0 is a pre-solve, not part of the recorded
trajectory: the settled state becomes the t=0 state, so the delivered motion starts from rest.

Deliverables (the 02 evidence package):
  resolved_config.json, provenance.json, bodies.json, trajectory.json, motion_substeps.jsonl,
  contacts.jsonl, events.json, causality.json, validation.json, scene_delta.json, camera.json,
  status.json, commands.txt
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
    ROLE_PASSIVE, ROLE_TARGET, ROLE_TRIGGER, BodySpec, StaticCollider,
    box_inertia_diagonal, frame_time_s, substep_time_s,
)
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
RUNTIME = SCENES / "runtime"
DESIGN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/design.json"
OUT = ROOT / "outcomes/v55/italian_flat/box_hits_bottle"
BUILD = ROOT / "models/gso/Big_Dot_Aqua_Pencil_Case"

RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "20260929T030000"
VIDEO_FPS = 24
PHYSICS_FPS = 480
DURATION_S = 3.0
FLOOR_Z = 0.510600


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


def main() -> int:
    run_dir = OUT / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    if not design.get("design_valid"):
        raise SystemExit("FATAL: design.json is not valid; refusing to solve")
    strike = design["chosen"]

    # ---- bodies ------------------------------------------------------------------------
    decision = json.loads((PROPS / "proxy_decision.json").read_text(encoding="utf-8"))
    prop_files: dict = {}
    for name in ("bottle_assembly", "glass_a", "glass_b"):
        prop_files[name] = sorted((PROPS / name / decision[name]["chosen"]).glob("*.obj"))

    # Merge each prop into ONE collision mesh file so the solver loads it by fileName.
    bodies = []
    provenance: dict = {"run_id": RUN_ID, "scene": "italian_flat",
                        "scene_source": str(ROOT / "models/backgrounds/candidates/"
                                            "italian_flat/source/flat-archiviz.blend"),
                        "runtime_copy": str(RUNTIME / "italian_flat_runtime.blend"),
                        "props": {}, "static_colliders": {}, "striker": {}}

    def write_merged(files, out_path: Path, offset):
        V, F = merged(files)
        V = V + offset
        with out_path.open("w", encoding="utf-8") as h:
            for p in V:
                h.write(f"v {p[0]:.9f} {p[1]:.9f} {p[2]:.9f}\n")
            for t in F:
                h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")
        return V, F

    prop_mass = {"bottle_assembly": 0.77, "glass_a": 0.113, "glass_b": 0.157}
    prop_role = {"bottle_assembly": ROLE_TARGET, "glass_a": ROLE_PASSIVE,
                 "glass_b": ROLE_PASSIVE}
    # Each prop mesh keeps its RECENTRED local coordinates and the BODY carries the world
    # position: baking the world offset into the mesh breaks concave contact generation.
    #
    # THE BODY ORIGIN HEIGHT. The mesh is recentred, so `V.min(axis=0)[2]` is negative and the
    # origin must be raised so the mesh's BOTTOM lands on the tray floor:
    #     origin_z + V.min[2] = FLOOR_Z   ->   origin_z = FLOOR_Z - V.min[2]
    # The first version wrote `FLOOR_Z - (V.min[2] + restore[2])`, which subtracts the world
    # height as well and put every body's origin at z = 0.000 with its mesh ~0.5 m BELOW the
    # floor. The result is unmistakable in the evidence: all four bodies free-fell for the whole
    # run and `contacts.jsonl` was empty.
    for name, files in prop_files.items():
        out_obj = run_dir / f"{name}_collision.obj"
        V, F = merged(files)
        with out_obj.open("w", encoding="utf-8") as h:
            for p in V:
                h.write(f"v {p[0]:.9f} {p[1]:.9f} {p[2]:.9f}\n")
            for t in F:
                h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")
        dims = (V.max(axis=0) - V.min(axis=0)).tolist()
        restore = -np.asarray(decision[name]["recentre_offset_m"], float)
        origin_z = float(FLOOR_Z - V.min(axis=0)[2])
        pos = [float(restore[0]), float(restore[1]), origin_z]
        # Cross-check against the recorded world AABB, so a frame error surfaces here rather
        # than as another free fall. The tolerance allows OBJ text round-off (measured 0.62 mm).
        rec_lo = np.asarray(decision[name]["world_aabb_min"], float)
        got_lo = V.min(axis=0) + restore
        err = float(np.max(np.abs(got_lo - rec_lo)))
        if err > 1e-3:
            raise SystemExit(f"FATAL {name}: restored world AABB is off by {err:.6f} m")
        print(f"  {name:18s} mesh bottom {V.min(axis=0)[2]:+.6f}, body origin z "
              f"{origin_z:.6f} -> world bottom {origin_z + V.min(axis=0)[2]:.6f} "
              f"(floor {FLOOR_Z:.6f}); AABB check {err*1000:.4f} mm")
        bodies.append(BodySpec(
            instance_id=name, asset_id=name, role=prop_role[name],
            mass_kg=prop_mass[name], mass_basis="estimated", collider_type="mesh",
            position_m=tuple(pos), quaternion_xyzw=(0.0, 0.0, 0.0, 1.0),
            friction=0.6, restitution=0.0, collision_uri=str(out_obj),
        ))
        provenance["props"][name] = {
            "instance_id": name, "role": prop_role[name],
            "proxy": decision[name]["chosen"],
            "collision_mesh": str(out_obj), "triangles": int(len(F)),
            "dimensions_m": [round(v, 9) for v in dims],
            "mass_kg": prop_mass[name], "mass_basis": "estimated",
            "source_objects": [f.stem.replace("_", " ") for f in files][:1],
        }

    # Striker: the approved box, recentred on its own AABB centre.
    bv, bf = load_obj(BUILD / "collision_geometry.obj")
    blo, bhi = bv.min(axis=0), bv.max(axis=0)
    box_centre_local = 0.5 * (blo + bhi)
    box_dims = (bhi - blo).tolist()
    bv_c = bv - box_centre_local

    # THE CHOSEN ORIENTATION IS A REAL ROTATION, NOT A LABEL.
    #
    # The design searches two orientations -- the box's long axis along y, or along x -- because
    # the strike geometry depends on which way the longest edge points. The first version
    # recorded the chosen name in provenance but built the body with the IDENTITY quaternion, so
    # the box fell in its authored orientation regardless. The evidence shows the consequence: the
    # box's x/y extent was 0.2092 m along x and 0.0898 m along y, exactly the authored layout,
    # while the chosen orientation was `long_axis_along_y`; its y range (7.5796..7.6694) did not
    # overlap the bottle's (7.4101..7.5196) AT ALL, so it fell past the bottle and
    # `contacts.jsonl` was empty.
    #
    # A yaw about the vertical axis is a placement choice, not a model change, so the rotation is
    # applied to the body here. The mesh itself is untouched.
    orient = strike["orientation"]
    yaw = {"long_axis_along_y": math.pi / 2,      # authored long axis is x -> rotate onto y
           "long_axis_along_x": 0.0}[orient]
    quat_xyzw = (0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2))
    # The rotated horizontal half-extents, which the offsets and checks must use.
    if orient == "long_axis_along_y":
        half_x_used, half_y_used = box_dims[1] / 2, box_dims[0] / 2
    else:
        half_x_used, half_y_used = box_dims[0] / 2, box_dims[1] / 2
    print(f"\n=== striker orientation ===")
    print(f"  chosen {orient} -> yaw {math.degrees(yaw):.1f} deg; rotated half-extents "
          f"x {half_x_used*1000:.2f} mm, y {half_y_used*1000:.2f} mm")
    print(f"  authored dims {[round(v,6) for v in box_dims]}")

    # Re-derive the start position WITH the rotated extents, so the geometry the design chose is
    # the geometry that is actually built. The design recorded its own centre; it is reused only
    # if it agrees with the rotated extents, otherwise the strike is recomputed from the same
    # rule the design used (near face at r(z*) from the axis).
    axis_xy = np.asarray(design["bottle_axis_xy"], float)
    r_contact = float(strike["radius_at_contact_m"])
    dvec = {"+y": (0.0, 1.0), "-y": (0.0, -1.0),
            "+x": (1.0, 0.0), "-x": (-1.0, 0.0)}[strike["direction"]]
    half_along = abs(dvec[0]) * half_x_used + abs(dvec[1]) * half_y_used
    centre_offset = r_contact + half_along
    box_bottom = float(design["bottle_top_z"]) + float(design["drop_clearance_m"])
    box_centre = np.array([axis_xy[0] + dvec[0] * centre_offset,
                           axis_xy[1] + dvec[1] * centre_offset,
                           box_bottom + box_dims[2] / 2])
    world_lo = box_centre - np.array([half_x_used, half_y_used, box_dims[2] / 2])
    world_hi = box_centre + np.array([half_x_used, half_y_used, box_dims[2] / 2])
    print(f"  near face from the bottle axis: {r_contact*1000:.3f} mm "
          f"(bottle widest radius {design['r_max_m']*1000:.3f} mm)")
    print(f"  box world x/y: x {world_lo[0]:.4f}..{world_hi[0]:.4f}  "
          f"y {world_lo[1]:.4f}..{world_hi[1]:.4f}")
    bp = design["props"]["bottle_assembly"]
    bmx, bmn = np.array(bp["max"]), np.array(bp["min"])
    ovx = min(world_hi[0], bmx[0]) - max(world_lo[0], bmn[0])
    ovy = min(world_hi[1], bmx[1]) - max(world_lo[1], bmn[1])
    print(f"  horizontal overlap with the bottle: x {ovx*1000:+.3f} mm, "
          f"y {ovy*1000:+.3f} mm -> overlaps both: {ovx > 0 and ovy > 0}")
    if not (ovx > 0 and ovy > 0):
        raise SystemExit("FATAL: the box's start footprint does not overlap the bottle in x/y, "
                         "so it cannot strike it; the strike geometry is wrong")

    box_obj = run_dir / "striker_box_collision.obj"
    with box_obj.open("w", encoding="utf-8") as h:
        for p in bv_c:
            h.write(f"v {p[0]:.9f} {p[1]:.9f} {p[2]:.9f}\n")
        for t in bf:
            h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")
    bodies.append(BodySpec(
        instance_id="striker_box", asset_id="small_box", role=ROLE_TRIGGER,
        mass_kg=0.1016, mass_basis="estimated", collider_type="mesh",
        position_m=tuple(float(v) for v in box_centre),
        quaternion_xyzw=quat_xyzw,
        friction=0.6, restitution=0.0, collision_uri=str(box_obj),
        inertia_diagonal_kg_m2=box_inertia_diagonal(0.1016, box_dims),
    ))
    provenance["striker"] = {
        "instance_id": "striker_box", "role": ROLE_TRIGGER, "asset_id": BUILD.name,
        "collision_mesh": str(box_obj), "triangles": int(len(bf)),
        "dimensions_m": [round(v, 9) for v in box_dims], "mass_kg": 0.1016,
        "mass_basis": "estimated",
        "inertia_diagonal_kg_m2": box_inertia_diagonal(0.1016, box_dims),
        "orientation": orient, "yaw_deg": round(math.degrees(yaw), 6),
        "quaternion_xyzw": list(quat_xyzw),
        "rotated_half_extents_m": [half_x_used, half_y_used],
        "start_centre_m": [float(v) for v in box_centre],
        "start_aabb_m": [world_lo.tolist(), world_hi.tolist()],
        "near_face_from_bottle_axis_m": r_contact,
        "horizontal_overlap_with_bottle_m": [float(ovx), float(ovy)],
        "note": "the real approved asset, unmodified; only placement orientation is chosen",
    }

    # ---- static colliders ---------------------------------------------------------------
    statics = []
    layer = json.loads((SCENES / "layer_report.json").read_text(encoding="utf-8"))
    for name, info in layer["static_collision_per_object"].items():
        uri = RUNTIME / info["uri"].replace("\\", "/").rsplit("/", 1)[-1]
        concave = str(name).lower().startswith("vassoio")
        statics.append(StaticCollider(
            collider_id=name, collider_type="mesh", uri=str(uri), concave=concave,
            support_z_m=FLOOR_Z if concave else None, triangles=info["triangles"],
        ))
        provenance["static_colliders"][name] = {
            "uri": str(uri), "triangles": info["triangles"], "concave": concave,
            "support_z_m": FLOOR_Z if concave else None,
            "load_route": "fileName",
        }

    # ---- solve ---------------------------------------------------------------------------
    settings = SolverSettings(physics_fps=PHYSICS_FPS)
    solver = MultibodySolver(settings)
    solver.load(bodies, statics)

    self_check = solver.self_check()
    print("=" * 90)
    print(f"=== solver self_check: ok={self_check['ok']} ===")
    for k, v in self_check["static_colliders"].items():
        print(f"  {k:38s} supported={v.get('supported')} "
              f"support_height_ok={v.get('support_height_verified')} "
              f"err={v.get('support_height_error_m')}")

    frame_count = int(round(DURATION_S * VIDEO_FPS))
    result = solver.run(frame_count, settle_seconds=2.0, record_substeps=True,
                        run_id=RUN_ID)

    # ---- write the evidence package -------------------------------------------------------
    (run_dir / "resolved_config.json").write_text(json.dumps({
        "run_id": RUN_ID, "scenario": "box_hits_bottle", "scene": "italian_flat",
        "video_fps": VIDEO_FPS, "physics_fps": PHYSICS_FPS,
        "substeps_per_frame": PHYSICS_FPS // VIDEO_FPS,
        "duration_s": DURATION_S, "frame_count": frame_count,
        "solver": settings.to_dict(),
        "design": strike,
    }, indent=2), encoding="utf-8")
    (run_dir / "provenance.json").write_text(json.dumps(provenance, indent=2),
                                             encoding="utf-8")
    (run_dir / "bodies.json").write_text(json.dumps(
        [b.to_dict() for b in result.bodies], indent=2), encoding="utf-8")
    (run_dir / "camera.json").write_text(json.dumps(
        design.get("camera", {"status": "chosen in stage 09"}), indent=2), encoding="utf-8")
    (run_dir / "commands.txt").write_text(
        "# V5.5 stage 05 box-hits-bottle run\n"
        f"# run_id {RUN_ID}\n"
        f"python {Path(__file__).name} {RUN_ID}\n"
        f"# solver: pybullet DIRECT, dt=1/{PHYSICS_FPS}, video {VIDEO_FPS} fps, "
        f"{PHYSICS_FPS//VIDEO_FPS} substeps/frame\n"
        f"# bodies: {[b.instance_id for b in result.bodies]}\n"
        f"# statics: {[s.collider_id for s in statics]}\n"
        f"# solve: settle 2.0 s then {frame_count} frames, gravity alone\n",
        encoding="utf-8")
    from physim.physics.multibody import write_evidence
    write_evidence(result, run_dir)
    print(f"\n=== evidence written to {run_dir} ===")
    for f in sorted(run_dir.iterdir()):
        print(f"  {f.name:28s} {f.stat().st_size:>10d} bytes")

    # ---- acceptance summary ---------------------------------------------------------------
    body_of = {b.instance_id: b for b in result.bodies}
    traj = result.trajectories
    box_traj = traj["striker_box"]
    bot_traj = traj["bottle_assembly"]
    # `BodyState` (the pre-existing physics dataclass) uses `position` and `quaternion`, and its
    # quaternion is wxyz. Rotating by the angle is invariant to the ordering, and both
    # quaternions here come from the same convention, so the tilt is computed directly.
    box_z0 = float(box_traj[0].position[2])
    bot_p0 = np.array(bot_traj[0].position)
    bot_p1 = np.array(bot_traj[-1].position)
    disp = float(np.linalg.norm((bot_p1 - bot_p0)[:2]))
    q0 = np.array(bot_traj[0].quaternion)
    q1 = np.array(bot_traj[-1].quaternion)
    dot = abs(float(np.dot(q0, q1)))
    tilt = math.degrees(2 * math.acos(min(1.0, dot)))
    contacts = result.contacts
    print(f"\n=== acceptance summary ===")
    print(f"  box start z          : {box_z0:.6f}")
    print(f"  bottle xy translation: {disp*1000:.3f} mm (need >= 30 mm)")
    print(f"  bottle tilt          : {tilt:.2f} deg (need >= 20 deg)")
    print(f"  contact records      : {len(contacts)}")
    print(f"  substeps recorded    : {len(result.substeps)}")
    if contacts:
        pairs = {}
        for c in contacts:
            pairs["|".join(sorted(c.pair))] = pairs.get("|".join(sorted(c.pair)), 0) + 1
        print(f"  contact pairs        : {pairs}")
    summary = {"bottle_translation_m": disp, "bottle_tilt_deg": tilt,
               "contact_records": len(contacts), "box_start_z": box_z0,
               "self_check_ok": self_check["ok"]}
    (run_dir / "acceptance_summary.json").write_text(json.dumps(summary, indent=2),
                                                     encoding="utf-8")
    solver.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
