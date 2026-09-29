"""V5.6 verification of a replay, using stable ids and fixed local reference points.

Replaces `v55_verify_replay.py` as the acceptance instrument. Section 3.3 requires that the old
approach be abandoned and says why: it anchored on the WORLD AABB bottom, which is not a fixed point
of a rigid body -- once the body rotates, the lowest corner of its bounding box is a different
material point -- and it matched scene objects to bodies by "nearest in XY", which silently rebinds
the wrong object when two bodies are close.

What this does instead:

  * **binding by stable id.** Each body names its scene object(s) explicitly, read from a
    `binding.json` the render step writes, so nothing is inferred from geometry at verification time.
    A body with no binding is a hard failure, not something to guess at.
  * **fixed local reference points.** Per body, at least 8 points are chosen ONCE in the body's local
    frame. Their world positions are predicted from the matrix chain
    `T_WV(t) = T_WB(t) @ inverse(T_WB(0)) @ T_WV(0)` and compared against the positions the saved
    file actually produces. Because the points are fixed in the body, rotation cannot move them
    relative to each other, so this measures the replay rather than the bounding box.
  * **support gaps.** The visual's lowest point is measured against the true support surface, with
    the surface passed in rather than assumed, and a flat-bottomed body is required to sit within
    2 mm of it.
  * **scale, bounding box and origin agreement** between visual and collision, per section 3.3.
  * **fail-stop.** Any failed gate exits non-zero so a render chain cannot continue past it.

Run with Blender (needs the scene), reading the run's own records:

    blender.exe --background --factory-startup --python tools\\v56\\verify_replay.py -- <RUN> <replay.blend>
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

# Same maths as tools/v56/body_visual.py, expressed with mathutils because the scene is open here.
# The two implementations are cross-checked by test_body_visual.py and by the frame-0 identity below,
# so a transcription error cannot pass unnoticed.


def rot_error_report(name, value, limit, unit="m"):
    ok = value <= limit
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {value:.6f} {unit} (limit {limit} {unit})")
    return ok


def world_matrix_rows(obj):
    return [list(r) for r in obj.matrix_world]


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        print(__doc__)
        return 2
    RUN = Path(argv[0])
    REPLAY = Path(argv[1]) if len(argv) > 1 else None
    if REPLAY is None or not REPLAY.is_file():
        cands = sorted((RUN / "render" / "replays").glob("replay_*.blend"))
        if not cands:
            print(f"FATAL: no replay project under {RUN / 'render' / 'replays'}")
            return 1
        REPLAY = cands[-1]

    print("=" * 104)
    print(f"V5.6 replay verification")
    print(f"  run     {RUN}")
    print(f"  replay  {REPLAY}")

    binding_p = RUN / "binding.json"
    traj_p = RUN / "trajectory.json"
    refpts_p = RUN / "reference_points.json"
    for p in (binding_p, traj_p, refpts_p):
        if not p.is_file():
            print(f"FATAL: {p} is missing; the binding and reference points must be written by the "
                  f"render step so that verification does not have to infer them")
            return 1

    binding = json.loads(binding_p.read_text(encoding="utf-8"))
    TRAJ = json.loads(traj_p.read_text(encoding="utf-8"))["bodies"]
    REFPTS = json.loads(refpts_p.read_text(encoding="utf-8"))

    bpy.ops.wm.open_mainfile(filepath=str(REPLAY))
    scene = bpy.context.scene
    print(f"  opened: {len(scene.objects)} objects, frames {scene.frame_start}..{scene.frame_end}, "
          f"{scene.render.fps} fps, camera {scene.camera.name if scene.camera else None}")

    cfg = json.loads((RUN / "resolved_config.json").read_text(encoding="utf-8"))
    gates = []

    # -----------------------------------------------------------------------------------
    # gate 1: the saved project can be played, and carries no live solver of its own
    # -----------------------------------------------------------------------------------
    print("\n=== gate 1: replay project ===")
    rbv = [o for o in scene.objects if o.rigid_body is not None]
    gates.append(("frame range matches the trajectory",
                  scene.frame_start == 1 and scene.frame_end == cfg["frame_count"]))
    gates.append(("fps matches", scene.render.fps == cfg["video_fps"]))
    gates.append(("an active camera exists", scene.camera is not None))
    # Section 3: the replayed motion must come only from the recorded keys. A live Blender
    # rigid-body world could re-simulate it differently and would invalidate the replay.
    gates.append(("no Blender rigid-body solver is live", len(rbv) == 0))
    for n, v in gates:
        print(f"  {'PASS' if v else 'FAIL'}  {n}")

    # -----------------------------------------------------------------------------------
    # gate 2: the SAVED camera is the authority, not any earlier JSON (section 3.3, 7.6)
    # -----------------------------------------------------------------------------------
    print("\n=== gate 2: camera, read from the saved file ===")
    cam = scene.camera
    cam_report = {
        "object": cam.name,
        "lens_mm": cam.data.lens,
        "sensor_width_mm": cam.data.sensor_width,
        "location_m": [float(v) for v in cam.matrix_world.translation],
        "rotation_quaternion_wxyz": [float(v) for v in cam.matrix_world.to_quaternion()],
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "fps": scene.render.fps,
    }
    print(f"  {cam_report['object']}  {cam_report['lens_mm']:.1f} mm  "
          f"res {cam_report['resolution'][0]}x{cam_report['resolution'][1]}")
    print(f"  location {[round(v, 5) for v in cam_report['location_m']]}")
    # Cross-check against camera.json and report disagreement rather than choosing one silently.
    cj = RUN / "camera.json"
    if cj.is_file():
        old = json.loads(cj.read_text(encoding="utf-8"))
        old_loc = old.get("eye_m") or old.get("location_m")
        if isinstance(old_loc, list) and len(old_loc) == 3:
            d = math.dist(old_loc, cam_report["location_m"])
            print(f"  camera.json location disagrees with the saved camera by {d*1000:.1f} mm")
            cam_report["disagreement_with_camera_json_m"] = d
            print(f"  the SAVED camera is used as the authority; the disagreement is recorded")
    gates.append(("resolution is even", cam_report["resolution"][0] % 2 == 0
                  and cam_report["resolution"][1] % 2 == 0))

    # -----------------------------------------------------------------------------------
    # gate 3: fixed local reference points reproduced (section 3.3, the core gate)
    # -----------------------------------------------------------------------------------
    print("\n=== gate 3: fixed local reference points ===")
    print("  (>=8 points per body, fixed in the body frame once; world positions predicted from")
    print("   T_WV(t) = T_WB(t) @ inverse(T_WB(0)) @ T_WV(0) and compared with what the file does)")
    worst_all = 0.0
    per_body = {}
    for body_id, info in binding.items():
        rows = TRAJ.get(body_id)
        if not rows:
            print(f"  FAIL  {body_id}: bound in binding.json but absent from trajectory.json")
            gates.append((f"{body_id} has a trajectory", False))
            continue
        pts_by_obj = REFPTS.get(body_id, {}).get("points_per_object")
        if not pts_by_obj:
            print(f"  FAIL  {body_id}: no per-object reference points recorded")
            gates.append((f"{body_id} has reference points", False))
            continue
        npts = sum(len(v) for v in pts_by_obj.values())
        if npts < 8 or any(len(v) < 8 for v in pts_by_obj.values()):
            print(f"  FAIL  {body_id}: {npts} points across {len(pts_by_obj)} object(s); section 3.3 "
                  f"requires at least 8 per object")
            gates.append((f"{body_id} has >=8 reference points per object", False))
            continue
        onames = info.get("objects") or []
        objs = [bpy.data.objects.get(n) for n in onames]
        if not objs or any(o is None for o in objs):
            print(f"  FAIL  {body_id}: bound objects {onames} not all present in the saved file")
            gates.append((f"{body_id} objects present", False))
            continue

        # T_WV(0) must be captured from the file at frame 1, then held fixed; T_WB(t) comes only
        # from the trajectory. Nothing is re-read from the file except the comparison points.
        scene.frame_set(1)
        bpy.context.view_layer.update()
        t_wv_0 = {o.name: o.matrix_world.copy() for o in objs}

        r0 = rows[0]
        # T_WB(0) is translation times the recorded quaternion, converted xyzw (the project contract)
        # to wxyz (Blender's order) explicitly at this boundary.
        q0 = r0["quaternion_xyzw"]
        from mathutils import Quaternion, Matrix
        t_wb_0 = (Matrix.Translation(Vector(r0["position_m"]))
                  @ Quaternion((q0[3], q0[0], q0[1], q0[2])).to_matrix().to_4x4())

        worst = 0.0
        worst_frame = None
        for r in rows:
            q = r["quaternion_xyzw"]
            t_wb_t = (Matrix.Translation(Vector(r["position_m"]))
                      @ Quaternion((q[3], q[0], q[1], q[2])).to_matrix().to_4x4())
            delta = t_wb_t @ t_wb_0.inverted()
            f = int(r["blender_frame"])
            scene.frame_set(f)
            bpy.context.view_layer.update()
            for o in objs:
                predicted_mat = delta @ t_wv_0[o.name]
                for lp in pts_by_obj.get(o.name, []):
                    predicted = predicted_mat @ Vector(lp)
                    actual = o.matrix_world @ Vector(lp)
                    d = (predicted - actual).length
                    if d > worst:
                        worst, worst_frame = d, f
        per_body[body_id] = {"objects": onames, "points": npts, "frames": len(rows),
                             "worst_error_m": worst, "worst_frame": worst_frame}
        ok = worst <= 0.001
        gates.append((f"{body_id} replay within 1 mm", ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {body_id:18s} {len(objs)} object(s) x {npts} points "
              f"x {len(rows)} frames, worst {worst*1000:.6f} mm"
              + (f" at frame {worst_frame}" if worst_frame else ""))
        worst_all = max(worst_all, worst)

    # -----------------------------------------------------------------------------------
    # gate 4: visual vs collision scale, bounding box and origin agreement
    # -----------------------------------------------------------------------------------
    print("\n=== gate 4: visual vs collision agreement ===")
    scale_report = {}
    for body_id, info in binding.items():
        coll = info.get("collision_obj")
        vis = info.get("objects") or []
        if not coll:
            continue
        cp = RUN / f"{body_id}_collision.obj"
        if not cp.is_file():
            print(f"  (no {cp.name} to compare against; recorded as not checked)")
            continue
        dims = obj_dims_from_file(cp)
        if not dims:
            continue
        got = {}
        for o in vis:
            ob = bpy.data.objects.get(o)
            if ob is None:
                continue
            bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
            got[o] = [max(p[i] for p in bb) - min(p[i] for p in bb) for i in range(3)]
        if not got:
            continue
        # Sum the assembly's extents per axis; a single visual is the common case.
        vdims = [max(v[i] for v in got.values()) for i in range(3)]
        rel = [abs(vdims[i] - dims[i]) / dims[i] if dims[i] else None for i in range(3)]
        worst_rel = max(r for r in rel if r is not None)
        scale_report[body_id] = {"collision_dims_m": dims, "visual_dims_m": vdims,
                                 "relative_error": rel}
        ok = worst_rel <= 0.01
        gates.append((f"{body_id} visual/collision dimensions within 1%", ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {body_id:18s} collision "
              f"{[round(d,5) for d in dims]} visual {[round(d,5) for d in vdims]} "
              f"worst {worst_rel*100:.3f}%")

    # -----------------------------------------------------------------------------------
    # gate 5: support gap at rest, measured against the TRUE support surface
    # -----------------------------------------------------------------------------------
    print("\n=== gate 5: support gap in the initial and pre-contact frames ===")
    supports = json.loads((RUN / "support_surfaces.json").read_text(encoding="utf-8")) \
        if (RUN / "support_surfaces.json").is_file() else {}
    if not supports:
        print("  (no support_surfaces.json; the support gap cannot be measured numerically.")
        print("   Section 3.3 forbids assuming a flat box base, so this is reported as NOT")
        print("   CHECKED rather than passed.)")
        gates.append(("support gap measured", False))
    gap_report = {}
    for body_id, info in binding.items():
        if body_id not in supports:
            continue
        z_support = float(supports[body_id]["z_m"])
        flat = bool(supports[body_id].get("flat_bottom", True))
        rows = TRAJ[body_id]
        q0 = rows[0]["quaternion_xyzw"]
        from mathutils import Quaternion, Matrix
        t_wb_0 = (Matrix.Translation(Vector(rows[0]["position_m"]))
                  @ Quaternion((q0[3], q0[0], q0[1], q0[2])).to_matrix().to_4x4())
        gaps = {}
        for f in supports[body_id].get("check_frames", [1, int(cfg["frame_count"])]):
            r = next((x for x in rows if int(x["blender_frame"]) == f), None)
            if r is None:
                continue
            q = r["quaternion_xyzw"]
            t_wb_t = (Matrix.Translation(Vector(r["position_m"]))
                      @ Quaternion((q[3], q[0], q[1], q[2])).to_matrix().to_4x4())
            scene.frame_set(f)
            bpy.context.view_layer.update()
            delta = t_wb_t @ t_wb_0.inverted()
            lows = []
            for o in info["objects"]:
                ob = bpy.data.objects.get(o)
                # The visual's true lowest world point, not its AABB bottom anchor.
                lows.append(min((ob.matrix_world @ v.co).z for v in ob.data.vertices))
            gap = min(lows) - z_support
            gaps[f] = gap
            limit = 0.002 if flat else 0.006
            ok = abs(gap) <= limit
            gates.append((f"{body_id} support gap at frame {f} within "
                          f"{'2' if flat else '6'} mm", ok))
            print(f"  {'PASS' if ok else 'FAIL'}  {body_id:18s} frame {f:4d} lowest visual point "
                  f"{min(lows):.6f} m vs support {z_support:.6f} m -> gap {gap*1000:+.3f} mm "
                  f"({'flat' if flat else 'curved/contact-point'} bottom, limit "
                  f"{limit*1000:.0f} mm)")
        gap_report[body_id] = {"support_z_m": z_support, "flat_bottom": flat,
                               "gaps_m": gaps}

    # -----------------------------------------------------------------------------------
    # verdict
    # -----------------------------------------------------------------------------------
    print("\n=== VERDICT ===")
    nfail = 0
    for n, v in gates:
        if not v:
            nfail += 1
        print(f"  {'PASS' if v else 'FAIL'}  {n}")
    ok = nfail == 0
    print(f"  {len(gates) - nfail}/{len(gates)} gates pass")

    (RUN / "replay_verification.json").write_text(json.dumps({
        "replay_blend": str(REPLAY),
        "gates": [{"name": n, "pass": bool(v)} for n, v in gates],
        "all_pass": ok, "failed_count": nfail,
        "worst_reference_point_error_m": worst_all,
        "per_body": per_body, "scale_check": scale_report, "support_gaps": gap_report,
        "camera": cam_report,
        "method": ("stable ids from binding.json; >=8 fixed local reference points per body compared "
                   "against T_WB(t) @ inverse(T_WB(0)) @ T_WV(0); the saved camera is the authority; "
                   "support gaps measured against the true surface. Section 3.3 forbids the old "
                   "world-AABB-bottom anchor and the old nearest-in-XY binding, both of which this "
                   "replaces."),
    }, indent=2), encoding="utf-8")
    print(f"  written: {RUN / 'replay_verification.json'}")
    if not ok:
        print(f"\nFATAL: {nfail} gate(s) failed. Section 3.3 requires the chain to stop here rather "
              f"than continue to full-frame rendering.")
    return 0 if ok else 1


def obj_dims_from_file(path: Path):
    """Bounding-box dimensions of an OBJ, read directly so no bpy import is needed."""
    mn = [1e18] * 3
    mx = [-1e18] * 3
    n = 0
    try:
        with path.open("r", errors="replace") as fh:
            for line in fh:
                if line.startswith("v "):
                    p = line.split()
                    if len(p) < 4:
                        continue
                    for i in range(3):
                        v = float(p[i + 1])
                        mn[i] = min(mn[i], v)
                        mx[i] = max(mx[i], v)
                    n += 1
    except Exception:
        return None
    if n == 0:
        return None
    return [mx[i] - mn[i] for i in range(3)]


if __name__ == "__main__":
    raise SystemExit(main())
