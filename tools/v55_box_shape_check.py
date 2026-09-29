"""Corrected shape check: is a candidate box usable as a domino?

Two earlier versions of this measurement were wrong, in instructive ways, and the numbers they
produced are what exposed the errors:

  1. First version asked what share of the TOTAL SURFACE AREA lies in the base plane and required
     0.75. No closed convex solid can reach that: a cube's largest face is one sixth of its surface.
     It reported 0 of 10 assets usable, including one named "Cube".

  2. Second version asked what share of the TOTAL PROJECTED AREA lies in the base plane and required
     0.90. A closed box projects BOTH its bottom and its top face onto the same footprint, plus its
     sides, so the theoretical ceiling is 0.50 -- and the best boxes measured 0.48-0.50, exactly on
     that ceiling. It reported 0 of 40.

The quantity that actually decides whether a body stands still and then topples predictably is
whether its base spans its own plan footprint. So this version measures:

    base coverage = (projected area of triangles lying in the base plane)
                    / (area of the bounding-box face on that plane)

A box scores about 1.0. A beveled box scores a little less. A rounded or irregular object scores far
less. The denominator is the nominal footprint, so no assumption about mesh closedness is needed, and
the same measure is applied to the top and to the striking face.

It also reports two things 08 depends on and that must not be assumed:

  * **mesh closedness**, as the share of edges shared by exactly two triangles. A convex-hull physics
    proxy assumes a closed mesh; an open mesh gives a proxy with no interior and therefore nonsense
    inertia.
  * **the asset's own URDF mass and inertia**, against 08 section 3's box formula
    Ixx = m*(h^2 + d^2)/12. The URDF masses in this library are scan artefacts (a Cranium box is
    recorded as 0.0028 kg) and the inertia ratios cluster at 0.1-0.65, which is physically consistent
    with a hollow shell rather than a solid block. Both facts change what 08 must do, so they are
    measured and disclosed here rather than absorbed silently.

Read-only; writes `outcomes/v55/stage08/box_shape_check.json` on the server.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
GSO = ROOT / "models/gso"
OUT = ROOT / "outcomes/v55/stage08"
OUT.mkdir(parents=True, exist_ok=True)

SHORTLIST = json.loads((OUT / "box_candidates.json").read_text(encoding="utf-8"))
CANDIDATES = [a["asset_id"] for a in SHORTLIST["assets"] if a["suitable_for_domino"]][:40]
for extra in ("Razer_BlackWidow_Ultimate_2014_Mechanical_Gaming_Keyboard",
              "Room_Essentials_Fabric_Cube_Lavender"):
    if extra not in CANDIDATES:
        CANDIDATES.append(extra)

# 08 section 2 requires a closed, flat-bottomed box. Thresholds, with the reason each is set where
# it is. They are chosen from what a real box physically scores, and the measured distribution is
# printed alongside so the separation between boxes and non-boxes is visible rather than asserted.
BOXINESS_MIN = 0.55        # volume / bounding-box volume; a real package fills most of its box
BASE_COVERAGE_MIN = 0.85   # base spans at least 85% of its bounding footprint; bevels take the rest
STRIKE_COVERAGE_MIN = 0.85
CLOSEDNESS_MIN = 0.95      # share of edges shared by exactly two triangles
TIPPING_DEG = (4.0, 25.0)  # topples when struck by a neighbour, stands when left alone


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


def closedness(tris) -> tuple[float, int, int]:
    """Share of edges shared by exactly two triangles; also the open-boundary edge count."""
    from collections import Counter
    c = Counter()
    for a, b, cc in tris:
        for e in ((a, b), (b, cc), (cc, a)):
            c[(min(e), max(e))] += 1
    if not c:
        return 0.0, 0, 0
    two = sum(1 for v in c.values() if v == 2)
    bad = sum(1 for v in c.values() if v != 2)
    return two / len(c), bad, len(c)


def mesh_volume_and_com(verts, tris):
    vol = 0.0
    cx = cy = cz = 0.0
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
    sgn = 1.0 if vol > 0 else -1.0
    return abs(vol), (sgn * cx / vol, sgn * cy / vol, sgn * cz / vol)


def proj_area(p0, p1, p2, u, w) -> float:
    ux, uz = p1[u] - p0[u], p1[w] - p0[w]
    vx, vz = p2[u] - p0[u], p2[w] - p0[w]
    return 0.5 * abs(ux * vz - uz * vx)


def face_coverage(verts, tris, axis: int, at_max: bool, tol_frac: float = 0.02):
    """Flat projected area in the extreme face, divided by the bounding-box face area.

    Denominator = the product of the two bounding-box extents perpendicular to `axis`, i.e. the
    nominal footprint. This needs no assumption about mesh closedness, which is why it replaced the
    two earlier attempts.
    """
    lo = min(v[axis] for v in verts)
    hi = max(v[axis] for v in verts)
    span = hi - lo
    if span <= 0 or lo == hi:
        return None, None
    plane = hi if at_max else lo
    tol = tol_frac * span
    u, w = [i for i in range(3) if i != axis]
    bbox_face = (max(v[u] for v in verts) - min(v[u] for v in verts)) * \
                (max(v[w] for v in verts) - min(v[w] for v in verts))
    if bbox_face <= 0:
        return None, None
    flat = total = 0.0
    for a, b, c in tris:
        try:
            p0, p1, p2 = verts[a], verts[b], verts[c]
        except IndexError:
            continue
        pa = proj_area(p0, p1, p2, u, w)
        total += pa
        if max(abs(p0[axis] - plane), abs(p1[axis] - plane), abs(p2[axis] - plane)) <= tol:
            flat += pa
    return (flat / bbox_face if bbox_face else None), (flat / total if total else None)


URDF_MI = re.compile(r"<mass\s+value=\"([0-9.eE+-]+)\"\s*/>.*?<inertia\s+ixx=\"([0-9.eE+-]+)\"", re.S)


def urdf_mass_inertia(path: Path):
    try:
        t = path.read_text(encoding="utf-8", errors="replace")
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
for name in CANDIDATES:
    d = GSO / name
    coll, vis = d / "collision_geometry.obj", d / "visual_geometry.obj"
    src = coll if coll.is_file() else vis
    if not src.is_file():
        continue
    verts, tris = read_obj(src)
    if not verts or not tris:
        continue

    dx = max(v[0] for v in verts) - min(v[0] for v in verts)
    dy = max(v[1] for v in verts) - min(v[1] for v in verts)
    dz = max(v[2] for v in verts) - min(v[2] for v in verts)
    dims = (dx, dy, dz)
    thick_ax, width_ax, height_ax = sorted(range(3), key=lambda a: dims[a])
    t, w, h = dims[thick_ax], dims[width_ax], dims[height_ax]

    vol, com = mesh_volume_and_com(verts, tris)
    closed, bad_edges, all_edges = closedness(tris)

    base_cov, base_raw = face_coverage(verts, tris, height_ax, False)
    top_cov, _ = face_coverage(verts, tris, height_ax, True)
    strike_cov, strike_raw = face_coverage(verts, tris, thick_ax, True)
    far_cov, _ = face_coverage(verts, tris, thick_ax, False)

    mass_urdf, ixx_urdf = urdf_mass_inertia(d / "object.urdf")
    zmin = min(v[height_ax] for v in verts)
    com_h = com[height_ax] - zmin
    # Smallest bottom edge is the pivot a domino rotates about.
    com_off = com[thick_ax] - (min(v[thick_ax] for v in verts) + t / 2.0)
    tip = math.degrees(math.atan2(max(0.0, t / 2.0 - abs(com_off)), com_h)) if com_h > 0 else 0.0
    ixx_box = (mass_urdf or 0.0) * (h * h + w * w) / 12.0

    row = {
        "asset_id": name, "source": src.name, "has_collision_proxy": coll.is_file(),
        "standing_h_m": round(h, 6), "thickness_m": round(t, 6), "width_m": round(w, 6),
        "h_over_t": round(h / t, 3) if t else None,
        "w_over_t": round(w / t, 3) if t else None,
        "boxiness": round(vol / (dx * dy * dz), 4) if dx * dy * dz > 0 else None,
        "closedness": round(closed, 4), "open_boundary_edges": bad_edges, "edges": all_edges,
        "base_coverage": round(base_cov, 4) if base_cov is not None else None,
        "base_share_of_projected": round(base_raw, 4) if base_raw is not None else None,
        "top_coverage": round(top_cov, 4) if top_cov is not None else None,
        "strike_coverage": round(strike_cov, 4) if strike_cov is not None else None,
        "strike_share_of_projected": round(strike_raw, 4) if strike_raw is not None else None,
        "far_coverage": round(far_cov, 4) if far_cov is not None else None,
        "com_height_m": round(com_h, 6), "com_offset_from_centre_m": round(com_off, 6),
        "tipping_angle_deg": round(tip, 3),
        "urdf_mass_kg": mass_urdf, "urdf_ixx": ixx_urdf,
        "box_formula_ixx": round(ixx_box, 15),
        "ixx_ratio_urdf_over_box": (round(ixx_urdf / ixx_box, 4) if (ixx_urdf and ixx_box) else None),
        "triangles": len(tris), "vertices": len(verts),
    }
    row["boxiness_ok"] = bool(row["boxiness"] and row["boxiness"] >= BOXINESS_MIN)
    row["closed_ok"] = bool(closed >= CLOSEDNESS_MIN)
    row["base_ok"] = bool(base_cov is not None and base_cov >= BASE_COVERAGE_MIN)
    row["strike_ok"] = bool(strike_cov is not None and strike_cov >= STRIKE_COVERAGE_MIN)
    row["tipping_ok"] = bool(TIPPING_DEG[0] <= tip <= TIPPING_DEG[1])
    # The rigid-box assumption 08 section 3 rests on is checked, and its failure is DISCLOSED rather
    # than smoothed: a hollow shell legitimately has less inertia than a solid block, so a low ratio
    # does not disqualify a box, but it does have to be reported.
    row["inertia_consistent_with_solid_box"] = bool(
        row["ixx_ratio_urdf_over_box"] is not None
        and 0.5 <= row["ixx_ratio_urdf_over_box"] <= 2.0)
    row["usable_as_domino"] = bool(row["boxiness_ok"] and row["closed_ok"] and row["base_ok"]
                                   and row["strike_ok"] and row["tipping_ok"])
    rows.append(row)

rows.sort(key=lambda r: (not r["usable_as_domino"], r["thickness_m"]))
print("=" * 122)
print(f"{'asset_id':42s} {'boxy':>5s} {'closed':>6s} {'base':>5s} {'top':>5s} {'strk':>5s} "
      f"{'tip':>6s} {'h_mm':>7s} {'t_mm':>7s} {'use':>4s}")
for r in rows:
    print(f"{r['asset_id'][:42]:42s} {r['boxiness']:5.3f} {r['closedness']:6.3f} "
          f"{(r['base_coverage'] or 0):5.3f} {(r['top_coverage'] or 0):5.3f} "
          f"{(r['strike_coverage'] or 0):5.3f} {r['tipping_angle_deg']:6.2f} "
          f"{r['standing_h_m']*1000:7.1f} {r['thickness_m']*1000:7.1f} "
          f"{'YES' if r['usable_as_domino'] else '-':>4s}")

usable = [r for r in rows if r["usable_as_domino"]]
print(f"\n{len(usable)} of {len(rows)} measured assets pass the shape test")
print(f"thresholds: boxiness>={BOXINESS_MIN}, closedness>={CLOSEDNESS_MIN}, "
      f"base coverage>={BASE_COVERAGE_MIN}, strike coverage>={STRIKE_COVERAGE_MIN}, "
      f"tipping {TIPPING_DEG[0]}-{TIPPING_DEG[1]} deg")
print("(base/share-of-projected was 0.48-0.50 for the best boxes, which is the ceiling for a closed "
      "solid whose bottom and top both project onto the same footprint -- that is what exposed the "
      "earlier denominator as wrong)")

if usable:
    print(f"\nusable boxes, thinnest first:")
    for r in usable[:10]:
        print(f"  {r['asset_id'][:50]:50s} {r['standing_h_m']*1000:6.1f} x "
              f"{r['thickness_m']*1000:5.1f} x {r['width_m']*1000:6.1f} mm  "
              f"h/t {r['h_over_t']:4.2f}  tip {r['tipping_angle_deg']:5.2f} deg  "
              f"urdf mass {r['urdf_mass_kg']} kg  ixx ratio {r['ixx_ratio_urdf_over_box']}")
    best = usable[0]
    h, t, w = best["standing_h_m"], best["thickness_m"], best["width_m"]
    print(f"\n  --- 12-box chain with {best['asset_id']} (h={h*1000:.1f}, t={t*1000:.1f}, "
          f"w={w*1000:.1f} mm) per 08 section 2: total = 12*t + 11*gap ---")
    for g in (0.15, 0.20, 0.25, 0.30):
        L = 12 * t + 11 * g * h
        print(f"    gap {g:.2f}*h = {g*h*1000:6.1f} mm -> chain {L*1000:7.1f} mm; "
              f"about {L + 1.0:.2f} m of clear run with run-in and run-out")
    print(f"    propagation needs gap < h = {h*1000:.1f} mm; satisfied at every gap above")
    print(f"    lateral requirement per 08: w/t = {best['w_over_t']:.2f} >= 1.5 -> "
          f"{'OK' if (best['w_over_t'] or 0) >= 1.5 else 'NOT MET'}")

masses = [r["urdf_mass_kg"] for r in rows if r["urdf_mass_kg"]]
if masses:
    print(f"\n  URDF mass range across the measured set: {min(masses):.5f} to {max(masses):.5f} kg")
    print(f"  a Cranium-sized game box at 0.0028 kg is a scan artefact, not a physical mass; 08 must "
          f"assign mass from a stated density and disclose it")
ratios = [r["ixx_ratio_urdf_over_box"] for r in rows if r["ixx_ratio_urdf_over_box"]]
if ratios:
    print(f"  inertia ratio (URDF / solid-box formula) range: {min(ratios):.3f} to {max(ratios):.3f}")
    print(f"  values well below 1 are consistent with a HOLLOW shell and must be disclosed wherever "
          f"08 section 3's solid-box formula is used")

(OUT / "box_shape_check.json").write_text(json.dumps({
    "note": ("08 section 2 requires a closed, flat-bottomed box. Base flatness is measured as the "
             "area of the flat contact surface over the nominal bounding footprint; two earlier "
             "versions used denominators that no closed solid can satisfy (surface-area share, "
             "ceiling 1/6; projected-area share, ceiling 1/2) and both rejected every asset."),
    "thresholds": {"boxiness_min": BOXINESS_MIN, "closedness_min": CLOSEDNESS_MIN,
                   "base_coverage_min": BASE_COVERAGE_MIN,
                   "strike_coverage_min": STRIKE_COVERAGE_MIN,
                   "tipping_angle_deg": list(TIPPING_DEG)},
    "measured": len(rows), "usable_count": len(usable),
    "usable": [r["asset_id"] for r in usable],
    "caveats": {
        "urdf_mass": ("URDF masses in this library are scan artefacts; 08 must assign mass from a "
                      "stated density and disclose it"),
        "inertia": ("many assets are hollow, so URDF inertia is below the solid-box formula; where "
                    "08 section 3 uses Ixx = m*(h^2+d^2)/12 the difference must be disclosed"),
    },
    "assets": rows,
}, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'box_shape_check.json'}")
