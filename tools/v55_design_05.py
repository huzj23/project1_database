"""V5.5 stage 05: choose the box-hits-bottle layout from the bottle's measured radius profile.

What went wrong before, and why this version is structured differently:

  * the previous search picked a near-face distance and then DERIVED the contact height from a
    sparse vertex profile. The assembly proxy has only 412 triangles, so its vertices are
    concentrated at the extremes and the profile had a single non-empty slice near the top. Every
    candidate therefore "contacted" 2.5 mm below the top, leaving a 2.5 mm lever arm and no
    tipping moment -- correctly rejected by the H4 check.
  * the profile is now sampled from the TRIANGLE SURFACE densely, so r(z) is real.
  * the search parameter is now the CONTACT HEIGHT itself, which is the physically meaningful
    quantity: 05 requires a real tipping moment, and the moment about the base is the horizontal
    impulse times the contact height. The horizontal offset then follows as r(z*) + half-extent,
    rather than being chosen first and hoped to produce a good contact.

A side strike at any height above the base produces a moment. The failure mode 05 warns about is
a box landing flat on the bottle's TOP, which only compresses it vertically; that is avoided by
keeping the contact height well below the top, which `MIN_LEVER_M` enforces.

The box is the real approved asset, used unmodified. Rotating it about the vertical axis is a
PLACEMENT choice, not a model change, so both long-axis orientations are searched (05 section 4
forbids resizing the model, not orienting it).

Output: outcomes/v55/italian_flat/box_hits_bottle/design.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
RUNTIME = SCENES / "runtime"
OUT = ROOT / "outcomes/v55/italian_flat/box_hits_bottle"
BUILD = ROOT / "models/gso/Big_Dot_Aqua_Pencil_Case"

FLOOR_Z = 0.510600
RIM_Z = 0.522260
MIN_LEVER_M = 0.030
NO_GO_M = 0.050
DROP_CLEARANCE_M = 0.25      # mid-range of 05's required 0.15-0.35 m


def load_obj(path: Path):
    vs, fs = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                vs.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    fs.append((idx[0] - 1, idx[k] - 1, idx[k + 1] - 1))
    return np.asarray(vs, float), np.asarray(fs, np.int64)


def merged(files):
    vs, fs, off = [], [], 0
    for f in files:
        v, fc = load_obj(f)
        vs.append(v)
        fs.append(fc + off)
        off += len(v)
    return np.vstack(vs), np.vstack(fs)


def surface_points(V, F, per_tri=120, seed=0) -> np.ndarray:
    """Uniform points on the mesh surface via barycentric sampling of every triangle."""
    rng = np.random.default_rng(seed)
    tri = V[F]                                     # (n, 3, 3)
    u = rng.random((len(F), per_tri))
    v = rng.random((len(F), per_tri))
    flip = (u + v) > 1.0
    u[flip] = 1.0 - u[flip]
    v[flip] = 1.0 - v[flip]
    a = tri[:, 0][:, None, :]
    b = tri[:, 1][:, None, :]
    c = tri[:, 2][:, None, :]
    pts = a + u[:, :, None] * (b - a) + v[:, :, None] * (c - a)
    return pts.reshape(-1, 3)


def radius_profile(pts, axis_xy, n_bins=120):
    r = np.hypot(pts[:, 0] - axis_xy[0], pts[:, 1] - axis_xy[1])
    z = pts[:, 2]
    edges = np.linspace(z.min(), z.max(), n_bins + 1)
    prof = []
    for i in range(n_bins):
        sel = (z >= edges[i]) & (z <= edges[i + 1])
        if sel.any():
            prof.append({"z_lo": float(edges[i]), "z_hi": float(edges[i + 1]),
                         "z_mid": float(0.5 * (edges[i] + edges[i + 1])),
                         "r_max": float(r[sel].max()),
                         "r_p95": float(np.percentile(r[sel], 95)),
                         "n": int(sel.sum())})
    return prof


def aabb_gap(alo, ahi, blo, bhi):
    gap = np.maximum(np.maximum(blo - ahi, alo - bhi), 0.0)
    if gap.max() > 0:
        return float(np.linalg.norm(gap))
    return -float(min(ahi[0] - blo[0], bhi[0] - alo[0], ahi[1] - blo[1], bhi[1] - alo[1],
                      ahi[2] - blo[2], bhi[2] - alo[2]))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"floor_z": FLOOR_Z, "rim_z": RIM_Z, "min_lever_m": MIN_LEVER_M,
                    "no_go_m": NO_GO_M, "drop_clearance_m": DROP_CLEARANCE_M}

    decision = json.loads((PROPS / "proxy_decision.json").read_text(encoding="utf-8"))
    print("=" * 90)
    print("=== measured prop geometry (world frame, accepted proxies) ===")
    props: dict = {}
    surfaces: dict = {}
    for name in ("bottle_assembly", "glass_a", "glass_b"):
        d = decision[name]
        restore = -np.asarray(d["recentre_offset_m"], float)
        files = sorted((PROPS / name / d["chosen"]).glob("*.obj"))
        V, F = merged(files)
        world = V + restore
        lo, hi = world.min(axis=0), world.max(axis=0)
        props[name] = {"min": lo.tolist(), "max": hi.tolist(),
                       "centre": (0.5 * (lo + hi)).tolist(), "dims": (hi - lo).tolist(),
                       "chosen_proxy": d["chosen"], "triangles": int(len(F)),
                       "vertices": int(len(world))}
        surfaces[name] = surface_points(world, F)
        print(f"  {name:18s} {d['chosen']:6s} tri={len(F):5d} "
              f"centre=({props[name]['centre'][0]:.4f},{props[name]['centre'][1]:.4f},"
              f"{props[name]['centre'][2]:.4f}) dims=({(hi-lo)[0]:.4f},{(hi-lo)[1]:.4f},"
              f"{(hi-lo)[2]:.4f}) top_z={hi[2]:.6f}")

    bp = props["bottle_assembly"]
    bmin, bmax = np.array(bp["min"]), np.array(bp["max"])
    bottle_top = float(bmax[2])
    pts = surfaces["bottle_assembly"]

    # The bottle's axis comes from the base ring, not the AABB centre: the assembly includes the
    # cap, which is offset, so the AABB centre is not the axis.
    base_band = pts[pts[:, 2] <= bmin[2] + 0.005]
    axis_xy = np.array([float(base_band[:, 0].mean()), float(base_band[:, 1].mean())])
    print(f"\n=== bottle axis ===")
    print(f"  base-ring axis ({axis_xy[0]:.6f}, {axis_xy[1]:.6f});  "
          f"AABB centre ({bp['centre'][0]:.6f}, {bp['centre'][1]:.6f}), offset "
          f"{np.linalg.norm(axis_xy - np.array(bp['centre'][:2]))*1000:.3f} mm")
    report["bottle_axis_xy"] = axis_xy.tolist()
    report["bottle_top_z"] = bottle_top

    prof = radius_profile(pts, axis_xy)
    r_max = max(p["r_max"] for p in prof)
    print(f"\n=== radius profile from the axis, {len(prof)} bins over "
          f"{prof[0]['z_lo']:.4f}..{prof[-1]['z_hi']:.4f}; r_max = {r_max*1000:.3f} mm ===")
    print("  (r_max is the widest radius anywhere on the assembly)")
    # Print the profile in the upper 220 mm, which is the region the box can reach.
    print(f"  {'z_lo':>9s} {'z_hi':>9s} {'r_max mm':>9s} {'r_p95 mm':>9s} {'n':>7s}   "
          f"(top - z) mm")
    for p in prof:
        if p["z_mid"] >= bottle_top - 0.240:
            print(f"  {p['z_lo']:9.4f} {p['z_hi']:9.4f} {p['r_max']*1000:9.3f} "
                  f"{p['r_p95']*1000:9.3f} {p['n']:7d}   {(bottle_top-p['z_mid'])*1000:8.2f}")
    report["radius_profile"] = prof
    report["r_max_m"] = r_max

    # ---- the striker ------------------------------------------------------------------
    box_col = BUILD / "collision_geometry.obj"
    bv, bf = load_obj(box_col)
    blo, bhi = bv.min(axis=0), bv.max(axis=0)
    bdims = bhi - blo
    report["box"] = {"asset_id": BUILD.name, "collision_file": str(box_col),
                     "collision_triangles": int(len(bf)),
                     "authored_dimensions_m": bdims.tolist(), "mass_kg": 0.1016,
                     "mass_basis": "estimated",
                     "recentre_offset_m": (0.5 * (blo + bhi)).tolist(),
                     "note": "the real approved asset is used unmodified; only its placement "
                             "orientation is chosen, which 05 section 4 permits"}
    print(f"\n=== approved striker {BUILD.name}: dims "
          f"({bdims[0]:.6f}, {bdims[1]:.6f}, {bdims[2]:.6f}), {len(bf)} tri ===")
    bx, by, bz = float(bdims[0]), float(bdims[1]), float(bdims[2])

    # ---- static colliders and soft zones ---------------------------------------------
    layer = json.loads((SCENES / "layer_report.json").read_text(encoding="utf-8"))
    statics = [{"name": nm, "lo": np.array(i["aabb_min"]), "hi": np.array(i["aabb_max"])}
               for nm, i in layer.get("static_collision", {}).items()]
    soft = layer.get("soft_background", [])

    # ---- search: contact height z*, then orientation ---------------------------------
    # Desired lever arms are searched from small to large; the largest that clears everything is
    # preferred, because a larger lever means a stronger tipping moment.
    levers = [0.03, 0.05, 0.08, 0.12, 0.16, 0.20]
    # ORIENTATION AND THE OFFSET MUST USE THE SAME HALF-EXTENT. Each entry is
    # (name, yaw, half-extent along x AFTER the yaw, half-extent along y AFTER the yaw). The
    # previous version labelled the orientation but computed the offset from the AUTHORED
    # half-extents, so the chosen `long_axis_along_y` case was offset by the authored y half
    # (44.89 mm) while the box, once rotated by 90 degrees, actually presented 104.58 mm along y.
    # The result was a box whose start footprint missed the bottle in y by 0.35 mm and which fell
    # past it with an empty contact log.
    orientations = [
        ("long_axis_along_x", 0.0, bx / 2, by / 2),
        ("long_axis_along_y", math.pi / 2, by / 2, bx / 2),
    ]
    directions = [("+y", np.array([0.0, 1.0])), ("-y", np.array([0.0, -1.0])),
                  ("+x", np.array([1.0, 0.0])), ("-x", np.array([-1.0, 0.0]))]

    print(f"\n=== layout search (05 section 2.6 allows at most 12) ===")
    candidates = []
    n = 0
    for oname, yaw, hx, hy in orientations:
        for lever in levers:
            if n >= 12:
                break
            n += 1
            z_contact = bottle_top - lever
            # Radius at the contact height, from the profile bin containing it.
            r_c = None
            for p in prof:
                if p["z_lo"] <= z_contact <= p["z_hi"]:
                    r_c = p["r_max"]
                    break
            if r_c is None:
                r_c = min(prof, key=lambda p: abs(p["z_mid"] - z_contact))["r_max"]
            # A side strike needs the near face INSIDE the widest radius, so the box catches the
            # shoulder on the way down instead of grazing the widest point.
            shoulder_overlap = r_max - r_c
            # The direction is chosen along whichever horizontal axis keeps the box clear; both
            # are tried and the check below decides.
            best = None
            for dname, dvec in directions:
                half_along = abs(dvec[0]) * hx + abs(dvec[1]) * hy
                offset = r_c + half_along
                box_c = np.array([axis_xy[0] + dvec[0] * offset,
                                  axis_xy[1] + dvec[1] * offset,
                                  bottle_top + DROP_CLEARANCE_M + bz / 2])
                # The START AABB of a rotated box: the rotated half-extents, not the authored
                # ones. This is the quantity the overlap and clearance checks must use.
                box_lo = np.array([box_c[0] - hx, box_c[1] - hy, box_c[2] - bz / 2])
                box_hi = np.array([box_c[0] + hx, box_c[1] + hy, box_c[2] + bz / 2])
                col_lo = np.array([box_c[0] - hx, box_c[1] - hy, z_contact])
                col_hi = np.array([box_c[0] + hx, box_c[1] + hy, box_c[2] + bz / 2])

                reasons = []
                # The strike requires the near face to be inside the bottle's silhouette, which
                # means the box must overlap the bottle in the offset direction.
                if dvec[0] != 0:
                    ov = min(box_hi[0], bmax[0]) - max(box_lo[0], bmin[0])
                else:
                    ov = min(box_hi[1], bmax[1]) - max(box_lo[1], bmin[1])
                if ov <= 0:
                    reasons.append(f"start footprint misses the bottle in the offset axis "
                                   f"by {-ov*1000:.3f} mm")
                for s in statics:
                    g = aabb_gap(box_lo, box_hi, s["lo"], s["hi"])
                    if g <= 0:
                        reasons.append(f"start AABB overlaps {s['name']} by {-g*1000:.1f} mm")
                for gname in ("glass_a", "glass_b"):
                    gl, gh = np.array(props[gname]["min"]), np.array(props[gname]["max"])
                    gg = aabb_gap(col_lo, col_hi, gl, gh)
                    if gg <= 0:
                        reasons.append(f"fall column overlaps {gname} by {-gg*1000:.1f} mm")
                bottle_lo = np.array([bmin[0] - 0.15, bmin[1] - 0.15, FLOOR_Z])
                bottle_hi = np.array([bmax[0] + 0.15, bmax[1] + 0.15, bottle_top + 0.02])
                soft_info = []
                for s in soft:
                    sl, sh = np.array(s["aabb_min"]), np.array(s["aabb_max"])
                    g1 = aabb_gap(col_lo, col_hi, sl, sh)
                    g2 = aabb_gap(bottle_lo, bottle_hi, sl, sh)
                    soft_info.append({"name": s["name"], "gap_to_box_column_m": g1,
                                      "gap_to_bottle_region_m": g2})
                    if g1 < NO_GO_M or g2 < NO_GO_M:
                        reasons.append(f"soft {s['name']} inside the no-go "
                                       f"(box {g1*1000:.1f} mm, bottle {g2*1000:.1f} mm)")
                if not (0.0 < r_c < r_max):
                    reasons.append(f"near face {r_c*1000:.2f} mm is not inside the widest radius "
                                   f"{r_max*1000:.2f} mm")
                rec = {"orientation": oname, "yaw_rad": yaw,
                       "half_x_after_yaw_m": hx, "half_y_after_yaw_m": hy,
                       "direction": dname, "lever_arm_m": lever,
                       "contact_z_m": float(z_contact),
                       "radius_at_contact_m": float(r_c),
                       "shoulder_overlap_m": float(shoulder_overlap),
                       "centre_offset_m": float(offset),
                       "near_face_from_axis_m": float(r_c),
                       "box_centre_start": box_c.tolist(),
                       "box_aabb_start": [box_lo.tolist(), box_hi.tolist()],
                       "offset_axis_overlap_m": float(ov),
                       "soft_distances": soft_info,
                       "passes": not reasons, "reasons_rejected": reasons}
                if best is None or (rec["passes"] and not best["passes"]):
                    best = rec
            best["attempt"] = n
            candidates.append(best)
            mark = "ACCEPT" if best["passes"] else "reject"
            print(f"  #{n:2d} {oname:18s} lever={lever*1000:5.0f} mm dir={best['direction']:3s} "
                  f"r_c={r_c*1000:6.2f} mm overlap={shoulder_overlap*1000:6.2f} mm "
                  f"offset={best['centre_offset_m']*1000:7.2f} mm {mark}"
                  + ("" if best["passes"] else f"  <- {'; '.join(best['reasons_rejected'])}"))
        if n >= 12:
            break

    report["search_attempts"] = n
    report["candidates"] = candidates
    passing = [c for c in candidates if c["passes"]]
    # Selection rule, stated because it is a real choice rather than a formality.
    #
    # `shoulder_overlap_m` is `r_max - r_contact`: how far the box's near face lies INSIDE the
    # bottle's widest silhouette. It measures how DEFINITE the strike is. A large lever arm with
    # a ~0.01 mm overlap is a graze that a 412-triangle proxy may not resolve at all, so the
    # largest lever arm is NOT automatically the best design. Candidates whose overlap is below
    # `MIN_STRIKE_OVERLAP_M` are therefore rejected as grazes, and among the rest the longest
    # lever arm wins, because the tipping moment about the base grows with the contact height.
    MIN_STRIKE_OVERLAP_M = 0.002
    robust = [c for c in passing if c["shoulder_overlap_m"] >= MIN_STRIKE_OVERLAP_M]
    grazes = [c for c in passing if c["shoulder_overlap_m"] < MIN_STRIKE_OVERLAP_M]
    for c in grazes:
        c["passes"] = False
        c["reasons_rejected"].append(
            f"graze: shoulder overlap {c['shoulder_overlap_m']*1000:.3f} mm < "
            f"{MIN_STRIKE_OVERLAP_M*1000:.1f} mm, so the strike may not resolve")
    robust.sort(key=lambda c: (-c["lever_arm_m"], -c["shoulder_overlap_m"]))
    report["passing_count"] = len(passing)
    report["robust_count"] = len(robust)
    report["min_strike_overlap_m"] = MIN_STRIKE_OVERLAP_M
    chosen = robust[0] if robust else None
    report["chosen"] = chosen
    print(f"\n  candidates passing all hard constraints: {len(passing)} "
          f"({len(robust)} of them robust, {len(grazes)} rejected as grazes)")
    if chosen:
        print(f"  CHOSEN attempt #{chosen['attempt']}: {chosen['orientation']} direction "
              f"{chosen['direction']}")
        print(f"    contact at z {chosen['contact_z_m']:.6f} = "
              f"{(bottle_top-chosen['contact_z_m'])*1000:.1f} mm below the top "
              f"{bottle_top:.6f}  -> lever arm {chosen['lever_arm_m']*1000:.1f} mm")
        print(f"    radius at contact {chosen['radius_at_contact_m']*1000:.2f} mm, "
              f"widest radius {r_max*1000:.2f} mm -> shoulder overlap "
              f"{chosen['shoulder_overlap_m']*1000:.2f} mm")
        print(f"    horizontal offset {chosen['centre_offset_m']*1000:.2f} mm, box centre start "
              f"({chosen['box_centre_start'][0]:.4f}, {chosen['box_centre_start'][1]:.4f}, "
              f"{chosen['box_centre_start'][2]:.4f})")
        print(f"    box bottom starts at z "
              f"{chosen['box_centre_start'][2]-bz/2:.6f}, which is "
              f"{(chosen['box_centre_start'][2]-bz/2-bottle_top)*1000:.1f} mm above the top")
    else:
        print("  NO LAYOUT PASSED; the design is NOT accepted and no solve will be run.")

    report["props"] = props
    report["design_valid"] = bool(chosen is not None)
    p = OUT / "design.json"
    p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {p}")
    print(f"\nSTAGE 05 DESIGN: {'PASS' if chosen else 'FAIL'}")
    return 0 if chosen else 1


if __name__ == "__main__":
    raise SystemExit(main())
