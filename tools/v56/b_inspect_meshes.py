"""V5.6 B: measure the real geometry of the three domino candidates before any physics.

The earlier stage-08 conclusion ("only Hasbro_Cranium is usable as a domino") came from a pure
SHAPE metric: strike-face flatness coverage >= 0.85. That metric can be a screening hint but it
cannot decide whether a closed box can knock over another box -- a box with a rounded or slightly
slanted strike face still reaches and strikes its neighbour. This script therefore only collects
the FACTS the physical test needs, and deliberately draws no usability verdict:

  * the real dimensions of `collision_geometry.obj`, in the object's OWN frame recovered from its
    face normals (GSO assets are scans stored in arbitrary poses, so the stored axes are not the
    box's axes);
  * the same axes measured on `visual_geometry.obj`, so the collision proxy can be compared to the
    visual per axis -- a proxy noticeably larger than the visual makes boxes collide early and
    overlap on screen;
  * convex-hull volume vs bounding box (boxiness) and a thin-extent flag, to catch a proxy that is
    a flat blob or has a near-zero thickness somewhere;
  * flat coverage of the base and of each strike face, i.e. the earlier screening numbers, recorded
    beside the physics rather than instead of it;
  * `data.json` and `object.urdf`. The URDF mass is NOT used as the physical mass: the library's
    URDF masses are scan artefacts (this game box is recorded as 0.0028 kg). Mass is assigned later
    from a stated density over the measured hull volume.

Axes are reordered ascending, so dims are always [thickness, width, height] and axis 2 is the
standing (vertical) axis. That makes every coverage number below unambiguous.

Read-only. Writes `outcomes/v56/mixed_box_domino/box_geometry.json` on the server.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
GSO = ROOT / "models/gso"
OUT = ROOT / "outcomes/v56/mixed_box_domino"
OUT.mkdir(parents=True, exist_ok=True)

ASSETS = [
    "Hasbro_Cranium_Performance_and_Acting_Game",
    "Hasbro_Trivial_Pursuit_Family_Edition_Game",
    "Supernatural_Ouija_Board_Game",
]

#: A face is "flat" if all three of its vertices lie within this fraction of the axis extent.
FLAT_TOL_FRAC = 0.02
NORMAL_CLUSTER_DEG = 12.0


# ---------------------------------------------------------------------------------------------
# geometry primitives (no third-party dependency, so the numbers are reproducible anywhere)
# ---------------------------------------------------------------------------------------------

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


def box_frame(normals_areas):
    """The object's own axes, from the directions carrying the most surface area.

    A box's six faces give six normal clusters on three perpendicular axes, so the three largest
    mutually-separated directions recover the box frame whatever pose the scan was stored in.
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

    # Order the axes by extent (ascending) so axis 0 is thickness and axis 2 is height, then
    # restore a right-handed frame (a left-handed one would mirror the collision shape).
    ext = []
    for ax in axes:
        p = [dot(v, ax) for v in _FRAME_VERTS]
        ext.append(max(p) - min(p))
    order = sorted(range(3), key=lambda i: ext[i])
    axes = [axes[i] for i in order]
    if det3(*axes) < 0:
        axes[2] = (-axes[2][0], -axes[2][1], -axes[2][2])
    return axes


#: Set by `measure()` before calling `box_frame`, so the frame can be ordered by real extent.
_FRAME_VERTS: list = []


def flat_coverage(vp, tris, axis, at_max, span):
    """Area of triangles lying in the extreme face, over the nominal bounding face area."""
    if span is None or span <= 1e-9:
        return None
    hi = max(v[axis] for v in vp)
    lo = min(v[axis] for v in vp)
    plane = hi if at_max else lo
    tol = FLAT_TOL_FRAC * span
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
        if max(abs(p0[axis] - plane), abs(p1[axis] - plane),
               abs(p2[axis] - plane)) <= tol:
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


URDF_MASS = re.compile(r"<mass\s+value=\"([0-9.eE+-]+)\"")
URDF_INERTIA = re.compile(r"<inertia\s+([^/>]+)/>")


def urdf_info(path: Path):
    out = {"exists": path.is_file()}
    if not out["exists"]:
        return out
    text = path.read_text(encoding="utf-8", errors="replace")
    m = URDF_MASS.search(text)
    out["mass_kg"] = float(m.group(1)) if m else None
    mi = URDF_INERTIA.search(text)
    if mi:
        attrs = dict(re.findall(r"(\w+)=\"([0-9.eE+-]+)\"", mi.group(1)))
        out["inertia"] = {k: float(v) for k, v in attrs.items()}
    out["mesh_refs"] = re.findall(r'filename="([^"]+)"', text)
    out["mentions_collision_geometry"] = "collision_geometry" in text
    out["mentions_visual_geometry"] = "visual_geometry" in text
    return out


def measure(path: Path) -> dict:
    """Geometry of one OBJ, in its own frame ordered [thickness, width, height]."""
    global _FRAME_VERTS
    v, t = read_obj(path)
    if not v or not t:
        return {"error": "empty mesh"}
    _FRAME_VERTS = v
    axes = box_frame(tri_normal_area(v, t))
    vp = [tuple(dot(vv, ax) for ax in axes) for vv in v]
    lo = [min(p[i] for p in vp) for i in range(3)]
    hi = [max(p[i] for p in vp) for i in range(3)]
    dims = [hi[i] - lo[i] for i in range(3)]
    vol = mesh_volume(v, t)

    edges = Counter()
    for a, b, c in t:
        for e in ((a, b), (b, c), (c, a)):
            edges[(min(e), max(e))] += 1
    two = sum(1 for k in edges.values() if k == 2)

    return {
        "path": str(path), "vertices": len(v), "triangles": len(t),
        "dims_in_own_frame_m": [round(x, 9) for x in dims],
        "thickness_m": round(dims[0], 9),
        "width_m": round(dims[1], 9),
        "height_m": round(dims[2], 9),
        "hull_volume_m3": round(vol, 12),
        "bbox_volume_m3": round(dims[0] * dims[1] * dims[2], 12),
        "boxiness_volume_over_bbox": (round(vol / (dims[0] * dims[1] * dims[2]), 5)
                                      if all(x > 0 for x in dims) else None),
        "closed_edge_fraction": round(two / len(edges), 5) if edges else None,
        "own_frame_axes": [[round(x, 9) for x in ax] for ax in axes],
        "own_frame_min": [round(x, 9) for x in lo],
        "own_frame_max": [round(x, 9) for x in hi],
        # coverage in the sorted frame: axis0 = thickness (the strike faces), axis2 = height
        "base_coverage": flat_coverage(vp, t, 2, False, dims[2]),
        "top_coverage": flat_coverage(vp, t, 2, True, dims[2]),
        "strike_coverage_minus": flat_coverage(vp, t, 0, False, dims[0]),
        "strike_coverage_plus": flat_coverage(vp, t, 0, True, dims[0]),
        "side_coverage_minus": flat_coverage(vp, t, 1, False, dims[1]),
        "side_coverage_plus": flat_coverage(vp, t, 1, True, dims[1]),
        "thinnest_extent_m": round(min(dims), 9),
        "thinnest_over_largest": (round(min(dims) / max(dims), 6) if max(dims) > 0 else None),
    }


report = {"note": ("measured geometry of the three named domino candidates, in each mesh's own "
                   "frame (axes recovered from face normals, ordered thickness/width/height). "
                   "No usability verdict is drawn here; the physical test decides that."),
          "assets_dir": str(GSO), "flat_tol_frac": FLAT_TOL_FRAC,
          "normal_cluster_deg": NORMAL_CLUSTER_DEG, "assets": {}}

for aid in ASSETS:
    d = GSO / aid
    rec: dict = {"asset_id": aid, "dir": str(d), "dir_exists": d.is_dir()}
    if not d.is_dir():
        report["assets"][aid] = rec
        continue

    rec["files"] = {f.name: f.stat().st_size for f in sorted(d.iterdir()) if f.is_file()}
    dj = d / "data.json"
    if dj.is_file():
        try:
            rec["data_json"] = json.loads(dj.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            rec["data_json_error"] = f"{type(exc).__name__}: {exc}"
    rec["urdf"] = urdf_info(d / "object.urdf")

    coll_p, vis_p = d / "collision_geometry.obj", d / "visual_geometry.obj"
    for label, p in (("collision", coll_p), ("visual", vis_p)):
        if not p.is_file():
            rec[f"{label}_missing"] = True
            continue
        rec[label] = measure(p)

    if "collision" in rec and "visual" in rec and vis_p.is_file():
        vv, _vt = read_obj(vis_p)
        caxes = [tuple(x) for x in rec["collision"]["own_frame_axes"]]
        rows = []
        roles = ["thickness_axis", "width_axis", "height_axis"]
        for i, ax in enumerate(caxes):
            p = [dot(x, ax) for x in vv]
            vd = max(p) - min(p)
            cd = rec["collision"]["dims_in_own_frame_m"][i]
            rel = (cd - vd) / vd if vd > 0 else None
            rows.append({
                "axis_index": i, "axis_role": roles[i],
                "collision_extent_m": round(cd, 6), "visual_extent_m": round(vd, 6),
                "collision_minus_visual_m": round(cd - vd, 6),
                "relative_difference": round(rel, 5) if rel is not None else None,
                "collision_bigger": bool(cd > vd + 1e-9),
            })
        rec["collision_vs_visual_in_collision_frame"] = rows
        rec["collision_bigger_on_any_axis"] = any(r["collision_bigger"] for r in rows)
        rec["max_relative_growth"] = max(
            (r["relative_difference"] for r in rows if r["relative_difference"] is not None),
            default=None)

    report["assets"][aid] = rec

(OUT / "box_geometry.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

print("=" * 118)
print("B step 1: real geometry of the three candidates (own frame, dims = [thickness, width, height])")
for aid, rec in report["assets"].items():
    print(f"\n--- {aid} ---")
    if not rec.get("dir_exists"):
        print("   DIR MISSING")
        continue
    print(f"   files: {list(rec.get('files', {}).keys())}")
    for label in ("collision", "visual"):
        g = rec.get(label)
        if not g:
            print(f"   {label:10s} MISSING")
            continue
        print(f"   {label:10s} verts={g['vertices']:5d} tris={g['triangles']:5d}")
        print(f"              t x w x h = {g['thickness_m']:.6f} x {g['width_m']:.6f} x "
              f"{g['height_m']:.6f} m")
        print(f"              boxiness={g['boxiness_volume_over_bbox']} "
              f"closed={g['closed_edge_fraction']} hull_vol={g['hull_volume_m3']:.10f} m^3")
        print(f"              base_cov={g['base_coverage']} top_cov={g['top_coverage']} "
              f"strike_minus={g['strike_coverage_minus']} strike_plus={g['strike_coverage_plus']}")
        print(f"              thinnest_extent={g['thinnest_extent_m']:.9f} m  "
              f"thinnest/largest={g['thinnest_over_largest']}")
    if "collision_vs_visual_in_collision_frame" in rec:
        print("   collision vs visual per axis (measured in the collision's own frame):")
        for r in rec["collision_vs_visual_in_collision_frame"]:
            print(f"      {r['axis_role']:14s} coll={r['collision_extent_m']:.6f} "
                  f"vis={r['visual_extent_m']:.6f} diff={r['collision_minus_visual_m']:+.6f} m "
                  f"rel={r['relative_difference']:+.5f}")
        print(f"   collision bigger on any axis: {rec['collision_bigger_on_any_axis']} "
              f"(max relative growth {rec['max_relative_growth']})")
    u = rec.get("urdf", {})
    print(f"   urdf mass (SCAN ARTEFACT, not used): {u.get('mass_kg')} inertia {u.get('inertia')}")
    print(f"   urdf mesh refs: {u.get('mesh_refs')}")
    dj = rec.get("data_json")
    if dj:
        print(f"   data.json keys: {list(dj)[:14]}")

print(f"\nwritten: {OUT / 'box_geometry.json'}")
