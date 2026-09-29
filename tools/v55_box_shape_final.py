"""Orientation-invariant box check, and the measurement of record for stage 08's domino boxes.

Three earlier attempts all failed for the same underlying reason and the failure modes are worth
recording, because each one looked plausible until a number contradicted it:

  1. share of TOTAL SURFACE AREA in the base plane -- a cube's largest face is 1/6 of its surface, so
     the 0.75 threshold was unreachable. Reported 0/10 usable, including an asset named "Cube".
  2. share of TOTAL PROJECTED AREA in the base plane -- a closed box projects bottom and top onto the
     same footprint, so the ceiling is 0.50; the best boxes measured 0.48-0.50, right on it.
     Reported 0/40.
  3. flat area over the bounding-box face -- correct in principle, but it ASSUMED the mesh's stored
     axes are the box's axes. GSO assets are scans stored in arbitrary poses, so for a box that is
     slightly rotated no face is axis-aligned: the "within 2% of the extreme" test then catches only
     slivers, and boxes reported a strike-face coverage of 0.001 while a figurine reported 0.42.

This version removes the orientation assumption. It finds the object's own frame from its FACE
NORMALS:

  * triangles are clustered by normal direction, greedily taking the direction that carries the most
    area, then the most area at least 60 degrees away from it, then the cross product;
  * the mesh is rotated into that frame, so the box's own axes become the measurement axes;
  * standing height, thickness, width and the three face coverages are then measured in that frame;
  * the best standing orientation is chosen explicitly -- the one that maximises height over
    thickness while keeping the base coverage high -- rather than assuming the stored Z is up.

It also reports, from the asset's own URDF, the recorded mass and inertia against 08 section 3's
solid-box formula. Both are needed: the library's URDF masses are scan artefacts (a game box recorded
as 0.0028 kg) and many assets are hollow shells whose inertia is far below a solid block, so wherever
08 uses the box formulas, the difference has to be disclosed rather than absorbed.

Read-only; writes `outcomes/v55/stage08/box_shape_final.json` on the server.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
GSO = ROOT / "models/gso"
OUT = ROOT / "outcomes/v55/stage08"
OUT.mkdir(parents=True, exist_ok=True)

CAND = json.loads((OUT / "box_candidates.json").read_text(encoding="utf-8"))
NAMES = [a["asset_id"] for a in CAND["assets"] if a["suitable_for_domino"]][:40]
for extra in ("Razer_BlackWidow_Ultimate_2014_Mechanical_Gaming_Keyboard",
              "Room_Essentials_Fabric_Cube_Lavender"):
    if extra not in NAMES:
        NAMES.append(extra)

BOXINESS_MIN = 0.55
BASE_COVERAGE_MIN = 0.85
STRIKE_COVERAGE_MIN = 0.85
TIPPING_DEG = (4.0, 25.0)
NORMAL_CLUSTER_DEG = 12.0
FLAT_TOL_FRAC = 0.02


def read_obj(path: Path):
    verts, tris = [], []
    with path.open("r", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
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


def tri_normal_area(verts, tris):
    out = []
    for a, b, c in tris:
        try:
            p0, p1, p2 = verts[a], verts[b], verts[c]
        except IndexError:
            continue
        ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
        vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
        cx = uy * vz - uz * vy
        cy = uz * vx - ux * vz
        cz = ux * vy - uy * vx
        L = math.sqrt(cx * cx + cy * cy + cz * cz)
        if L < 1e-14:
            continue
        out.append(((cx / L, cy / L, cz / L), 0.5 * L, (p0, p1, p2)))
    return out


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    L = math.sqrt(dot(a, a))
    return (a[0] / L, a[1] / L, a[2] / L) if L > 1e-14 else (0.0, 0.0, 1.0)


def box_frame(normals_areas):
    """The object's own axes, from the directions carrying the most surface area.

    A box's six faces give six normal clusters on three perpendicular axes, so the three largest
    mutually-separated directions recover the box frame whatever pose the scan was stored in.
    """
    cos_tol = math.cos(math.radians(NORMAL_CLUSTER_DEG))
    axes = []
    for _ in range(3):
        best_dir, best_area = None, -1.0
        for n, a, _ in normals_areas:
            if any(abs(dot(n, ax)) > cos_tol for ax in axes):
                continue
            # area of every normal close to this candidate, which is what makes it a face cluster
            tot = sum(aa for nn, aa, _ in normals_areas
                      if abs(dot(nn, n)) > cos_tol
                      and not any(abs(dot(nn, ax)) > cos_tol for ax in axes))
            if tot > best_area:
                best_area, best_dir = tot, n
        if best_dir is None:
            break
        if axes:
            # re-orthogonalise so the frame is exactly orthogonal
            d = best_dir
            for ax in axes:
                k = dot(d, ax)
                d = (d[0] - k * ax[0], d[1] - k * ax[1], d[2] - k * ax[2])
            best_dir = norm(d)
        axes.append(best_dir)
    while len(axes) < 3:
        cand = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
        for c in cand:
            if not any(abs(dot(c, ax)) > 0.9 for ax in axes):
                axes.append(norm(c))
                break
        else:
            axes.append(norm(cross(axes[0], axes[1])))
    return axes


def rotate(v, axes):
    """Coordinates of v in the frame given by `axes` (rows)."""
    return tuple(dot(v, ax) for ax in axes)


def footprint_coverage(verts, tris, axis, at_max):
    """Flat area in the extreme face over the nominal footprint, in the box's own frame."""
    lo = min(v[axis] for v in verts)
    hi = max(v[axis] for v in verts)
    span = hi - lo
    if span <= 1e-9:
        return None
    plane = hi if at_max else lo
    tol = FLAT_TOL_FRAC * span
    u, w = [i for i in range(3) if i != axis]
    du = max(v[u] for v in verts) - min(v[u] for v in verts)
    dw = max(v[w] for v in verts) - min(v[w] for v in verts)
    if du <= 0 or dw <= 0:
        return None
    bbox_face = du * dw
    flat = 0.0
    for a, b, c in tris:
        try:
            p0, p1, p2 = verts[a], verts[b], verts[c]
        except IndexError:
            continue
        ux, uz = p1[u] - p0[u], p1[w] - p0[w]
        vx, vz = p2[u] - p0[u], p2[w] - p0[w]
        pa = 0.5 * abs(ux * vz - uz * vx)
        if max(abs(p0[axis] - plane), abs(p1[axis] - plane), abs(p2[axis] - plane)) <= tol:
            flat += pa
    return flat / bbox_face


def mesh_volume_com(verts, tris):
    vol = cx = cy = cz = 0.0
    for a, b, c in tris:
        try:
            p0, p1, p2 = verts[a], verts[b], verts[c]
        except IndexError:
            continue
        v = (p0[0] * (p1[1] * p2[2] - p2[1] * p1[2])
             - p0[1] * (p1[0] * p2[2] - p2[0] * p1[2])
             + p0[2] * (p1[0] * p2[1] - p2[0] * p1[1])) / 6.0
        vol += v
        cx += v * (p0[0] + p1[0] + p2[0]) / 4.0
        cy += v * (p0[1] + p1[1] + p2[1]) / 4.0
        cz += v * (p0[2] + p1[2] + p2[2]) / 4.0
    if abs(vol) < 1e-15:
        return 0.0, (0.0, 0.0, 0.0)
    s = 1.0 if vol > 0 else -1.0
    return abs(vol), (s * cx / vol, s * cy / vol, s * cz / vol)


URDF_MI = re.compile(r"<mass\s+value=\"([0-9.eE+-]+)\"\s*/>.*?<inertia\s+ixx=\"([0-9.eE+-]+)\"", re.S)


def urdf_mi(p: Path):
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None, None
    m = URDF_MI.search(t)
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(2))
    except ValueError:
        return None, None


rows = []
for name in NAMES:
    d = GSO / name
    coll, vis = d / "collision_geometry.obj", d / "visual_geometry.obj"
    src = coll if coll.is_file() else vis
    if not src.is_file():
        continue
    verts, tris = read_obj(src)
    if not verts or not tris:
        continue

    na = tri_normal_area(verts, tris)
    axes = box_frame(na)
    rv = [rotate(v, axes) for v in verts]

    dims = [max(v[i] for v in rv) - min(v[i] for v in rv) for i in range(3)]

    vol, com_local = mesh_volume_com(verts, tris)
    # rotate the centre of mass into the box frame as well (it is a point, so rotate its offset)
    c0 = tuple((max(v[i] for v in verts) + min(v[i] for v in verts)) / 2 for i in range(3))
    com = rotate((com_local[0] - c0[0], com_local[1] - c0[1], com_local[2] - c0[2]), axes)

    # Try all three standing orientations: stand on face k (k = height axis), etc. A domino stands on
    # its smallest face, so the height axis is the largest extent and the thickness is the smallest.
    order = sorted(range(3), key=lambda a: dims[a])
    results = {}
    for stand_ax in range(3):
        h = dims[stand_ax]
        others = [a for a in range(3) if a != stand_ax]
        t_ax = min(others, key=lambda a: dims[a])
        w_ax = max(others, key=lambda a: dims[a])
        t, w = dims[t_ax], dims[w_ax]
        base_cov = footprint_coverage(rv, tris, stand_ax, False)
        top_cov = footprint_coverage(rv, tris, stand_ax, True)
        # the striking face is the one facing along the thickness axis
        strike_hi = footprint_coverage(rv, tris, t_ax, True)
        strike_lo = footprint_coverage(rv, tris, t_ax, False)
        com_h = com[stand_ax] - min(v[stand_ax] for v in rv)
        com_off = com[t_ax] - (min(v[t_ax] for v in rv) + t / 2.0)
        tip = (math.degrees(math.atan2(max(0.0, t / 2.0 - abs(com_off)), com_h))
               if com_h > 1e-9 else 0.0)
        results[stand_ax] = {
            "height_axis": stand_ax, "standing_h_m": h, "thickness_m": t, "width_m": w,
            "h_over_t": (h / t) if t > 0 else None, "w_over_t": (w / t) if t > 0 else None,
            "base_coverage": base_cov, "top_coverage": top_cov,
            "strike_coverage_best": max([c for c in (strike_hi, strike_lo) if c is not None],
                                        default=None),
            "tipping_angle_deg": tip,
        }
    # Choose the standing orientation a domino would use: the tallest one that still stands flat.
    viable = [v for v in results.values()
              if (v["base_coverage"] or 0) >= BASE_COVERAGE_MIN]
    best = max(viable, key=lambda v: v["h_over_t"] or 0) if viable else \
        max(results.values(), key=lambda v: v["base_coverage"] or 0)

    closed = Counter()
    for a, b, c in tris:
        for e in ((a, b), (b, c), (c, a)):
            closed[(min(e), max(e))] += 1
    two = sum(1 for v in closed.values() if v == 2)
    closedness = two / len(closed) if closed else 0.0

    mass_u, ixx_u = urdf_mi(d / "object.urdf")
    ixx_box = (mass_u or 0.0) * (best["standing_h_m"] ** 2 + best["width_m"] ** 2) / 12.0

    row = {
        "asset_id": name, "source": src.name, "has_collision_proxy": coll.is_file(),
        "standing_h_m": round(best["standing_h_m"], 6),
        "thickness_m": round(best["thickness_m"], 6),
        "width_m": round(best["width_m"], 6),
        "h_over_t": round(best["h_over_t"], 3) if best["h_over_t"] else None,
        "w_over_t": round(best["w_over_t"], 3) if best["w_over_t"] else None,
        "standing_axis": best["height_axis"],
        "base_coverage": round(best["base_coverage"], 4) if best["base_coverage"] is not None else None,
        "top_coverage": round(best["top_coverage"], 4) if best["top_coverage"] is not None else None,
        "strike_coverage": (round(best["strike_coverage_best"], 4)
                            if best["strike_coverage_best"] is not None else None),
        "tipping_angle_deg": round(best["tipping_angle_deg"], 3),
        "boxiness": round(vol / (dims[0] * dims[1] * dims[2]), 4) if all(d > 0 for d in dims) else None,
        "closedness": round(closedness, 4),
        "dims_in_own_frame_m": [round(x, 6) for x in dims],
        "all_orientations": {str(k): {kk: (round(vv, 5) if isinstance(vv, float) else vv)
                                      for kk, vv in v.items()} for k, v in results.items()},
        "urdf_mass_kg": mass_u, "urdf_ixx": ixx_u,
        "box_formula_ixx": round(ixx_box, 15),
        "ixx_ratio_urdf_over_box": (round(ixx_u / ixx_box, 4) if (ixx_u and ixx_box) else None),
        "triangles": len(tris), "vertices": len(verts),
    }
    row["boxiness_ok"] = bool(row["boxiness"] and row["boxiness"] >= BOXINESS_MIN)
    row["base_ok"] = bool(row["base_coverage"] is not None
                          and row["base_coverage"] >= BASE_COVERAGE_MIN)
    row["strike_ok"] = bool(row["strike_coverage"] is not None
                            and row["strike_coverage"] >= STRIKE_COVERAGE_MIN)
    row["tipping_ok"] = bool(TIPPING_DEG[0] <= row["tipping_angle_deg"] <= TIPPING_DEG[1])
    row["ratio_ok"] = bool(row["h_over_t"] and 3.0 <= row["h_over_t"] <= 8.0
                           and row["w_over_t"] and row["w_over_t"] >= 1.5)
    row["usable_as_domino"] = bool(row["boxiness_ok"] and row["base_ok"] and row["strike_ok"]
                                   and row["tipping_ok"] and row["ratio_ok"])
    rows.append(row)

rows.sort(key=lambda r: (not r["usable_as_domino"], r["thickness_m"]))
print("=" * 124)
print(f"{'asset_id':42s} {'boxy':>5s} {'base':>5s} {'top':>5s} {'strk':>5s} {'tip':>6s} "
      f"{'h/t':>5s} {'w/t':>5s} {'h_mm':>7s} {'t_mm':>6s} {'use':>4s}")
for r in rows:
    print(f"{r['asset_id'][:42]:42s} {r['boxiness']:5.3f} {(r['base_coverage'] or 0):5.3f} "
          f"{(r['top_coverage'] or 0):5.3f} {(r['strike_coverage'] or 0):5.3f} "
          f"{r['tipping_angle_deg']:6.2f} {(r['h_over_t'] or 0):5.2f} {(r['w_over_t'] or 0):5.2f} "
          f"{r['standing_h_m']*1000:7.1f} {r['thickness_m']*1000:6.1f} "
          f"{'YES' if r['usable_as_domino'] else '-':>4s}")

usable = [r for r in rows if r["usable_as_domino"]]
print(f"\n{len(usable)} of {len(rows)} assets usable as dominoes")
print(f"thresholds: boxiness>={BOXINESS_MIN}, base>={BASE_COVERAGE_MIN}, "
      f"strike>={STRIKE_COVERAGE_MIN}, tipping {TIPPING_DEG[0]}-{TIPPING_DEG[1]} deg, "
      f"h/t 3-8, w/t>=1.5")

if usable:
    best = usable[0]
    h, t, w = best["standing_h_m"], best["thickness_m"], best["width_m"]
    print(f"\nbest (thinnest usable): {best['asset_id']}")
    print(f"  {h*1000:.1f} x {t*1000:.1f} x {w*1000:.1f} mm (h x t x w), h/t {best['h_over_t']:.2f}, "
          f"w/t {best['w_over_t']:.2f}")
    print(f"  boxiness {best['boxiness']:.3f}, base coverage {best['base_coverage']:.3f}, "
          f"strike coverage {best['strike_coverage']:.3f}, tipping {best['tipping_angle_deg']:.2f} deg")
    print(f"  urdf mass {best['urdf_mass_kg']} kg, ixx ratio vs solid-box formula "
          f"{best['ixx_ratio_urdf_over_box']}")
    print(f"\n  12-box chain, 08 section 2: total = 12*t + 11*gap")
    for g in (0.15, 0.20, 0.25, 0.30):
        L = 12 * t + 11 * g * h
        print(f"    gap {g:.2f}*h = {g*h*1000:6.1f} mm -> chain {L*1000:7.1f} mm; "
              f"about {L+1.0:.2f} m clear run with run-in and run-out")

(OUT / "box_shape_final.json").write_text(json.dumps({
    "note": ("orientation-invariant box check. The object's own axes are recovered from its face "
             "normals, so the measurement does not assume the scan's stored Z is up. Three earlier "
             "versions failed on denominators no closed solid can satisfy (surface share ceiling "
             "1/6, projected share ceiling 1/2) or on the orientation assumption."),
    "thresholds": {"boxiness_min": BOXINESS_MIN, "base_coverage_min": BASE_COVERAGE_MIN,
                   "strike_coverage_min": STRIKE_COVERAGE_MIN,
                   "tipping_angle_deg": list(TIPPING_DEG), "h_over_t": [3.0, 8.0],
                   "w_over_t_min": 1.5},
    "normal_cluster_deg": NORMAL_CLUSTER_DEG, "flat_tol_frac": FLAT_TOL_FRAC,
    "measured": len(rows), "usable_count": len(usable),
    "usable": [r["asset_id"] for r in usable],
    "caveats": {
        "urdf_mass": ("URDF masses in this library are scan artefacts (a game box is recorded as "
                      "0.0028 kg); 08 must assign mass from a stated density and disclose it"),
        "inertia": ("solid-box inertia formula is an over-estimate for hollow assets; ratios "
                    "measured here must be disclosed wherever 08 section 3 uses the formula"),
        "closedness": ("measured on the collision proxy, which is a convex hull and therefore "
                       "always closed; it is uninformative as a discriminator"),
    },
    "assets": rows,
}, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'box_shape_final.json'}")
