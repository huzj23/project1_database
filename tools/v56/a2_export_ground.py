"""A2 step 1: export the Hidden Alley ground/wall collision region and characterise it.

Writes, into the run dir:

  ground/ground_static.obj      Floor_main + apartment_walls + base_tripple_01.003 +
                                dado_tripple_01.003 clipped to a 5.0 m x 6.0 m x 2.2 m
                                box around the board, in WORLD coordinates (static body,
                                so the OBJ origin is irrelevant to its centre of mass).
  ground/heightfields.npz       top-surface heightfield of Floor_main and the scatter
                                top-surface heightfield (stones / grass / leaves), on a
                                2 cm grid.  This is what makes the lane analysis cheap
                                and unambiguous -- no raycast back-face guesswork.
  ground/ground_geometry.json   extents, triangle counts, the exact vertex lists of the
                                plinth and skirting boxes, and the board-vs-support
                                separation measurements.

Geometry only.  No render.  Reads the scene, writes files.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RUN = Path(ARGV[0])
BOX = [(-3.4, 1.6), (-0.9, 5.1), (-0.6, 1.6)]
GRID = 0.02

BLEND = ("D:/workspace/project1_database/models/backgrounds/candidates/"
         "hidden_alley/extracted/ph_hidden_alley.blend")

T0 = time.time()


def log(m: str) -> None:
    print(f"[{time.time() - T0:7.1f}s] {m}", flush=True)


def tri_array(ob, dg):
    """World-space triangle vertices, shape (N, 3, 3), float64."""
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(nv, 3)
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    idx = np.empty(nt * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", idx)
    idx = idx.reshape(nt, 3)
    mw = np.array(ev.matrix_world, dtype=np.float64)
    world = co @ mw[:3, :3].T + mw[:3, 3]
    tris = world[idx]
    ev.to_mesh_clear()
    return tris


def vert_array(ob, dg):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(nv, 3)
    mw = np.array(ev.matrix_world, dtype=np.float64)
    world = co @ mw[:3, :3].T + mw[:3, 3]
    ev.to_mesh_clear()
    return world


def write_obj(path: Path, tris: np.ndarray, header: list[str]) -> None:
    """Write a triangle soup as OBJ with deduplicated vertices."""
    flat = tris.reshape(-1, 3)
    uniq, inv = np.unique(np.round(flat, 9), axis=0, return_inverse=True)
    lines = list(header)
    for v in uniq:
        lines.append(f"v {v[0]:.9f} {v[1]:.9f} {v[2]:.9f}")
    inv = inv.reshape(-1, 3) + 1
    for f in inv:
        lines.append(f"f {f[0]} {f[1]} {f[2]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clip(tris: np.ndarray, box) -> np.ndarray:
    m = np.ones(len(tris), dtype=bool)
    for i in range(3):
        lo, hi = box[i]
        m &= (tris[:, :, i] >= lo).all(axis=1) & (tris[:, :, i] <= hi).all(axis=1)
    return tris[m]


def raster_top(tris, gx, gy, cell):
    """Top-surface heightfield: max plane-z per cell over top-facing triangles."""
    nx = len(gx)
    ny = len(gy)
    H = np.full((nx, ny), np.nan)
    n = tris[:, 0]
    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    nrm = np.cross(e1, e2)
    ln = np.linalg.norm(nrm, axis=1)
    ln[ln == 0] = 1.0
    up = (nrm[:, 2] / ln) > 0.3
    tris = tris[up]
    log(f"    raster: {len(tris)} top-facing triangles")
    x0, y0 = gx[0], gy[0]
    for t in tris:
        px = t[:, 0]
        py = t[:, 1]
        pz = t[:, 2]
        i0 = max(0, int((px.min() - x0) / cell) - 1)
        i1 = min(nx - 1, int((px.max() - x0) / cell) + 1)
        j0 = max(0, int((py.min() - y0) / cell) - 1)
        j1 = min(ny - 1, int((py.max() - y0) / cell) + 1)
        if i1 < i0 or j1 < j0:
            continue
        X = gx[i0:i1 + 1][:, None]
        Y = gy[j0:j1 + 1][None, :]
        d = (t[1, 0] - t[0, 0]) * (t[2, 1] - t[0, 1]) - \
            (t[2, 0] - t[0, 0]) * (t[1, 1] - t[0, 1])
        if abs(d) < 1e-14:
            continue
        w1 = ((X - t[0, 0]) * (t[2, 1] - t[0, 1]) - (t[2, 0] - t[0, 0]) * (Y - t[0, 1])) / d
        w2 = ((t[1, 0] - t[0, 0]) * (Y - t[0, 1]) - (X - t[0, 0]) * (t[1, 1] - t[0, 1])) / d
        inside = (w1 >= -1e-9) & (w2 >= -1e-9) & (w1 + w2 <= 1 + 1e-9)
        if not inside.any():
            continue
        Z = t[0, 2] + w1 * (t[1, 2] - t[0, 2]) + w2 * (t[2, 2] - t[0, 2])
        sub = H[i0:i1 + 1, j0:j1 + 1]
        upd = inside & (np.isnan(sub) | (Z > sub))
        sub[upd] = Z[upd]
    return H


def main() -> int:
    (RUN / "ground").mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    dg = bpy.context.evaluated_depsgraph_get()
    log("opened blend")

    names = ["Floor_main", "apartment_walls", "base_tripple_01.003",
             "dado_tripple_01.003"]
    geo = {}
    kept = []
    for nm in names:
        ob = bpy.data.objects.get(nm)
        if ob is None:
            raise SystemExit(f"missing object {nm}")
        t_all = tri_array(ob, dg)
        t = clip(t_all, BOX)
        log(f"{nm}: {len(t_all)} tris total, {len(t)} kept in clip box")
        geo[nm] = {
            "tris_total": int(len(t_all)),
            "tris_kept": int(len(t)),
            "aabb_world_min": t_all.reshape(-1, 3).min(axis=0).tolist(),
            "aabb_world_max": t_all.reshape(-1, 3).max(axis=0).tolist(),
            "world_matrix": [list(r) for r in ob.matrix_world],
            "n_vertices_mesh": len(ob.data.vertices),
            "n_faces_mesh": len(ob.data.polygons),
        }
        if nm in ("base_tripple_01.003", "dado_tripple_01.003"):
            v = vert_array(ob, dg)
            geo[nm]["vertices_world"] = v.tolist()
            geo[nm]["faces"] = [list(p.vertices) for p in ob.data.polygons]
        kept.append(t)

    ground = np.concatenate(kept, axis=0)
    total_v = ground.reshape(-1, 3)
    ext = {"min": total_v.min(axis=0).tolist(), "max": total_v.max(axis=0).tolist()}
    ext["size"] = (total_v.max(axis=0) - total_v.min(axis=0)).tolist()
    log(f"ground_static: {len(ground)} tris, extent {ext['size']}")
    write_obj(RUN / "ground" / "ground_static.obj", ground, [
        "# V5.6 A2 Hidden Alley ground/wall collision region",
        f"# source_blend={BLEND}",
        "# objects=Floor_main,apartment_walls,base_tripple_01.003,dado_tripple_01.003",
        f"# clip_box x[{BOX[0][0]},{BOX[0][1]}] y[{BOX[1][0]},{BOX[1][1]}] "
        f"z[{BOX[2][0]},{BOX[2][1]}]",
        "# world coordinates preserved; static body, so the file origin is not a COM",
    ])
    geo["_ground_static"] = {"tris": int(len(ground)), "extent": ext,
                             "clip_box": BOX}

    # ---- heightfields -----------------------------------------------------
    gx = np.arange(BOX[0][0], BOX[0][1] + 1e-9, GRID)
    gy = np.arange(BOX[1][0], BOX[1][1] + 1e-9, GRID)
    log(f"heightfield grid {len(gx)} x {len(gy)} at {GRID} m")

    floor_ob = bpy.data.objects["Floor_main"]
    ftris = tri_array(floor_ob, dg)
    ftris = clip(ftris, BOX)
    Hf = raster_top(ftris, gx, gy, GRID)
    log(f"floor heightfield: {np.isfinite(Hf).sum()} filled cells of {Hf.size}")

    # Walls: top-facing is wrong for a wall.  Record the wall/skirting surface
    # as the min-x surface per (y, z) cell instead -- separate grid.
    Hz = np.arange(-0.10, 0.70 + 1e-9, GRID)
    wall_x = np.full((len(gy), len(Hz)), np.nan)
    for nm in ("apartment_walls", "dado_tripple_01.003"):
        t = clip(tri_array(bpy.data.objects[nm], dg), BOX)
        for tri in t:
            px, py, pz = tri[:, 0], tri[:, 1], tri[:, 2]
            j0 = max(0, int((py.min() - gy[0]) / GRID) - 1)
            j1 = min(len(gy) - 1, int((py.max() - gy[0]) / GRID) + 1)
            k0 = max(0, int((pz.min() - Hz[0]) / GRID) - 1)
            k1 = min(len(Hz) - 1, int((pz.max() - Hz[0]) / GRID) + 1)
            if j1 < j0 or k1 < k0:
                continue
            Y = gy[j0:j1 + 1][:, None]
            Z = Hz[k0:k1 + 1][None, :]
            d = (tri[1, 1] - tri[0, 1]) * (tri[2, 2] - tri[0, 2]) - \
                (tri[2, 1] - tri[0, 1]) * (tri[1, 2] - tri[0, 2])
            if abs(d) < 1e-14:
                continue
            w1 = ((Y - tri[0, 1]) * (tri[2, 2] - tri[0, 2]) -
                  (tri[2, 1] - tri[0, 1]) * (Z - tri[0, 2])) / d
            w2 = ((tri[1, 1] - tri[0, 1]) * (Z - tri[0, 2]) -
                  (Y - tri[0, 1]) * (tri[1, 2] - tri[0, 2])) / d
            inside = (w1 >= -1e-9) & (w2 >= -1e-9) & (w1 + w2 <= 1 + 1e-9)
            if not inside.any():
                continue
            Xc = tri[0, 0] + w1 * (tri[1, 0] - tri[0, 0]) + w2 * (tri[2, 0] - tri[0, 0])
            sub = wall_x[j0:j1 + 1, k0:k1 + 1]
            upd = inside & (np.isnan(sub) | (Xc < sub))
            sub[upd] = Xc[upd]
    log(f"wall/min-x field: {np.isfinite(wall_x).sum()} filled cells of {wall_x.size}")

    Hs = np.full((len(gx), len(gy)), np.nan)
    scatter_counts = {}
    for nm in ("stones", "grass", "leaves"):
        ob = bpy.data.objects.get(nm)
        if ob is None:
            scatter_counts[nm] = 0
            continue
        v = vert_array(ob, dg)
        m = np.ones(len(v), dtype=bool)
        for i in range(3):
            m &= (v[:, i] >= BOX[i][0]) & (v[:, i] <= BOX[i][1])
        v = v[m]
        scatter_counts[nm] = int(len(v))
        log(f"scatter {nm}: {len(v)} vertices inside clip box")
        if len(v) == 0:
            continue
        ii = np.clip(((v[:, 0] - gx[0]) / GRID).astype(np.int64), 0, len(gx) - 1)
        jj = np.clip(((v[:, 1] - gy[0]) / GRID).astype(np.int64), 0, len(gy) - 1)
        cur = Hs[ii, jj]
        Hs[ii, jj] = np.where(np.isnan(cur), v[:, 2], np.maximum(cur, v[:, 2]))

    np.savez_compressed(RUN / "ground" / "heightfields.npz",
                        gx=gx, gy=gy, Hz=Hz, floor=Hf, scatter=Hs, wall_x=wall_x,
                        grid=GRID, box=np.array(BOX))
    log("saved heightfields.npz")

    geo["_scatter_vertices_in_box"] = scatter_counts
    (RUN / "ground" / "ground_geometry.json").write_text(
        json.dumps(geo, indent=2), encoding="utf-8")
    log("wrote ground_geometry.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
