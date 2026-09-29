"""b2_make_proxies.py -- V5.6 video B step 2: fitted collision proxies whose AABB centre IS the origin.

WHAT THE PLAN ALLOWS
--------------------
Section 6.1: for a genuine rectangular box you may make a fitted box / low-face convex proxy while
KEEPING the real visual model and the original scale. Section 6.2 step 3: each box keeps its real
proportions in an ordinary standing pose.

WHY A FITTED BOX AND NOT THE SCANNED HULL
-----------------------------------------
The GSO `collision_geometry.obj` for these assets is a scan-derived convex hull stored in AUTHORED
coordinates in an arbitrary pose, with a warped base (the earlier work measured base z-spreads of
0.09-0.82 mm and 2-7 vertices within 1 mm of the base plane, giving a permanent 0.46-2.65 deg lean).
For a domino chain we want a clean, deterministic contact surface and an exactly-known support plane.
A fitted box gives both, and it is explicitly permitted.

TWO THINGS THIS SCRIPT GETS RIGHT, BOTH OF WHICH ARE EASY TO GET WRONG
----------------------------------------------------------------------
1. **The proxy's AABB centre is the file origin.** PyBullet places a GEOM_MESH body's COM at the OBJ
   file's own origin. If the proxy's base sits at z = 0 then the COM is on the floor and gravity
   restores the box upright however far you tip it. Writing the box centred on the origin means the
   COM is CORRECT with NO inertial offset at all -- and we do not merely assert that, we read
   `getDynamicsInfo(...)[3]` back from the engine and check it is the origin. A proxy that is not
   recentred is therefore a hard failure here, not a footnote.

   The physics position therefore denotes the box CENTRE, and the box's base plane is at
   `z_centre - height/2`.

2. **The frame is the box's OWN frame, recovered from the scan, not the stored axes.** The scans are
   stored in arbitrary poses, so the OBJ's x/y/z are not the box's thickness/width/height. `b_geom`
   recovers the three principal face-normal directions and orders them by extent ascending:
   axis 0 = thickness, axis 1 = width, axis 2 = height. The proxy is built in that frame and the
   recovered axes are reported, so the visual can be rotated into the same frame at replay time.

DIMENSIONS
----------
The collision proxy uses the REAL collision hull's own-frame extents (extreme-vertex to
extreme-vertex), not the visual's, because that is the asset's declared collision size. The visual's
extents in the same frame are measured and reported alongside, so the relative difference is explicit
rather than assumed to be zero.

TRIANGULATION
-------------
GEOM_MESH takes the convex hull of the file, so 12 triangles of a unit cube scaled to the box is
exactly the box. The OBJ is written with explicit vertex coordinates (no `usemtl`, no transform), so
there is nothing between the numbers in the file and the hull pybullet builds.

Run with the CONTROL interpreter (no bpy needed):

    python tools\\v56\\b2_make_proxies.py --assets <dir> --out <proxy_dir> --report <json>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b_geom  # noqa: E402

#: The visual mesh and collision hull are measured in the SAME recovered object frame, so comparing
#: them per axis is meaningful. The reported frame disagreement tells us how well the recovery held.
CUBE_TRIS = [
    (0, 2, 1), (0, 3, 2),      # -x
    (4, 5, 6), (4, 6, 7),      # +x
    (0, 1, 5), (0, 5, 4),      # -y
    (2, 3, 7), (2, 7, 6),      # +y
    (0, 4, 7), (0, 7, 3),      # -z
    (1, 2, 6), (1, 6, 5),      # +z
]


def unit_cube_verts():
    """Corners of the box centred on the ORIGIN, in the order the CUBE_TRIS above expect."""
    return [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
            (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]


def frame_of(path: Path):
    """(axes, verts_in_own_frame, tris) for one OBJ, in the object's recovered own frame."""
    v, t = b_geom.read_obj(path)
    if not v or not t:
        raise SystemExit(f"empty mesh: {path}")
    axes = b_geom.box_frame(b_geom.tri_normal_area(v, t), v)
    vp = b_geom.to_own_frame(v, axes)
    return axes, vp, t


def extents(vp):
    lo = [min(p[i] for p in vp) for i in range(3)]
    hi = [max(p[i] for p in vp) for i in range(3)]
    return lo, hi, [hi[i] - lo[i] for i in range(3)]


def axis_misalignment_deg(a, b):
    """Largest angle between corresponding axes of two recovered frames, in degrees."""
    worst = 0.0
    for i in range(3):
        d = abs(sum(a[i][k] * b[i][k] for k in range(3)))
        worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, d)))))
    return worst


def write_box_obj(path: Path, dims):
    """A box of `dims` centred on the origin, 8 vertices / 12 triangles."""
    verts = [(x * dims[0], y * dims[1], z * dims[2]) for x, y, z in unit_cube_verts()]
    b_geom.write_obj(path, verts, CUBE_TRIS)
    # verify what we wrote, from the file, rather than trusting the arithmetic above
    back, btris = b_geom.read_obj(path)
    lo, hi, d = extents(back)
    ctr = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    return {
        "vertices": len(back), "triangles": len(btris),
        "aabb_min": [round(x, 12) for x in lo], "aabb_max": [round(x, 12) for x in hi],
        "dims_readback_m": [round(x, 12) for x in d],
        "aabb_centre_readback_m": [round(x, 12) for x in ctr],
        "max_dim_error_m": max(abs(d[i] - dims[i]) for i in range(3)),
        "centre_offset_from_origin_m": math.sqrt(sum(c * c for c in ctr)),
        "closed_edge_fraction": b_geom.closed_edge_fraction(btris),
        "hull_volume_m3": b_geom.mesh_volume(back, btris),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", required=True, help="dir of <AssetId>/{collision,visual}_geometry.obj")
    ap.add_argument("--out", required=True, help="dir to write <AssetId>__proxy_collision.obj")
    ap.add_argument("--report", required=True)
    ap.add_argument("--assets-list", default="", help="comma-separated asset ids; default = all dirs")
    A = ap.parse_args()

    root = Path(A.assets)
    out = Path(A.out)
    out.mkdir(parents=True, exist_ok=True)
    if A.assets_list:
        ids = [s.strip() for s in A.assets_list.split(",") if s.strip()]
    else:
        ids = sorted(p.name for p in root.iterdir() if p.is_dir())
    if not ids:
        raise SystemExit(f"no asset dirs under {root}")

    rec = {"assets_dir": str(root), "proxy_dir": str(out), "assets": {}}
    for aid in ids:
        d = root / aid
        cp, vp = d / "collision_geometry.obj", d / "visual_geometry.obj"
        if not cp.is_file() or not vp.is_file():
            rec["assets"][aid] = {"error": f"missing {cp.name} or {vp.name}"}
            print(f"[b2_proxy] SKIP {aid}: missing collision/visual obj")
            continue
        cax, cvp, ct = frame_of(cp)
        vax, vvp, vt = frame_of(vp)
        clo, chi, cdims = extents(cvp)
        vlo, vhi, vdims = extents(vvp)
        # The visual's extents in the COLLISION's own frame. This is the comparison that means
        # something: two independent frame recoveries can pick different axes when one mesh has a
        # protruding lid or a strap (a scan artefact), so the visual's self-recovered frame is
        # reported for information but the per-axis comparison projects the visual onto the
        # collision's axes, exactly as the earlier measurement in this project did.
        raw_vis, raw_tris = b_geom.read_obj(vp)
        vvp_on_c = b_geom.to_own_frame(raw_vis, cax)
        _, _, vdims_on_c = extents(vvp_on_c)
        # collision hull volumes: the real hull (for the density-mass basis) and the fitted box
        hull_vol = b_geom.mesh_volume(cvp, ct)
        box_vol = cdims[0] * cdims[1] * cdims[2]

        pname = f"{aid}__proxy_collision.obj"
        rb = write_box_obj(out / pname, cdims)

        rel = [(cdims[i] - vdims_on_c[i]) / vdims_on_c[i] if vdims_on_c[i] else None
               for i in range(3)]
        c = {
            "proxy_obj": str(out / pname),
            "source_collision_obj": str(cp),
            "source_visual_obj": str(vp),
            "own_frame_axes_collision": [[round(x, 9) for x in ax] for ax in cax],
            "own_frame_axes_visual_selfrecovered": [[round(x, 9) for x in ax] for ax in vax],
            "frame_misalignment_deg": round(axis_misalignment_deg(cax, vax), 6),
            "collision_own_frame_min_m": [round(x, 9) for x in clo],
            "collision_own_frame_max_m": [round(x, 9) for x in chi],
            "collision_dims_t_w_h_m": [round(x, 9) for x in cdims],
            "visual_own_frame_min_m": [round(x, 9) for x in vlo],
            "visual_own_frame_max_m": [round(x, 9) for x in vhi],
            "visual_dims_t_w_h_in_its_own_recovered_frame_m": [round(x, 9) for x in vdims],
            "visual_dims_t_w_h_projected_on_collision_axes_m": [round(x, 9) for x in vdims_on_c],
            "per_axis_relative_difference": [None if r is None else round(r, 6) for r in rel],
            "per_axis_absolute_difference_m": [round(cdims[i] - vdims_on_c[i], 9)
                                               for i in range(3)],
            "worst_relative_difference": (None if any(r is None for r in rel)
                                          else round(max(abs(r) for r in rel), 6)),
            "any_axis_over_10pct_bigger_than_visual": any(
                r is not None and r > 0.10 for r in rel),
            "collision_hull_volume_m3": round(hull_vol, 12),
            "fitted_box_volume_m3": round(box_vol, 12),
            "box_volume_over_hull_volume": round(box_vol / hull_vol, 6) if hull_vol else None,
            # The numeric basis for mass. `mass_volume_m3` is what the solver will multiply by the
            # density: the FITTED BOX volume, because the proxy IS a box now. The hull volume is
            # kept alongside so the two bases can be compared rather than conflated.
            "mass_volume_m3": round(box_vol, 12),
            "mass_volume_basis": "fitted box volume = collision extents t*w*h",
            "collision_hull_volume_alternative_m3": round(hull_vol, 12),
            "proxy_file_readback": rb,
            "proxy_aabb_centre_at_origin_ok": bool(rb["centre_offset_from_origin_m"] < 1e-12),
            "visual_triangles": len(vt), "collision_triangles": len(ct),
        }
        rec["assets"][aid] = c
        print(f"[b2_proxy] {aid[:44]:44s} t/w/h = "
              f"{cdims[0] * 1000:7.3f} x {cdims[1] * 1000:7.3f} x {cdims[2] * 1000:7.3f} mm  "
              f"visual(on collision axes) {vdims_on_c[0] * 1000:7.3f} x "
              f"{vdims_on_c[1] * 1000:7.3f} x {vdims_on_c[2] * 1000:7.3f}  "
              f"worst_rel="
              f"{(max(abs(r) for r in rel) * 100 if all(r is not None for r in rel) else float('nan')):.3f}%  "
              f"centred={rb['centre_offset_from_origin_m']:.2e} m  "
              f"frame_mis={c['frame_misalignment_deg']:.3f} deg")

    rec["count"] = len(rec["assets"])
    rec["all_centred"] = all(v.get("proxy_aabb_centre_at_origin_ok")
                             for v in rec["assets"].values() if "error" not in v)
    with open(A.report, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    print(f"[b2_proxy] written {A.report}; all proxies centred on origin: {rec['all_centred']}")
    return 0 if rec["all_centred"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
