"""b2_ground_survey.py -- V5.6 video B, step 1: pick the REAL ground region for the box chain.

WHY THIS EXISTS
---------------
Plan section 4.B says to reuse a plain, reasonably flat, non-reflective native area of Hidden Alley
(brick wall / door / wall base as a low-distraction background) and requires a clear straight region
about 2-3 m long. It also forbids declaring an area usable "from an empty-looking still".

We cannot look at images, so the ground is MEASURED:

  1. A downward ray grid against a BVH of the whole scene. Per cell we record the topmost hit object,
     the hit height, and |normal.z|. This shows whether the ground under a candidate region is one
     continuous surface or several objects meeting at a seam.
  2. A two-stage search for axis-aligned rectangles of the required length x width in which every
     ray hits the SAME object and the hit heights deviate from their best-fit plane by no more than
     a tolerance. Stage A is a coarse sweep over the whole survey area; stage B refines each coarse
     winner on a fine grid, and the FINAL reported flatness is the fine-grid number.
     "Flatness" = max |residual| from a least-squares plane, and the fitted tilt is reported too, so
     a planar-but-tilted slab is not confused with a bumpy one.
  3. An obstacle check that is a measurement, not a look: a candidate is rejected if any OTHER
     object's world AABB intersects the region's stand-up volume (footprint grown by `pad`, from
     z_ground - 0.10 to z_ground + headroom). Every intersecting object is named with its overlap
     volume, so a rejection is always explained.
  4. A background check: horizontal rays from the region's centre report which object provides the
     visible backdrop and at what distance, in four directions.

Read-only w.r.t. the scene. Writes only its JSON report and a text grid map. Deletes nothing.

Run:
  & '<blender.exe>' --background --factory-startup --python b2_ground_survey.py -- \
        --blend <scene.blend> --out <report.json> [--coarse 0.15] [--fine 0.025]
        [--len 3.0] [--width 0.60] [--flat-tol 0.008]
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

# A ray counts as landing on "the ground" only if the topmost hit object's name matches one of
# these. This is deliberately name-based so a barrel lid or a windowsill can never be reported as
# the ground; the ray's own height filter (below) removes the huge backdrop planes as well.
GROUND_NAME_HINTS = ("floor_main", "floor_", "_floor", "ground", "stones", "gravel",
                     "concrete", "asphalt", "road", "paving", "pavement", "base_")

# Objects whose AABB max dimension exceeds this are backdrop/sky and are excluded from setting the
# survey extent. BG_floor is ~810 units across and would otherwise define a 810 m search area.
BACKDROP_MAX_DIM_UNITS = 60.0


def log(*a):
    print("[b2_ground]", *a, flush=True)


def rnd(x, nd=6):
    if x is None or isinstance(x, bool):
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


def eval_world_verts(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        nv = len(me.vertices)
        if nv == 0:
            return None, None
        mw = np.array(obj.matrix_world, dtype=np.float64)
        co = np.empty((nv, 3), dtype=np.float64)
        me.vertices.foreach_get("co", co.ravel())
        co4 = np.concatenate([co, np.ones((nv, 1))], axis=1)
        w = (mw @ co4.T).T[:, :3]
        me.calc_loop_triangles()
        if len(me.loop_triangles) == 0:
            return w, None
        li = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
        me.loop_triangles.foreach_get("vertices", li)
        return w, li.reshape(-1, 3)
    finally:
        ev.to_mesh_clear()


def build_scene(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--coarse", type=float, default=0.15)
    ap.add_argument("--fine", type=float, default=0.025)
    ap.add_argument("--len", type=float, default=3.0)
    ap.add_argument("--width", type=float, default=0.60)
    ap.add_argument("--flat-tol", type=float, default=0.008)
    ap.add_argument("--headroom", type=float, default=1.20)
    ap.add_argument("--pad", type=float, default=0.10)
    ap.add_argument("--z-min", type=float, default=-1.0)
    ap.add_argument("--z-max", type=float, default=1.0)
    ap.add_argument("--refine-keep", type=int, default=12)
    ap.add_argument("--refine-span", type=float, default=0.8)
    return ap.parse_args(argv)


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    A = build_scene(args)
    t0 = time.time()

    bpy.ops.wm.open_mainfile(filepath=A.blend)
    sc = bpy.context.scene
    meshes = [o for o in sc.objects if o.type == "MESH"]
    log(f"{len(meshes)} mesh objects; opened in {time.time() - t0:.1f}s")

    all_verts, all_tris, spans, names, aabbs = [], [], {}, [], {}
    v_off = t_off = 0
    for o in meshes:
        w, t = eval_world_verts(o)
        if w is None or t is None or len(t) == 0:
            continue
        aabbs[o.name] = (w.min(axis=0), w.max(axis=0))
        names.append(o.name)
        spans[o.name] = (t_off, len(w), len(t))
        all_verts.append(w)
        all_tris.append(t + v_off)
        v_off += len(w)
        t_off += len(t)
    sv = np.concatenate(all_verts, axis=0)
    st = np.concatenate(all_tris, axis=0)
    n_mesh = len(names)
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
    log(f"scene BVH input ready: {len(sv)} verts, {len(st)} tris, "
        f"attribution verified over {n_mesh} meshes ({time.time() - t0:.1f}s)")

    scene_bvh = BVHTree.FromPolygons([tuple(v) for v in sv],
                                     [tuple(int(i) for i in t) for t in st],
                                     all_triangles=True, epsilon=0.0)
    log(f"scene BVH built ({time.time() - t0:.1f}s)")

    # ---- ground object inventory ------------------------------------------------------------
    ground_objs = {}
    for nm, (amn, amx) in aabbs.items():
        low = nm.lower()
        if any(h in low for h in GROUND_NAME_HINTS):
            ground_objs[nm] = (amn, amx, float(max(amx - amn)))
    inv = []
    for nm, (amn, amx, md) in sorted(ground_objs.items(), key=lambda kv: -kv[1][2]):
        inv.append({"object": nm, "aabb_min": rnd(amn), "aabb_max": rnd(amx),
                    "max_dim_units": rnd(md, 4),
                    "backdrop_excluded": bool(md > BACKDROP_MAX_DIM_UNITS)})
    log(f"{len(inv)} ground-name-matched objects")

    # survey extent: the union of the NON-backdrop ground objects' XY extents
    setdress = [g for g in ground_objs.values() if g[2] <= BACKDROP_MAX_DIM_UNITS]
    if not setdress:
        raise SystemExit("no non-backdrop ground object found; widen GROUND_NAME_HINTS")
    gx0 = min(g[0][0] for g in setdress)
    gx1 = max(g[1][0] for g in setdress)
    gy0 = min(g[0][1] for g in setdress)
    gy1 = max(g[1][1] for g in setdress)
    zstart = max(g[1][2] for g in setdress) + 0.5
    log(f"survey extent x[{gx0:.2f},{gx1:.2f}] y[{gy0:.2f},{gy1:.2f}], cast from z={zstart:.2f}")

    ground_set = {nm.lower() for nm in ground_objs}
    down = Vector((0.0, 0.0, -1.0))

    def cast_grid(step):
        xs = np.arange(gx0, gx1 + 1e-9, step)
        ys = np.arange(gy0, gy1 + 1e-9, step)
        nx, ny = len(xs), len(ys)
        z_hit = np.full((nx, ny), np.nan)
        own = np.full((nx, ny), -1, dtype=np.int32)
        nz = np.full((nx, ny), np.nan)
        for i in range(nx):
            for j in range(ny):
                loc, nrm, idx, dist = scene_bvh.ray_cast(
                    Vector((float(xs[i]), float(ys[j]), float(zstart))), down, 400.0)
                if loc is None or idx is None:
                    continue
                nm = names[tri_owner[idx]]
                if nm.lower() not in ground_set:
                    continue
                if not (A.z_min <= loc.z <= A.z_max):
                    continue
                z_hit[i, j] = loc.z
                own[i, j] = int(tri_owner[idx])
                nz[i, j] = abs(float(nrm.z))
        return xs, ys, z_hit, own, nz

    def window_record(i0, j0, L, W, xs, ys, z_hit, own):
        bo = own[i0:i0 + L, j0:j0 + W]
        bz = z_hit[i0:i0 + L, j0:j0 + W]
        if np.any(bo < 0) or np.any(np.isnan(bz)):
            return None
        if int(bo.max()) != int(bo.min()):
            return None
        px = np.repeat(xs[i0:i0 + L], W)
        py = np.tile(ys[j0:j0 + W], L)
        pz = bz.ravel()
        Amat = np.column_stack([px, py, np.ones(len(px))])
        coef, *_ = np.linalg.lstsq(Amat, pz, rcond=None)
        res = pz - Amat @ coef
        return {
            "x0": float(xs[i0]), "x1": float(xs[i0 + L - 1]),
            "y0": float(ys[j0]), "y1": float(ys[j0 + W - 1]),
            "len_m": float(xs[i0 + L - 1] - xs[i0]),
            "width_m": float(ys[j0 + W - 1] - ys[j0]),
            "surface_object": names[int(bo[0, 0])],
            "grid_step_m": float(xs[1] - xs[0]),
            "n_samples": int(L * W),
            "plane": {"a_dzdx": float(coef[0]), "b_dzdy": float(coef[1]),
                      "c_z0": float(coef[2]),
                      "tilt_deg": math.degrees(math.atan(math.hypot(coef[0], coef[1])))},
            "flatness_max_dev_m": float(np.max(np.abs(res))),
            "flatness_rms_m": float(np.sqrt(np.mean(res ** 2))),
            "z_min": float(bz.min()), "z_max": float(bz.max()),
            "normal_z_min": float(np.nanmin(nz[i0:i0 + L, j0:j0 + W])),
        }

    # ---- stage A: coarse sweep ---------------------------------------------------------------
    xs, ys, z_hit, own, nz = cast_grid(A.coarse)
    nx, ny = len(xs), len(ys)
    Lc = max(2, int(round(A.len / A.coarse)) + 1)
    Wc = max(2, int(round(A.width / A.coarse)) + 1)
    log(f"stage A grid {nx}x{ny} step {A.coarse} -> block {Lc}x{Wc} cells "
        f"({(Lc - 1) * A.coarse:.2f} x {(Wc - 1) * A.coarse:.2f} m)")
    coarse = []
    for i0 in range(0, nx - Lc + 1):
        for j0 in range(0, ny - Wc + 1):
            rec = window_record(i0, j0, Lc, Wc, xs, ys, z_hit, own)
            if rec is not None:
                coarse.append(rec)
    log(f"stage A: {len(coarse)} windows land on a single ground object "
        f"({time.time() - t0:.1f}s)")
    coarse.sort(key=lambda c: c["flatness_max_dev_m"])
    log(f"stage A flattest: " + ", ".join(
        f"{c['surface_object']}@{c['x0']:.2f},{c['y0']:.2f}:{c['flatness_max_dev_m'] * 1000:.1f}mm"
        for c in coarse[:6]))

    # ---- stage B: refine around the coarse winners -------------------------------------------
    refine_centres = []
    for c in coarse:
        if c["flatness_max_dev_m"] > A.flat_tol * 3:
            break
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
        if any(abs(cx - p[0]) < 0.5 and abs(cy - p[1]) < 0.5 for p in refine_centres):
            continue
        refine_centres.append((cx, cy, c["surface_object"]))
        if len(refine_centres) >= A.refine_keep:
            break
    log(f"stage B: {len(refine_centres)} refinement centres")

    fine_finals = []
    for cx, cy, sur in refine_centres:
        ax0, ax1 = cx - A.refine_span, cx + A.refine_span
        ay0, ay1 = cy - A.refine_span, cy + A.refine_span
        fxs = np.arange(max(ax0, gx0), min(ax1, gx1) + 1e-9, A.fine)
        fys = np.arange(max(ay0, gy0), min(ay1, gy1) + 1e-9, A.fine)
        fnx, fny = len(fxs), len(fys)
        fz = np.full((fnx, fny), np.nan)
        fo = np.full((fnx, fny), -1, dtype=np.int32)
        fnz = np.full((fnx, fny), np.nan)
        for i in range(fnx):
            for j in range(fny):
                loc, nrm, idx, dist = scene_bvh.ray_cast(
                    Vector((float(fxs[i]), float(fys[j]), float(zstart))), down, 400.0)
                if loc is None or idx is None:
                    continue
                nm = names[tri_owner[idx]]
                if nm.lower() not in ground_set or not (A.z_min <= loc.z <= A.z_max):
                    continue
                fz[i, j] = loc.z
                fo[i, j] = int(tri_owner[idx])
                fnz[i, j] = abs(float(nrm.z))
        fL = max(2, int(round(A.len / A.fine)) + 1)
        fW = max(2, int(round(A.width / A.fine)) + 1)
        best = None
        for i0 in range(0, fnx - fL + 1):
            for j0 in range(0, fny - fW + 1):
                rec = window_record(i0, j0, fL, fW, fxs, fys, fz, fo)
                if rec is None:
                    continue
                if rec["surface_object"] != sur:
                    continue
                if best is None or rec["flatness_max_dev_m"] < best["flatness_max_dev_m"]:
                    best = rec
        if best is None:
            log(f"  refine centre ({cx:.2f},{cy:.2f}) {sur}: no single-object fine window "
                f"-> the coarse winner does not survive at {A.fine} m resolution")
            fine_finals.append({"refine_centre": [cx, cy], "surface_object": sur,
                                "fine_window_found": False,
                                "note": "coarse window did not survive the fine re-measurement"})
            continue
        best["refine_centre"] = [cx, cy]
        best["fine_window_found"] = True
        fine_finals.append(best)
        log(f"  refine ({cx:.2f},{cy:.2f}) -> {sur} "
            f"x[{best['x0']:.3f},{best['x1']:.3f}] y[{best['y0']:.3f},{best['y1']:.3f}] "
            f"{best['n_samples']} samples flat={best['flatness_max_dev_m'] * 1000:.3f}mm "
            f"tilt={best['plane']['tilt_deg']:.3f}deg")

    # longest fine window per surface object: the 3.0 m target may be too long for the best surface,
    # so the report must say what the longest single-object flat run actually is.
    longest = []
    for cx, cy, sur in refine_centres:
        fxs = np.arange(max(cx - A.refine_span, gx0), min(cx + A.refine_span, gx1) + 1e-9, A.fine)
        fys = np.arange(max(cy - A.refine_span, gy0), min(cy + A.refine_span, gy1) + 1e-9, A.fine)
        fnx, fny = len(fxs), len(fys)
        fz = np.full((fnx, fny), np.nan)
        fo = np.full((fnx, fny), -1, dtype=np.int32)
        for i in range(fnx):
            for j in range(fny):
                loc, nrm, idx, dist = scene_bvh.ray_cast(
                    Vector((float(fxs[i]), float(fys[j]), float(zstart))), down, 400.0)
                if loc is None or idx is None:
                    continue
                nm = names[tri_owner[idx]]
                if nm.lower() not in ground_set or not (A.z_min <= loc.z <= A.z_max):
                    continue
                fz[i, j] = loc.z
                fo[i, j] = int(tri_owner[idx])
        fW = max(2, int(round(A.width / A.fine)) + 1)
        # grow the length along x while one object persists and the plane stays within tolerance
        best_run = None
        for i0 in range(fnx):
            for j0 in range(fny - fW + 1):
                own0 = fo[i0, j0:j0 + fW]
                if np.any(own0 < 0) or int(own0.max()) != int(own0.min()):
                    continue
                if names[int(own0[0])] != sur:
                    continue
                L = fW and 0
                for L in range(fW, fnx - i0 + 1):
                    rec = window_record(i0, j0, L, fW, fxs, fys, fz, fo)
                    if rec is None or rec["flatness_max_dev_m"] > A.flat_tol:
                        break
                    if best_run is None or rec["len_m"] > best_run["len_m"]:
                        best_run = rec
        if best_run is not None:
            longest.append(best_run)
            log(f"  longest flat single-object run near ({cx:.2f},{cy:.2f}) {sur}: "
                f"{best_run['len_m']:.3f} x {best_run['width_m']:.3f} m, "
                f"flat={best_run['flatness_max_dev_m'] * 1000:.3f}mm")

    # ---- obstacle + background checks on the fine winners ------------------------------------
    scene_items = [(nm, ab[0], ab[1]) for nm, ab in aabbs.items()]
    for c in fine_finals:
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
                             "overlap_z_top_above_ground_m": rnd(min(amx[2], hi[2]) - zc, 5)})
        hits.sort(key=lambda h: -h["overlap_volume_m3"])
        c["obstacle_check"] = {
            "standup_volume_min": rnd(lo), "standup_volume_max": rnd(hi),
            "pad_m": A.pad, "headroom_m": A.headroom,
            "objects_overlapping": len(hits), "overlapping": hits,
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
                 "hit_z_m": rnd(float(loc.z), 4), "normal_z_abs": rnd(abs(float(nrm.z)), 5)})
        # how far the surface extends in x before the owner changes: the usable chain length
        c["surface_run_lengths_m"] = {}
        for c2 in longest:
            if c2["surface_object"] == c["surface_object"]:
                c["surface_run_lengths_m"]["longest_flat_run_in_refine_box"] = c2["len_m"]

    out = {
        "blend": A.blend,
        "generated_unix": time.time(),
        "parameters": {
            "coarse_step_m": A.coarse, "fine_step_m": A.fine,
            "target_len_m": A.len, "target_width_m": A.width,
            "flat_tol_m": A.flat_tol, "headroom_m": A.headroom, "pad_m": A.pad,
            "z_window_m": [A.z_min, A.z_max],
            "backdrop_max_dim_units": BACKDROP_MAX_DIM_UNITS,
            "ground_name_hints": list(GROUND_NAME_HINTS),
        },
        "method": (
            "downward ray grid against a BVH of the whole scene; a cell is ground only if the "
            "topmost hit object's name matches the ground hints AND the hit z lies in the z window "
            "(so the huge backdrop floor/sky planes cannot be reported as the alley ground). All "
            "cells in a window must hit the SAME object. Flatness is the max |residual| from a "
            "least-squares plane over the window's hit points at the FINE grid step. The obstacle "
            "check intersects the stand-up volume with every scene object's world AABB and lists "
            "each overlapping object with its overlap volume."
        ),
        "scene": {
            "mesh_objects": len(meshes),
            "ground_inventory": inv,
            "survey_extent": {"x": [float(gx0), float(gx1)], "y": [float(gy0), float(gy1)],
                              "cast_from_z": float(zstart)},
            "stage_a_grid": {"nx": nx, "ny": ny, "step_m": A.coarse,
                             "single_object_windows": len(coarse)},
        },
        "stage_a_coarse_windows": coarse[:60],
        "fine_final_windows": fine_finals,
        "longest_flat_runs": longest,
        "runtime_s": rnd(time.time() - t0, 2),
    }
    with open(A.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

    # a coarse owner map, so the report shows the surface layout rather than asserting it
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    legend = {}
    with open(A.out.replace(".json", "_gridmap.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"COARSE OWNER MAP  rows={ny} cols={nx} step={A.coarse} "
                 f"x0={xs[0]:.3f} y0={ys[0]:.3f}  (top row = max y, left col = min x)\n")
        fh.write("'.' = no ground-named hit in the z window\n\n")
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
