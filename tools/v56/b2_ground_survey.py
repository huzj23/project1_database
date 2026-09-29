"""b2_ground_survey.py -- V5.6 video B, step 1: pick and MEASURE the real ground region for the chain.

WHY THIS EXISTS
---------------
Plan section 4.B prefers a plain, reasonably flat, non-reflective NATIVE area of Hidden Alley
(brick wall / door / wall base as a low-distraction background) and requires a clear straight region
about 2-3 m long. It forbids declaring an area usable "from an empty-looking still".

We cannot look at images, so the ground is measured with rays:

  1. Restrict the survey to the alley floor proper. `b2_ground_inventory.py` shows the alley floor is
     `Floor_main` (x -4.2..4.2, y -8.0..14.2, 12 437 verts) with a `stones` scatter layer on top of it
     (185 330 verts), while `BG_floor` is a 810-unit backdrop plane and `courtyard_floor` is a single
     quad 1.4 m up. Only Floor_main / stones are treated as ground; the backdrop planes cannot win.
  2. A downward ray grid records, per cell, the topmost hit ground object, the hit height and
     |normal.z| -- so a seam between two objects is visible rather than inferred.
  3. A window search finds rectangles of the required length x width where every cell hits the SAME
     object and the heights fit a plane within tolerance. Reported flatness is the max |residual| from
     a least-squares plane at the FINE step, with the fitted tilt in degrees, so a planar-but-tilted
     slab is not confused with a bumpy one. The fitted plane coefficients are reported because the
     physics step needs an explicit support plane.
  4. An obstacle check intersects the region's stand-up volume with every scene object's world AABB
     and names each overlapping object with its overlap volume -- a measurement, not a look.
  5. Background rays report which object provides the visible backdrop and at what distance, in four
     directions (across the chain both ways, and past each end).

Read-only w.r.t. the scene. Writes one JSON and one text map. Deletes nothing.

Run:
  & '<blender.exe>' --background --factory-startup --python b2_ground_survey.py -- \
        --blend <scene.blend> --out <report.json> [--step 0.04] [--fine 0.015]
        [--len 3.0] [--width 0.60]
"""

import argparse
import json
import math
import sys
import time

import numpy as np

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

#: Only these objects are allowed to BE the ground. Chosen from the measured inventory: Floor_main is
#: the alley floor slab, `stones` is its decorative scatter layer. BG_floor (810 units across) and
#: courtyard_floor (a single quad 1.4 m up) are deliberately excluded so a backdrop plane cannot be
#: reported as the ground under the chain.
GROUND_OBJECTS = ("Floor_main", "stones")


def log(*a):
    print("[b2_ground]", *a, flush=True)


def rnd(x, nd=6):
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, (list, tuple, np.ndarray)):
        return [rnd(v, nd) for v in x]
    try:
        f = float(x)
    except (TypeError, ValueError):
        return x
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ground", default=",".join(GROUND_OBJECTS))
    ap.add_argument("--step", type=float, default=0.04)
    ap.add_argument("--fine", type=float, default=0.015)
    ap.add_argument("--len", type=float, default=3.0)
    ap.add_argument("--width", type=float, default=0.60)
    ap.add_argument("--flat-tol", type=float, default=0.010)
    ap.add_argument("--headroom", type=float, default=1.20)
    ap.add_argument("--pad", type=float, default=0.10)
    ap.add_argument("--z-window", type=float, nargs=2, default=[-0.40, 0.60])
    ap.add_argument("--top", type=int, default=14)
    A = ap.parse_args(args)
    ground_names = [g.strip() for g in A.ground.split(",") if g.strip()]
    t0 = time.time()

    bpy.ops.wm.open_mainfile(filepath=A.blend)
    sc = bpy.context.scene
    meshes = [o for o in sc.objects if o.type == "MESH"]
    log(f"{len(meshes)} mesh objects; opened in {time.time() - t0:.1f}s")

    if not all(bpy.data.objects.get(g) is not None for g in ground_names):
        raise SystemExit(f"ground object(s) not in scene: "
                         f"{[g for g in ground_names if bpy.data.objects.get(g) is None]}")

    # ---- 1. one flattened triangle soup + a triangle->object map ----------------------------
    all_verts, all_tris, spans, names, aabbs = [], [], {}, [], {}
    v_off = t_off = 0
    dg = bpy.context.evaluated_depsgraph_get()
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            nv = len(me.vertices)
            if nv == 0:
                continue
            me.calc_loop_triangles()
            if len(me.loop_triangles) == 0:
                continue
            mw = np.array(o.matrix_world, dtype=np.float64)
            co = np.empty((nv, 3), dtype=np.float64)
            me.vertices.foreach_get("co", co.ravel())
            co4 = np.concatenate([co, np.ones((nv, 1))], axis=1)
            w = (mw @ co4.T).T[:, :3]
            li = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("vertices", li)
            tri = li.reshape(-1, 3)
        finally:
            ev.to_mesh_clear()
        aabbs[o.name] = (w.min(axis=0), w.max(axis=0))
        names.append(o.name)
        spans[o.name] = (t_off, len(w), len(tri))
        all_verts.append(w)
        all_tris.append(tri + v_off)
        v_off += len(w)
        t_off += len(tri)
    sv = np.concatenate(all_verts, axis=0)
    st = np.concatenate(all_tris, axis=0)
    n_mesh = len(names)
    name_index = {nm: i for i, nm in enumerate(names)}
    tri_owner = np.empty(len(st), dtype=np.int32)
    for i, nm in enumerate(names):
        base, nv, nt = spans[nm]
        tri_owner[base:base + nt] = i
    # Loud invariants: a silent off-by-one here would mislabel every ray hit.
    _off = 0
    for nm in names:
        base, nv, nt = spans[nm]
        assert base == _off, f"span bookkeeping broken at {nm}: {base} != {_off}"
        _off += nt
    assert _off == len(st), f"span total {_off} != {len(st)}"
    assert len(sv) == v_off, f"vertex total {len(sv)} != {v_off}"
    counts = np.bincount(tri_owner, minlength=n_mesh)
    for i, nm in enumerate(names):
        assert counts[i] == spans[nm][2], f"tri_owner wrong for {nm}"
    log(f"triangle soup ready: {len(sv)} verts, {len(st)} tris, attribution verified over "
        f"{n_mesh} meshes ({time.time() - t0:.1f}s)")

    scene_bvh = BVHTree.FromPolygons([tuple(v) for v in sv],
                                     [tuple(int(i) for i in t) for t in st],
                                     all_triangles=True, epsilon=0.0)
    log(f"scene BVH built ({time.time() - t0:.1f}s)")

    # ---- 2. survey area = union of the ground objects' XY extents ---------------------------
    gmin = np.min([aabbs[g][0] for g in ground_names], axis=0)
    gmax = np.max([aabbs[g][1] for g in ground_names], axis=0)
    zstart = float(gmax[2]) + 0.30
    log(f"survey area x[{gmin[0]:.3f},{gmax[0]:.3f}] y[{gmin[1]:.3f},{gmax[1]:.3f}], "
        f"cast down from z={zstart:.3f}")

    gset = {g.lower() for g in ground_names}
    down = Vector((0.0, 0.0, -1.0))

    def cast(step):
        xs = np.arange(gmin[0], gmax[0] + 1e-9, step)
        ys = np.arange(gmin[1], gmax[1] + 1e-9, step)
        nx, ny = len(xs), len(ys)
        z = np.full((nx, ny), np.nan)
        own = np.full((nx, ny), -1, dtype=np.int32)
        nz = np.full((nx, ny), np.nan)
        for i in range(nx):
            for j in range(ny):
                loc, nrm, idx, dist = scene_bvh.ray_cast(
                    Vector((float(xs[i]), float(ys[j]), zstart)), down, 400.0)
                if loc is None or idx is None:
                    continue
                nm = names[tri_owner[idx]]
                if nm.lower() not in gset:
                    continue
                if not (A.z_window[0] <= loc.z <= A.z_window[1]):
                    continue
                z[i, j] = loc.z
                own[i, j] = int(tri_owner[idx])
                nz[i, j] = abs(float(nrm.z))
        return xs, ys, z, own, nz

    def window(i0, j0, L, W, xs, ys, z, own, nz):
        bo = own[i0:i0 + L, j0:j0 + W]
        bz = z[i0:i0 + L, j0:j0 + W]
        if np.any(bo < 0) or np.any(np.isnan(bz)):
            return None
        if int(bo.max()) != int(bo.min()):
            return None
        px = np.repeat(xs[i0:i0 + L], W)
        py = np.tile(ys[j0:j0 + W], L)
        pz = bz.ravel()
        Am = np.column_stack([px, py, np.ones(len(px))])
        coef, *_ = np.linalg.lstsq(Am, pz, rcond=None)
        res = pz - Am @ coef
        bn = nz[i0:i0 + L, j0:j0 + W]
        return {
            "x0": float(xs[i0]), "x1": float(xs[i0 + L - 1]),
            "y0": float(ys[j0]), "y1": float(ys[j0 + W - 1]),
            "len_m": float(xs[i0 + L - 1] - xs[i0]),
            "width_m": float(ys[j0 + W - 1] - ys[j0]),
            "surface_object": names[int(bo[0, 0])],
            "grid_step_m": float(xs[1] - xs[0]),
            "n_samples": int(L * W),
            "plane_z_equals_ax_by_c": {"a_dzdx": float(coef[0]), "b_dzdy": float(coef[1]),
                                       "c_z_at_origin": float(coef[2])},
            "plane_tilt_deg": math.degrees(math.atan(math.hypot(coef[0], coef[1]))),
            "plane_normal_world": rnd([-coef[0] / math.sqrt(coef[0] ** 2 + coef[1] ** 2 + 1.0),
                                       -coef[1] / math.sqrt(coef[0] ** 2 + coef[1] ** 2 + 1.0),
                                       1.0 / math.sqrt(coef[0] ** 2 + coef[1] ** 2 + 1.0)], 8),
            "flatness_max_dev_m": float(np.max(np.abs(res))),
            "flatness_rms_m": float(np.sqrt(np.mean(res ** 2))),
            "flatness_p95_dev_m": float(np.percentile(np.abs(res), 95)),
            "z_min": float(bz.min()), "z_max": float(bz.max()),
            "z_span_m": float(bz.max() - bz.min()),
            "normal_z_min": (None if np.all(np.isnan(bn)) else float(np.nanmin(bn))),
            "normal_z_mean": (None if np.all(np.isnan(bn)) else float(np.nanmean(bn))),
        }

    xs, ys, z, own, nz = cast(A.step)
    nx, ny = len(xs), len(ys)
    Lc = max(2, int(round(A.len / A.step)) + 1)
    Wc = max(2, int(round(A.width / A.step)) + 1)
    log(f"grid {nx}x{ny} step {A.step}; block {Lc}x{Wc} = "
        f"{(Lc - 1) * A.step:.2f} x {(Wc - 1) * A.step:.2f} m")
    hits = int(np.sum(own >= 0))
    log(f"{hits}/{nx * ny} rays landed on a ground object ({time.time() - t0:.1f}s)")

    wins = []
    for i0 in range(0, nx - Lc + 1):
        for j0 in range(0, ny - Wc + 1):
            rec = window(i0, j0, Lc, Wc, xs, ys, z, own, nz)
            if rec is not None:
                wins.append(rec)
    log(f"{len(wins)} single-object windows at {A.step} m ({time.time() - t0:.1f}s)")
    wins.sort(key=lambda c: c["flatness_max_dev_m"])

    # ---- 3. refine the best windows at the fine step ---------------------------------------
    centres = []
    for c in wins:
        if c["flatness_max_dev_m"] > A.flat_tol:
            break
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
        if any(abs(cx - p[0]) < 0.50 and abs(cy - p[1]) < 0.50 for p in centres):
            continue
        centres.append((cx, cy, c["surface_object"]))
        if len(centres) >= A.top:
            break
    log(f"{len(centres)} refinement centres")

    finals = []
    for cx, cy, sur in centres:
        span = A.len / 2 + 0.30
        ax0, ax1 = max(cx - span, gmin[0]), min(cx + span, gmax[0])
        ay0, ay1 = max(cy - span, gmin[1]), min(cy + span, gmax[1])
        fxs = np.arange(ax0, ax1 + 1e-9, A.fine)
        fys = np.arange(ay0, ay1 + 1e-9, A.fine)
        fnx, fny = len(fxs), len(fys)
        fz = np.full((fnx, fny), np.nan)
        fo = np.full((fnx, fny), -1, dtype=np.int32)
        fnz = np.full((fnx, fny), np.nan)
        for i in range(fnx):
            for j in range(fny):
                loc, nrm, idx, dist = scene_bvh.ray_cast(
                    Vector((float(fxs[i]), float(fys[j]), zstart)), down, 400.0)
                if loc is None or idx is None:
                    continue
                nm = names[tri_owner[idx]]
                if nm.lower() not in gset:
                    continue
                if not (A.z_window[0] <= loc.z <= A.z_window[1]):
                    continue
                fz[i, j] = loc.z
                fo[i, j] = int(tri_owner[idx])
                fnz[i, j] = abs(float(nrm.z))
        fL = max(2, int(round(A.len / A.fine)) + 1)
        fW = max(2, int(round(A.width / A.fine)) + 1)
        best = None
        for i0 in range(0, fnx - fL + 1):
            for j0 in range(0, fny - fW + 1):
                rec = window(i0, j0, fL, fW, fxs, fys, fz, fo, fnz)
                if rec is None or rec["surface_object"] != sur:
                    continue
                if best is None or rec["flatness_max_dev_m"] < best["flatness_max_dev_m"]:
                    best = rec
        if best is None:
            finals.append({"refine_centre": [cx, cy], "surface_object": sur,
                           "fine_window_found": False,
                           "note": f"no single-object {A.len} x {A.width} m window on {sur} "
                                   f"survives the {A.fine} m re-measurement here"})
            log(f"  refine ({cx:.2f},{cy:.2f}) {sur}: NO fine window")
            continue
        best["refine_centre"] = [cx, cy]
        best["fine_window_found"] = True
        finals.append(best)
        log(f"  refine ({cx:.2f},{cy:.2f}) {sur}: x[{best['x0']:.3f},{best['x1']:.3f}] "
            f"y[{best['y0']:.3f},{best['y1']:.3f}] n={best['n_samples']} "
            f"flat={best['flatness_max_dev_m'] * 1000:.3f}mm "
            f"p95={best['flatness_p95_dev_m'] * 1000:.3f}mm "
            f"tilt={best['plane_tilt_deg']:.3f}deg zspan={best['z_span_m'] * 1000:.1f}mm")

    # ---- 4. longest flat single-object run in each refine box (the 3 m target may be too long) --
    runs = []
    for cx, cy, sur in centres:
        span = A.len / 2 + 0.30
        fxs = np.arange(max(cx - span, gmin[0]), min(cx + span, gmax[0]) + 1e-9, A.fine)
        fys = np.arange(max(cy - span, gmin[1]), min(cy + span, gmax[1]) + 1e-9, A.fine)
        fnx, fny = len(fxs), len(fys)
        fz = np.full((fnx, fny), np.nan)
        fo = np.full((fnx, fny), -1, dtype=np.int32)
        fnz = np.full((fnx, fny), np.nan)
        for i in range(fnx):
            for j in range(fny):
                loc, nrm, idx, dist = scene_bvh.ray_cast(
                    Vector((float(fxs[i]), float(fys[j]), zstart)), down, 400.0)
                if loc is None or idx is None:
                    continue
                nm = names[tri_owner[idx]]
                if nm.lower() not in gset:
                    continue
                if not (A.z_window[0] <= loc.z <= A.z_window[1]):
                    continue
                fz[i, j] = loc.z
                fo[i, j] = int(tri_owner[idx])
                fnz[i, j] = abs(float(nrm.z))
        fW = max(2, int(round(A.width / A.fine)) + 1)
        # widen the width first (cheap) then grow the length, so we learn how wide a clean
        # corridor actually is as well as how long
        best_w = None
        for j0 in range(fny - fW + 1):
            for i0 in range(0, fnx - fW + 1):     # a square-ish seed, then grow in x
                rec = window(i0, j0, fW, fW, fxs, fys, fz, fo, fnz)
                if rec is None or rec["surface_object"] != sur:
                    continue
                for L in range(fW, fnx - i0 + 1):
                    r2 = window(i0, j0, L, fW, fxs, fys, fz, fo, fnz)
                    if r2 is None or r2["flatness_max_dev_m"] > A.flat_tol:
                        break
                    if best_w is None or r2["len_m"] > best_w["len_m"]:
                        best_w = r2
                break
        if best_w is not None:
            best_w["refine_centre"] = [cx, cy]
            runs.append(best_w)
            log(f"  longest flat {A.width:.2f} m-wide corridor near ({cx:.2f},{cy:.2f}) {sur}: "
                f"len={best_w['len_m']:.3f} m flat={best_w['flatness_max_dev_m'] * 1000:.3f}mm "
                f"tilt={best_w['plane_tilt_deg']:.3f}deg")

    # ---- 5. obstacle + background checks ---------------------------------------------------
    scene_items = [(nm, aabbs[nm][0], aabbs[nm][1]) for nm in names]
    for c in finals:
        if not c.get("fine_window_found"):
            continue
        zc = c["z_min"]
        lo = np.array([c["x0"] - A.pad, c["y0"] - A.pad, zc - 0.10])
        hi = np.array([c["x1"] + A.pad, c["y1"] + A.pad, zc + A.headroom])
        hits = []
        for nm, amn, amx in scene_items:
            if np.all(amn <= hi) and np.all(amx >= lo):
                ov = np.minimum(amx, hi) - np.maximum(amn, lo)
                vol = float(max(0.0, ov[0]) * max(0.0, ov[1]) * max(0.0, ov[2]))
                hits.append({"object": nm, "aabb_min": rnd(amn), "aabb_max": rnd(amx),
                             "overlap_volume_m3": rnd(vol, 8),
                             "overlap_xy_m": rnd([max(0.0, ov[0]), max(0.0, ov[1])], 5),
                             "overlap_top_above_ground_m": rnd(min(amx[2], hi[2]) - zc, 5)})
        hits.sort(key=lambda h: -h["overlap_volume_m3"])
        c["obstacle_check"] = {
            "standup_volume_min": rnd(lo), "standup_volume_max": rnd(hi),
            "pad_m": A.pad, "headroom_m": A.headroom,
            "objects_overlapping": len(hits), "overlapping": hits[:25],
            "overlapping_truncated_at": 25,
        }
        c["obstacle_free"] = len(hits) == 0
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
        c["background_rays"] = {}
        for dn, dv in (("perp_plus_y", (0.0, 1.0, 0.0)), ("perp_minus_y", (0.0, -1.0, 0.0)),
                       ("along_plus_x", (1.0, 0.0, 0.0)), ("along_minus_x", (-1.0, 0.0, 0.0))):
            loc, nrm, idx, dist = scene_bvh.ray_cast(
                Vector((cx, cy, zc + 0.20)), Vector(dv), 80.0)
            c["background_rays"][dn] = (
                {"hit": None, "note": "ray escaped the scene"} if loc is None else
                {"hit_object": names[tri_owner[idx]], "distance_m": rnd(dist, 4),
                 "hit_point": rnd([float(loc.x), float(loc.y), float(loc.z)], 4),
                 "normal_z_abs": rnd(abs(float(nrm.z)), 5)})

    out = {
        "blend": A.blend,
        "generated_unix": time.time(),
        "parameters": {
            "ground_objects": ground_names, "survey_step_m": A.step, "fine_step_m": A.fine,
            "target_len_m": A.len, "target_width_m": A.width, "flat_tol_m": A.flat_tol,
            "headroom_m": A.headroom, "pad_m": A.pad, "z_window_m": A.z_window,
        },
        "method": (
            "downward ray grid against a BVH of the whole scene. A cell counts as ground only if the "
            "topmost hit belongs to one of `ground_objects` AND the hit z is inside the z window; "
            "every cell of a window must hit the SAME object. Flatness = max |residual| from a "
            "least-squares plane through the window's hit points, at the fine step, with the fitted "
            "plane coefficients and tilt reported. The obstacle check intersects the region's "
            "stand-up volume with every scene object's world AABB and lists each overlapping object "
            "and its overlap volume."
        ),
        "ground_object_aabbs": {g: {"min": rnd(aabbs[g][0]), "max": rnd(aabbs[g][1])}
                                for g in ground_names},
        "survey": {"x": [float(xs[0]), float(xs[-1])], "y": [float(ys[0]), float(ys[-1])],
                   "nx": nx, "ny": ny, "step_m": A.step, "cast_from_z": zstart,
                   "rays_on_ground": hits},
        "coarse_windows_total": len(wins),
        "coarse_windows_top": wins[:80],
        "fine_final_windows": finals,
        "longest_flat_corridors": runs,
        "runtime_s": rnd(time.time() - t0, 2),
    }
    with open(A.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

    # a text map of which ground object was hit, and one of the residual-vs-plane sign
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    legend = {}
    with open(A.out.replace(".json", "_gridmap.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"GROUND OBJECT MAP  rows={ny} cols={nx} step={A.step} "
                 f"x0={xs[0]:.3f} y0={ys[0]:.3f}  (top row = max y, left col = min x)\n")
        fh.write("'.' = no ground-object hit in the z window\n\n")
        for j in range(ny - 1, -1, -1):
            row = []
            for i in range(nx):
                v = own[i, j]
                if v < 0:
                    row.append(".")
                    continue
                if v not in legend:
                    legend[v] = chars[len(legend) % len(chars)]
                row.append(legend[v])
            fh.write("".join(row) + "\n")
        fh.write("\nLEGEND:\n")
        for k, ch in sorted(legend.items(), key=lambda kv: kv[1]):
            fh.write(f"  {ch} = {names[k]}\n")
    log(f"written {A.out} in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
