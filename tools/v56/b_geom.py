"""Shared geometry helpers for the V5.6 B box-domino re-verification.

Both `b_inspect_meshes.py` and `b_domino_test.py` must agree on what "the box's own frame" and
"its dimensions" mean, otherwise the physics run would be using a differently-oriented box from the
one that was measured. The frame logic therefore lives here once and is imported, and the physics
script asserts that the dimensions it computes match the recorded `box_geometry.json`.

The frame is recovered from face NORMALS rather than from the stored coordinates, because GSO
assets are scans stored in arbitrary poses. Axes are then ordered by extent (ascending), so:

    dims[0] = thickness  (the axis the box falls along; its two faces are the strike faces)
    dims[1] = width
    dims[2] = height     (the standing axis)
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

FLAT_TOL_FRAC = 0.02
NORMAL_CLUSTER_DEG = 12.0


def read_obj(path: Path):
    """Return (verts, tris) from an OBJ, triangulating polygons and honouring negative indices."""
    verts, tris = [], []
    with path.open("r", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                if len(p) >= 4:
                    verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    s = tok.split("/")[0]
                    if s.lstrip("-").isdigit():
                        i = int(s)
                        idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    tris.append((idx[0], idx[k], idx[k + 1]))
    return verts, tris


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    L = math.sqrt(dot(a, a))
    return (a[0] / L, a[1] / L, a[2] / L) if L > 1e-14 else (0.0, 0.0, 1.0)


def det3(a, b, c):
    return (a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0]))


def tri_normal_area(verts, tris):
    out = []
    for a, b, c in tris:
        try:
            p0, p1, p2 = verts[a], verts[b], verts[c]
        except IndexError:
            continue
        ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
        vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
        cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        L = math.sqrt(cx * cx + cy * cy + cz * cz)
        if L < 1e-14:
            continue
        out.append(((cx / L, cy / L, cz / L), 0.5 * L, (p0, p1, p2)))
    return out


def box_frame(normals_areas, verts):
    """The object's own axes, from the directions carrying the most surface area.

    A box's six faces give six normal clusters on three perpendicular axes, so the three largest
    mutually-separated directions recover the box frame whatever pose the scan was stored in.
    Axes are returned ordered by extent ascending and in a right-handed frame.
    """
    cos_tol = math.cos(math.radians(NORMAL_CLUSTER_DEG))
    axes = []
    for _ in range(3):
        best_dir, best_area = None, -1.0
        for n, _a, _t in normals_areas:
            if any(abs(dot(n, ax)) > cos_tol for ax in axes):
                continue
            tot = sum(aa for nn, aa, _tt in normals_areas
                      if abs(dot(nn, n)) > cos_tol
                      and not any(abs(dot(nn, ax)) > cos_tol for ax in axes))
            if tot > best_area:
                best_area, best_dir = tot, n
        if best_dir is None:
            break
        if axes:
            d = best_dir
            for ax in axes:
                k = dot(d, ax)
                d = (d[0] - k * ax[0], d[1] - k * ax[1], d[2] - k * ax[2])
            best_dir = norm(d)
        axes.append(best_dir)
    while len(axes) < 3:
        for c in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
            if not any(abs(dot(c, ax)) > 0.9 for ax in axes):
                axes.append(norm(c))
                break
        else:
            axes.append(norm(cross(axes[0], axes[1])))

    ext = []
    for ax in axes:
        p = [dot(v, ax) for v in verts]
        ext.append(max(p) - min(p))
    order = sorted(range(3), key=lambda i: ext[i])
    axes = [axes[i] for i in order]
    if det3(*axes) < 0:                     # keep it right-handed
        axes[2] = (-axes[2][0], -axes[2][1], -axes[2][2])
    return axes


def to_own_frame(verts, axes):
    """Express every vertex in the object's own frame (axis 0 = thickness, 2 = height)."""
    return [tuple(dot(v, ax) for ax in axes) for v in verts]


def flat_coverage(vp, tris, axis, at_max, span, tol_frac=FLAT_TOL_FRAC):
    """Area of triangles lying in the extreme face, over the nominal bounding face area."""
    if span is None or span <= 1e-9:
        return None
    hi = max(v[axis] for v in vp)
    lo = min(v[axis] for v in vp)
    plane = hi if at_max else lo
    tol = tol_frac * span
    u, w = [i for i in range(3) if i != axis]
    du = max(v[u] for v in vp) - min(v[u] for v in vp)
    dw = max(v[w] for v in vp) - min(v[w] for v in vp)
    if du <= 0 or dw <= 0:
        return None
    flat = 0.0
    for a, b, c in tris:
        try:
            p0, p1, p2 = vp[a], vp[b], vp[c]
        except IndexError:
            continue
        ux, uz = p1[u] - p0[u], p1[w] - p0[w]
        vx, vz = p2[u] - p0[u], p2[w] - p0[w]
        pa = 0.5 * abs(ux * vz - uz * vx)
        if max(abs(p0[axis] - plane), abs(p1[axis] - plane), abs(p2[axis] - plane)) <= tol:
            flat += pa
    return flat / (du * dw)


def mesh_volume(verts, tris):
    """Volume enclosed by the mesh via the divergence theorem."""
    vol = 0.0
    for a, b, c in tris:
        try:
            p0, p1, p2 = verts[a], verts[b], verts[c]
        except IndexError:
            continue
        vol += (p0[0] * (p1[1] * p2[2] - p2[1] * p1[2])
                - p0[1] * (p1[0] * p2[2] - p2[0] * p1[2])
                + p0[2] * (p1[0] * p2[1] - p2[0] * p1[1])) / 6.0
    return abs(vol)


def closed_edge_fraction(tris) -> float | None:
    """Fraction of edges shared by exactly two triangles (1.0 = watertight)."""
    edges = Counter()
    for a, b, c in tris:
        for e in ((a, b), (b, c), (c, a)):
            edges[(min(e), max(e))] += 1
    if not edges:
        return None
    return sum(1 for k in edges.values() if k == 2) / len(edges)


def measure_obj(path: Path) -> dict:
    """Full geometry record of one OBJ, in its own frame ordered [thickness, width, height]."""
    v, t = read_obj(path)
    if not v or not t:
        return {"error": "empty mesh"}
    axes = box_frame(tri_normal_area(v, t), v)
    vp = to_own_frame(v, axes)
    lo = [min(p[i] for p in vp) for i in range(3)]
    hi = [max(p[i] for p in vp) for i in range(3)]
    dims = [hi[i] - lo[i] for i in range(3)]
    vol = mesh_volume(v, t)
    bbox_vol = dims[0] * dims[1] * dims[2]
    return {
        "path": str(path), "vertices": len(v), "triangles": len(t),
        "dims_in_own_frame_m": [round(x, 9) for x in dims],
        "thickness_m": round(dims[0], 9),
        "width_m": round(dims[1], 9),
        "height_m": round(dims[2], 9),
        "hull_volume_m3": round(vol, 12),
        "bbox_volume_m3": round(bbox_vol, 12),
        "boxiness_volume_over_bbox": round(vol / bbox_vol, 5) if bbox_vol > 0 else None,
        "closed_edge_fraction": (round(closed_edge_fraction(t), 5)
                                 if closed_edge_fraction(t) is not None else None),
        "own_frame_axes": [[round(x, 9) for x in ax] for ax in axes],
        "own_frame_min": [round(x, 9) for x in lo],
        "own_frame_max": [round(x, 9) for x in hi],
        "base_coverage": flat_coverage(vp, t, 2, False, dims[2]),
        "top_coverage": flat_coverage(vp, t, 2, True, dims[2]),
        "strike_coverage_minus": flat_coverage(vp, t, 0, False, dims[0]),
        "strike_coverage_plus": flat_coverage(vp, t, 0, True, dims[0]),
        "side_coverage_minus": flat_coverage(vp, t, 1, False, dims[1]),
        "side_coverage_plus": flat_coverage(vp, t, 1, True, dims[1]),
        "thinnest_extent_m": round(min(dims), 9),
        "thinnest_over_largest": round(min(dims) / max(dims), 6) if max(dims) > 0 else None,
    }


def upright_vertices(path: Path) -> tuple[list, list, dict]:
    """Vertices of `path` re-expressed so the box is axis-aligned, upright and resting on z = 0.

    Returns (vertices, triangles, info). The returned vertices have the box's own frame mapped onto
    the world axes and are shifted so that the base sits exactly at z = 0 and the footprint is
    centred on the origin, so a body spawned at (x, y, 0) rests on a floor whose top is z = 0 with
    no initial penetration.
    """
    v, t = read_obj(path)
    axes = box_frame(tri_normal_area(v, t), v)
    vp = to_own_frame(v, axes)
    lo = [min(p[i] for p in vp) for i in range(3)]
    hi = [max(p[i] for p in vp) for i in range(3)]
    cx = (lo[0] + hi[0]) / 2.0
    cy = (lo[1] + hi[1]) / 2.0
    out = [(p[0] - cx, p[1] - cy, p[2] - lo[2]) for p in vp]
    info = {
        "dims_m": [hi[i] - lo[i] for i in range(3)],
        "thickness_m": hi[0] - lo[0], "width_m": hi[1] - lo[1], "height_m": hi[2] - lo[2],
        "hull_volume_m3": mesh_volume(v, t),
        "vertices": len(v), "triangles": len(t),
    }
    return out, t, info


def write_obj(path: Path, verts, tris) -> None:
    """Write a triangulated OBJ, so pybullet's mesh loader can build the convex hull from a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for p in verts:
        lines.append(f"v {p[0]:.12f} {p[1]:.12f} {p[2]:.12f}")
    for a, b, c in tris:
        lines.append(f"f {a + 1} {b + 1} {c + 1}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
