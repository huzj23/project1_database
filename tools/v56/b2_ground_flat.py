"""b2_ground_flat.py -- measure the Hidden Alley support surface well enough to CHOOSE a chain line.

WHAT WENT WRONG IN THE FIRST TWO ATTEMPTS (kept in the report, not hidden)
-------------------------------------------------------------------------
Attempt 1 surveyed the whole scene and `BG_floor` (an ~810-unit backdrop plane) won every window: a
backdrop plane is trivially "one object, zero deviation". Attempt 2 restricted the ground to
`Floor_main` + `stones` but required EVERY cell of a window to hit the SAME object, which threw away
every corridor wider than 12 cm because `stones` is a pebble scatter whose pebbles sit between the
`Floor_main` cells. It also tested obstacles with world AABBs, so `Sky` and `light_blocker_` -- whose
boxes enclose the entire set -- were reported as blocking a 12 cm patch of pavement.

WHAT THIS VERSION DOES
----------------------
1. ONE fine downward ray grid over the alley floor. A cell's value is the topmost hit among the
   native ground objects (`Floor_main`, `stones`) inside a z window; every other object is scenery.
2. Every axis-aligned window up to max_len x max_width is evaluated through summed-area tables for
   the exact plane-fit normal equations. For a plane z = a x + b y + c the residual sum of squares has
   the closed form SSE = Szz - coef . (Sxz, Syz, Sz), and every moment is a prefix sum, so the search
   is exact and needs no sampling.
3. THREE things are reported per window, because "one object" was the wrong single criterion:
     * `flatness_max_dev_m` -- max |residual| from the window's own least-squares plane.
     * `stones_fraction` and `max_step_between_objects_m` -- how much of the window is the pebble
       layer, and the largest height jump between horizontally adjacent cells of DIFFERENT objects,
       i.e. the actual pebble lip a box base would have to clear.
     * `per_station_footprint` -- for BOX_PITCH_M-spaced stations along the window, the relief inside
       that station's own box footprint (BOX_FOOTPRINT_M), and the tilt a box would take if it rested
       on the three highest points of that footprint. This is the number that decides whether a box
       can stand: a box of thickness t tips at atan(t/h), so for these assets the budget is small.
4. Obstacles are measured GEOMETRICALLY, by rays, not by AABB: an upward ray per footprint cell to
   `headroom`, and lateral rays at several heights along and across the corridor. A 810-unit sky box
   no longer "blocks" pavement it does not touch. Every blocking object is named.

Run:
  & '<blender.exe>' --background --factory-startup --python b2_ground_flat.py -- \
        --blend <scene.blend> --out <report.json> [--step 0.03] [--max-len 3.0] [--max-width 0.90]
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

GROUND_OBJECTS = ("Floor_main", "stones")

#: A Cranium is 0.2077 wide and 0.0558 thick; the widest asset is 0.2755 wide. The footprint used for
#: the per-station relief measurement is the union of the real footprints, so the measurement is not
#: tuned to one asset.
BOX_FOOTPRINT_M = (0.28, 0.085)
#: Centre-to-centre pitch of a Cranium-at-0.25h chain: thickness + gap = 0.0558 + 0.0681.
BOX_PITCH_M = 0.124


def log(*a):
    print("[b2_flat]", *a, flush=True)


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


def prefix(a):
    """Summed-area table with a zero row/column."""
    return np.pad(np.cumsum(np.cumsum(a, axis=0), axis=1), ((1, 0), (1, 0)), mode="constant")


def rectsum(P, i0, i1, j0, j1):
    return P[i1, j1] - P[i0, j1] - P[i1, j0] + P[i0, j0]


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ground", default=",".join(GROUND_OBJECTS))
    ap.add_argument("--step", type=float, default=0.03)
    ap.add_argument("--max-len", type=float, default=3.0)
    ap.add_argument("--max-width", type=float, default=0.90)
    ap.add_argument("--len-step", type=float, default=0.15)
    ap.add_argument("--width-step", type=float, default=0.15)
    ap.add_argument("--z-window", type=float, nargs=2, default=[-0.40, 0.60])
    ap.add_argument("--headroom", type=float, default=1.20)
    ap.add_argument("--pad", type=float, default=0.10)
    ap.add_argument("--search-top", type=int, default=600,
                    help="how many SSE-ranked positions per bucket to re-score exactly")
    A = ap.parse_args(args)
    ground_names = [g.strip() for g in A.ground.split(",") if g.strip()]
    t0 = time.time()

    bpy.ops.wm.open_mainfile(filepath=A.blend)
    sc = bpy.context.scene
    meshes = [o for o in sc.objects if o.type == "MESH"]
    dg = bpy.context.evaluated_depsgraph_get()

    all_verts, all_tris, spans, names, aabbs = [], [], {}, [], {}
    v_off = t_off = 0
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
    tri_owner = np.empty(len(st), dtype=np.int32)
    for i, nm in enumerate(names):
        base, nv, nt = spans[nm]
        tri_owner[base:base + nt] = i
    _off = 0
    for nm in names:
        base, nv, nt = spans[nm]
        assert base == _off, f"span bookkeeping broken at {nm}: {base} != {_off}"
        _off += nt
    assert _off == len(st), f"span total {_off} != {len(st)}"
    counts = np.bincount(tri_owner, minlength=n_mesh)
    for i, nm in enumerate(names):
        assert counts[i] == spans[nm][2], f"tri_owner wrong for {nm}"
    log(f"triangle soup {len(sv)} verts / {len(st)} tris, attribution verified "
        f"({time.time() - t0:.1f}s)")
    scene_bvh = BVHTree.FromPolygons([tuple(v) for v in sv],
                                     [tuple(int(i) for i in t) for t in st],
                                     all_triangles=True, epsilon=0.0)
    log(f"scene BVH built ({time.time() - t0:.1f}s)")
    gset = {g.lower() for g in ground_names}

    def cast_down_grid(ax0, ax1, ay0, ay1, step, zfrom):
        xs = np.arange(ax0, ax1 + 1e-9, step)
        ys = np.arange(ay0, ay1 + 1e-9, step)
        nx, ny = len(xs), len(ys)
        z = np.full((nx, ny), np.nan)
        own = np.full((nx, ny), -1, dtype=np.int32)
        nz = np.full((nx, ny), np.nan)
        down = Vector((0.0, 0.0, -1.0))
        for i in range(nx):
            for j in range(ny):
                loc, nrm, idx, dist = scene_bvh.ray_cast(
                    Vector((float(xs[i]), float(ys[j]), zfrom)), down, 400.0)
                if loc is None or idx is None:
                    continue
                nm = names[tri_owner[idx]]
                if nm.lower() not in gset or not (A.z_window[0] <= loc.z <= A.z_window[1]):
                    continue
                z[i, j] = loc.z
                own[i, j] = int(tri_owner[idx])
                nz[i, j] = abs(float(nrm.z))
        return xs, ys, z, own, nz

    gmin = np.min([aabbs[g][0] for g in ground_names], axis=0)
    gmax = np.max([aabbs[g][1] for g in ground_names], axis=0)
    zstart = float(gmax[2]) + 0.30
    xs, ys, z, own, nz = cast_down_grid(gmin[0], gmax[0], gmin[1], gmax[1], A.step, zstart)
    nx, ny = len(xs), len(ys)
    log(f"grid {nx}x{ny} step {A.step}: {int(np.sum(own >= 0))}/{nx * ny} cells on ground "
        f"({time.time() - t0:.1f}s)")
    if int(np.sum(own >= 0)) < 100:
        raise SystemExit("almost no ground cells; check --z-window / --ground")

    # ---- exact plane-fit machinery -----------------------------------------------------------
    valid = (own >= 0).astype(np.float64)
    XX = np.repeat(xs[:, None], ny, axis=1)
    YY = np.repeat(ys[None, :], nx, axis=0)
    Z = np.where(own >= 0, z, 0.0)
    stone_id = None
    for i, nm in enumerate(names):
        if nm == "stones":
            stone_id = i
    Pp = {"n": prefix(valid), "x": prefix(XX * valid), "y": prefix(YY * valid), "z": prefix(Z),
          "xx": prefix(XX * XX * valid), "xy": prefix(XX * YY * valid),
          "yy": prefix(YY * YY * valid), "xz": prefix(XX * Z), "yz": prefix(YY * Z),
          "zz": prefix(Z * Z),
          "stone": prefix((own == stone_id).astype(np.float64)) if stone_id is not None else None}
    # adjacent-cell step between DIFFERENT ground objects, as the pebble lip a base must clear
    step_arr = np.zeros((nx, ny))
    for axis, a in (("x", 0), ("y", 1)):
        if a == 0:
            o1, o2 = own[1:, :], own[:-1, :]
            z1, z2 = z[1:, :], z[:-1, :]
        else:
            o1, o2 = own[:, 1:], own[:, :-1]
            z1, z2 = z[:, 1:], z[:, :-1]
        m = (o1 >= 0) & (o2 >= 0) & (o1 != o2)
        if a == 0:
            step_arr[1:, :] = np.where(m, np.abs(z1 - z2), 0.0)
        else:
            step_arr[:, 1:] = np.where(m, np.abs(z1 - z2), 0.0)
    Pst = prefix(step_arr)

    def window_stats(i0, j0, L, W):
        bo = own[i0:i0 + L, j0:j0 + W]
        bz = z[i0:i0 + L, j0:j0 + W]
        if np.any(bo < 0) or np.any(np.isnan(bz)):
            return None
        n = float(L * W)
        sx = float(rectsum(Pp["x"], i0, i0 + L, j0, j0 + W))
        sy = float(rectsum(Pp["y"], i0, i0 + L, j0, j0 + W))
        sz = float(rectsum(Pp["z"], i0, i0 + L, j0, j0 + W))
        sxx = float(rectsum(Pp["xx"], i0, i0 + L, j0, j0 + W))
        sxy = float(rectsum(Pp["xy"], i0, i0 + L, j0, j0 + W))
        syy = float(rectsum(Pp["yy"], i0, i0 + L, j0, j0 + W))
        sxz = float(rectsum(Pp["xz"], i0, i0 + L, j0, j0 + W))
        syz = float(rectsum(Pp["yz"], i0, i0 + L, j0, j0 + W))
        szz = float(rectsum(Pp["zz"], i0, i0 + L, j0, j0 + W))
        M = np.array([[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]])
        rhs = np.array([sxz, syz, sz])
        if abs(np.linalg.det(M)) < 1e-14:
            return None
        coef = np.linalg.solve(M, rhs)
        px = np.repeat(xs[i0:i0 + L], W)
        py = np.tile(ys[j0:j0 + W], L)
        pz = bz.ravel()
        res = pz - (coef[0] * px + coef[1] * py + coef[2])
        ar = np.abs(res)
        nstone = (float(rectsum(Pp["stone"], i0, i0 + L, j0, j0 + W))
                  if Pp["stone"] is not None else 0.0)
        maxstep = float(rectsum(Pst, i0, i0 + L, j0, j0 + W))
        bn = nz[i0:i0 + L, j0:j0 + W]
        return {
            "x0": float(xs[i0]), "x1": float(xs[i0 + L - 1]),
            "y0": float(ys[j0]), "y1": float(ys[j0 + W - 1]),
            "len_m": float(xs[i0 + L - 1] - xs[i0]),
            "width_m": float(ys[j0 + W - 1] - ys[j0]),
            "grid_step_m": float(xs[1] - xs[0]), "n_samples": int(L * W),
            "surface_objects_present": sorted({names[int(v)] for v in np.unique(bo)}),
            "stones_fraction": round(nstone / n, 6),
            "max_step_between_objects_m": round(maxstep, 6),
            "plane": {"a_dzdx": float(coef[0]), "b_dzdy": float(coef[1]),
                      "c_z_at_origin": float(coef[2]),
                      "tilt_deg": math.degrees(math.atan(math.hypot(coef[0], coef[1])))},
            "flatness_max_dev_m": float(ar.max()),
            "flatness_p95_dev_m": float(np.percentile(ar, 95)),
            "flatness_rms_m": float(np.sqrt(np.mean(res ** 2))),
            "residual_profile_along_x_m": rnd(res.reshape(L, W).mean(axis=1).tolist(), 6),
            "z_min": float(pz.min()), "z_max": float(pz.max()),
            "z_span_m": float(pz.max() - pz.min()),
            "normal_z_min": (None if np.all(np.isnan(bn)) else float(np.nanmin(bn))),
            "normal_z_mean": (None if np.all(np.isnan(bn)) else float(np.nanmean(bn))),
            "_res_2d": res.reshape(L, W), "_coef": coef,
        }

    # ---- per-station footprint support: how would a BOX actually sit along this window? --------
    def station_support(rec):
        """For each box station along the window, the relief inside its own footprint."""
        L, W = rec["n_samples"] // 1, 0
        res2 = rec["_res_2d"]
        Ln, Wn = res2.shape
        coef = rec["_coef"]
        i0 = int(round((rec["x0"] - xs[0]) / (xs[1] - xs[0])))
        j0 = int(round((rec["y0"] - ys[0]) / (ys[1] - ys[0])))
        # footprint cells in each direction
        fL = max(2, int(round(BOX_FOOTPRINT_M[0] / (xs[1] - xs[0]))))
        fW = max(2, int(round(BOX_FOOTPRINT_M[1] / (ys[1] - ys[0]))))
        pitch = max(1, int(round(BOX_PITCH_M / (xs[1] - xs[0]))))
        out = []
        k = 0
        while True:
            ii = k * pitch
            if ii + fL > Ln:
                break
            for jj_choice in (0, max(0, (Wn - fW) // 2), max(0, Wn - fW)):
                if jj_choice + fW > Wn:
                    continue
                bo = own[i0 + ii:i0 + ii + fL, j0 + jj_choice:j0 + jj_choice + fW]
                bz = z[i0 + ii:i0 + ii + fL, j0 + jj_choice:j0 + jj_choice + fW]
                if np.any(bo < 0) or np.any(np.isnan(bz)):
                    continue
                # world x/y of these cells, then residual against the WINDOW's plane so the number
                # is "how far this footprint departs from the chain line's support plane"
                wx = np.repeat(xs[i0 + ii:i0 + ii + fL], fW)
                wy = np.tile(ys[j0 + jj_choice:j0 + jj_choice + fW], fL)
                wz = bz.ravel()
                r = wz - (coef[0] * wx + coef[1] * wy + coef[2])
                # the box rests on the local high points: tilt from the 3 highest sample points
                top = np.argsort(-wz)[:3]
                if len(top) >= 3:
                    P3 = np.column_stack([wx[top], wy[top], wz[top]])
                    v1 = P3[1] - P3[0]
                    v2 = P3[2] - P3[0]
                    nrm = np.cross(v1, v2)
                    nl = np.linalg.norm(nrm)
                    tilt = (math.degrees(math.acos(min(1.0, abs(nrm[2]) / nl)))
                            if nl > 1e-12 else 0.0)
                else:
                    tilt = 0.0
                out.append({
                    "station_index": k, "x_centre_m": float(np.mean(wx)),
                    "y_centre_m": float(np.mean(wy)),
                    "footprint_m": [float(wx.max() - wx.min()), float(wy.max() - wy.min())],
                    "relief_vs_chain_plane_max_m": float(np.max(np.abs(r))),
                    "relief_vs_chain_plane_min_m": float(r.min()),
                    "relief_vs_chain_plane_max_positive_m": float(r.max()),
                    "tilt_if_resting_on_3_highest_deg": tilt,
                    "objects": sorted({names[int(v)] for v in np.unique(bo)}),
                })
            k += 1
        return out

    # ---- search ------------------------------------------------------------------------------
    lens = sorted({max(2, int(round(v / A.step)))
                   for v in np.arange(A.len_step, A.max_len + 1e-9, A.len_step)})
    widths = sorted({max(2, int(round(v / A.step)))
                     for v in np.arange(A.width_step, A.max_width + 1e-9, A.width_step)})
    log(f"buckets: {len(lens)} lengths, {len(widths)} widths")

    def sse_grid(L, W):
        i1 = np.arange(L, nx + 1)
        j1 = np.arange(W, ny + 1)
        I1, J1 = np.meshgrid(i1, j1, indexing="ij")
        I0, J0 = I1 - L, J1 - W
        n = rectsum(Pp["n"], I0, I1, J0, J1)
        good = n >= L * W
        if not np.any(good):
            return None
        s = {k: rectsum(Pp[k], I0, I1, J0, J1) for k in
             ("x", "y", "z", "xx", "xy", "yy", "xz", "yz", "zz")}
        shape = n.shape
        M = np.empty(shape + (3, 3))
        M[..., 0, 0], M[..., 0, 1], M[..., 0, 2] = s["xx"], s["xy"], s["x"]
        M[..., 1, 0], M[..., 1, 1], M[..., 1, 2] = s["xy"], s["yy"], s["y"]
        M[..., 2, 0], M[..., 2, 1], M[..., 2, 2] = s["x"], s["y"], n
        rhs = np.stack([s["xz"], s["yz"], s["z"]], axis=-1)
        Mf, rf = M.reshape(-1, 3, 3), rhs.reshape(-1, 3)
        det = np.linalg.det(Mf)
        solvable = (np.abs(det) > 1e-14).reshape(shape)
        sol = np.zeros_like(rf)
        flat = solvable.ravel()
        sol[flat] = np.linalg.solve(Mf[flat], rf[flat])
        coef = sol.reshape(shape + (3,))
        sse = s["zz"] - np.einsum("...i,...i->...", coef, rhs)
        sse = np.where(solvable & good, np.maximum(sse, 0.0), np.inf)
        return {"I0": I0, "J0": J0, "sse": sse}

    refined = []
    for L in lens:
        for W in widths:
            g = sse_grid(L, W)
            if g is None:
                continue
            order = np.argsort(g["sse"], axis=None)[:A.search_top]
            best = None
            for kk in order:
                k = np.unravel_index(kk, g["sse"].shape)
                if not np.isfinite(g["sse"][k]):
                    break
                rec = window_stats(int(g["I0"][k]), int(g["J0"][k]), L, W)
                if rec is None:
                    continue
                if best is None or rec["flatness_max_dev_m"] < best["flatness_max_dev_m"]:
                    best = rec
            if best is not None:
                refined.append(best)
    log(f"scored {len(refined)} (length,width) buckets ({time.time() - t0:.1f}s)")

    # flattest per length, and the per-station support for the top candidates
    per_len = {}
    for rec in refined:
        key = round(rec["len_m"], 4)
        if key not in per_len or rec["flatness_max_dev_m"] < per_len[key]["flatness_max_dev_m"]:
            per_len[key] = rec
    flat_curve = [per_len[k] for k in sorted(per_len)]

    top = sorted(refined, key=lambda c: c["flatness_max_dev_m"])[:30]
    for rec in top:
        rec["per_station_footprint"] = station_support(rec)

    # ---- geometric obstacle check (rays, not AABBs) -----------------------------------------
    def obstacle_report(rec):
        x0, x1 = rec["x0"], rec["x1"]
        y0, y1 = rec["y0"], rec["y1"]
        i0 = int(round((x0 - xs[0]) / (xs[1] - xs[0])))
        j0 = int(round((y0 - ys[0]) / (ys[1] - ys[0])))
        L = int(round(rec["len_m"] / (xs[1] - xs[0]))) + 1
        W = int(round(rec["width_m"] / (ys[1] - ys[0]))) + 1
        blockers = {}

        def note(nm, where, dist):
            e = blockers.setdefault(nm, {"count": 0, "examples": []})
            e["count"] += 1
            if len(e["examples"]) < 4:
                e["examples"].append({"where": where, "distance_m": rnd(dist, 4)})

        up = Vector((0.0, 0.0, 1.0))
        n_up = 0
        for i in range(0, L, 3):
            for j in range(0, W, 3):
                if i0 + i >= nx or j0 + j >= ny or own[i0 + i, j0 + j] < 0:
                    continue
                o = Vector((float(xs[i0 + i]), float(ys[j0 + j]), float(z[i0 + i, j0 + j]) + 0.002))
                loc, nrm, idx, dist = scene_bvh.ray_cast(o, up, A.headroom)
                n_up += 1
                if loc is not None:
                    note(names[tri_owner[idx]], [round(float(o.x), 3), round(float(o.y), 3)],
                         dist)
        # lateral rays at several heights, across the corridor, from stations along it
        lat = {}
        for h in (0.03, 0.08, 0.15, 0.30, 0.60):
            for dn, dv in (("+y", (0.0, 1.0, 0.0)), ("-y", (0.0, -1.0, 0.0)),
                           ("+x", (1.0, 0.0, 0.0)), ("-x", (-1.0, 0.0, 0.0))):
                hits = {}
                for frac in (0.05, 0.5, 0.95):
                    xx = x0 + frac * (x1 - x0)
                    # start just inside the footprint of the first/last box, offset across the chain
                    o = Vector((xx, (y0 + y1) / 2.0, float(z[i0 + int(frac * (L - 1)),
                                                             j0 + W // 2]) + h))
                    loc, nrm, idx, dist = scene_bvh.ray_cast(o, Vector(dv), 40.0)
                    nm = None if loc is None else names[tri_owner[idx]]
                    if nm is not None:
                        hits.setdefault(nm, []).append(round(dist, 4))
                        note(nm, f"lateral {dn} at h={h} frac={frac}", dist)
                lat[f"h{h}_{dn}"] = hits
        return {"upward_rays_cast": n_up, "headroom_m": A.headroom,
                "lateral_ray_hits": lat, "blockers": blockers,
                "blocking_objects": sorted(blockers), "obstacle_free": len(blockers) == 0}

    for rec in top[:12]:
        rec["obstacle_check_geometric"] = obstacle_report(rec)
        cx, cy = (rec["x0"] + rec["x1"]) / 2, (rec["y0"] + rec["y1"]) / 2
        ci = int(round((rec["x0"] - xs[0]) / (xs[1] - xs[0])))
        cj = int(round((rec["y0"] - ys[0]) / (ys[1] - ys[0])))
        zc = float(z[ci, cj])
        rec["background_rays"] = {}
        for dn, dv in (("perp_plus_y", (0.0, 1.0, 0.0)), ("perp_minus_y", (0.0, -1.0, 0.0)),
                       ("along_plus_x", (1.0, 0.0, 0.0)), ("along_minus_x", (-1.0, 0.0, 0.0))):
            loc, nrm, idx, dist = scene_bvh.ray_cast(Vector((cx, cy, zc + 0.20)), Vector(dv), 80.0)
            rec["background_rays"][dn] = (
                {"hit": None, "note": "ray escaped the scene"} if loc is None else
                {"hit_object": names[tri_owner[idx]], "distance_m": rnd(dist, 4),
                 "normal_z_abs": rnd(abs(float(nrm)), 5)})

    for rec in refined + top:
        rec.pop("_res_2d", None)
        rec.pop("_coef", None)

    out = {
        "blend": A.blend,
        "generated_unix": time.time(),
        "parameters": {
            "ground_objects": ground_names, "step_m": A.step, "max_len_m": A.max_len,
            "max_width_m": A.max_width, "z_window_m": A.z_window, "headroom_m": A.headroom,
            "box_footprint_m": list(BOX_FOOTPRINT_M), "box_pitch_m": BOX_PITCH_M,
        },
        "method": (
            "one fine downward ray grid over the native ground; every axis-aligned window up to "
            "max_len x max_width scored by the EXACT plane-fit SSE via summed-area tables "
            "(SSE = Szz - coef . (Sxz,Syz,Sz)); the top candidates per bucket re-scored with an "
            "explicit least-squares fit. Flatness = max |residual| from the window's own plane. "
            "Per-station footprints report the relief against that plane and the tilt a box would "
            "take resting on the three highest sample points inside its own base. Obstacles are "
            "measured by rays (upward per footprint cell, lateral at five heights), never by AABB, "
            "so a backdrop box that encloses the set cannot be misreported as blocking pavement."
        ),
        "ground_object_aabbs": {g: {"min": rnd(aabbs[g][0]), "max": rnd(aabbs[g][1])}
                                for g in ground_names},
        "grid": {"x": [float(xs[0]), float(xs[-1])], "y": [float(ys[0]), float(ys[-1])],
                 "nx": nx, "ny": ny, "step_m": A.step, "cast_from_z": zstart,
                 "cells_on_ground": int(np.sum(own >= 0))},
        "flatness_vs_length_best_width": flat_curve,
        "top30_flattest_windows": top,
        "runtime_s": rnd(time.time() - t0, 2),
    }
    with open(A.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    log(f"written {A.out} in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
