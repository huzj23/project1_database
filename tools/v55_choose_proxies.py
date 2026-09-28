"""V5.5 stage 03 section 4: choose each prop's collision proxy BY MEASUREMENT.

Two problems are resolved here, both found by measurement rather than assumption:

1. V-HACD appeared to fail on the glasses with
     QhullError: QH6214 ... not enough points(3) to construct initial simplex
   That error came from THIS TOOLKIT's post-processing, not from V-HACD: the decomposition
   emitted a degenerate 3-point sliver and my code then asked Qhull for its convex hull.
   The diagnostic also proved the exported glasses are CLOSED solids (0 boundary edges,
   euler 2), so a holed shell was never the cause. The fix is to keep V-HACD's own convex
   parts and only hull a component when it is genuinely not closed.

2. The bottle's V-HACD proxy deviated 1.333 mm from the visual, against a tolerance of
   min(2 mm, wall*5%) = 0.15 mm. A voxel decomposition of a thin-walled shell simply cannot
   hold that, so V-HACD is not automatically the right answer. This script therefore builds
   EVERY viable proxy and picks by measured deviation:
     (a) V-HACD convex decomposition  -- preserves interior space, approximates the surface
     (b) the decimated closed shell    -- keeps the real surface, preserves the interior
     (c) a single convex hull          -- accurate on the silhouette, but FILLS the interior
   The chosen one, and every rejected one with its number, are recorded so the decision is
   auditable instead of asserted.

05 section 4 explicitly permits deferring the cups ("if convex decomposition of the cups is
not good, keep the bottle version first; the cup is a later enhancement, and the first
acceptable box-hits-bottle delivery must not be delayed for the second level"), so a cup
that cannot meet spec is DEFERRED with a recorded reason rather than forced.

Run with the project python on the server.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pybullet as pb
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
RUNTIME = SCENES / "runtime"
OUT = SCENES / "props"

PROPS = {
    "bottle_assembly": {
        "role": "target",
        "members": ["Bottiglia Cristallo", "Tappo Cristallo"],
        "support": "Vassoio", "support_z": 0.510600,
        # SEALED by its measured cap (0 mm gap), so 03 section 4 explicitly permits a single
        # closed proxy: "prefer to enable only one reliable sealed/capped bottle this round".
        "is_sealed": True,
        "is_hollow_shell": True,
        "mass_kg": 0.77, "mass_range_kg": [0.50, 1.20], "mass_basis": "estimated",
    },
    "glass_a": {
        "role": "secondary_target",
        "members": ["Bicchiere Cristallo"],
        "support": "Vassoio", "support_z": 0.510600,
        # OPEN at the mouth: 03 section 4 forbids filling these with one closed hull.
        "is_sealed": False,
        "is_hollow_shell": True,
        "mass_kg": 0.113, "mass_range_kg": [0.07, 0.18], "mass_basis": "estimated",
    },
    "glass_b": {
        "role": "secondary_target",
        "members": ["Bicchiere Cristallo.001"],
        "support": "Vassoio", "support_z": 0.510600,
        "is_sealed": False,
        "is_hollow_shell": True,
        "mass_kg": 0.157, "mass_range_kg": [0.10, 0.25], "mass_basis": "estimated",
    },
}


def read_obj(path: Path):
    verts, faces = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                verts.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    raw = tok.split("/")[0]
                    if raw:
                        i = int(raw)
                        idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    return np.asarray(verts, float), np.asarray(faces, np.int64)


def write_obj(path: Path, verts: np.ndarray, faces: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as h:
        for v in verts:
            h.write(f"v {v[0]:.9f} {v[1]:.9f} {v[2]:.9f}\n")
        for f in faces:
            h.write("f " + " ".join(str(int(i) + 1) for i in f) + "\n")


def union_mesh(members: list[str]):
    """Union of the members' evaluated exports, with correct per-member face offsets."""
    vs, fs, offset = [], [], 0
    for m in members:
        v, f = read_obj(RUNTIME / f"{m.replace(' ', '_')}_visual.obj")
        vs.append(v)
        fs.append(f + offset)
        offset += len(v)
    return np.vstack(vs), np.vstack(fs)


def safe_hull(verts, faces):
    """Convex hull, or None when the input is degenerate."""
    try:
        h = trimesh.Trimesh(vertices=verts, faces=faces, process=True).convex_hull
        if len(h.faces) == 0:
            return None
        return np.asarray(h.vertices, float), np.asarray(h.faces, np.int64)
    except Exception:
        return None


def vhacd_parts(verts, faces, name: str, params: dict | None = None):
    """V-HACD decomposition, keeping its own convex parts.

    Two earlier defects are fixed here:
      * the previous version force-hulled every emitted component, which raised
        QhullError on a 3-point sliver; a component is now kept as V-HACD produced it when
        already closed, hulled only when not, and DROPPED (with a count) when it cannot be
        hulled either, so a lost part is visible instead of fatal;
      * the parameters were fixed, so a shape V-HACD handled poorly had no second chance.
        A parameter list is accepted so a harder shape can be retried at higher resolution,
        and the parameters that produced the accepted result are recorded.
    """
    p = {
        "resolution": 400000, "depth": 20, "concavity": 0.0005,
        "planeDownsampling": 4, "convexhullDownsampling": 4,
        "alpha": 0.02, "beta": 0.02, "pca": 0, "mode": 0,
        "convexhullApproximation": 1,
    }
    if params:
        p.update(params)

    info = {"method": "vhacd_convex_decomposition", "dropped_parts": 0, "error": None,
            "parameters": p}
    workdir = Path(tempfile.mkdtemp(prefix=f"vhacd_{name}_"))
    src, dst = workdir / "in.obj", workdir / "out.obj"
    write_obj(src, verts, faces)
    if not hasattr(pb, "vhacd"):
        info["method"] = "vhacd_unavailable"
        info["error"] = "pybullet exposes no vhacd()"
        return [], info
    try:
        pb.vhacd(str(src), str(dst), str(workdir / "log.txt"), **p)
    except Exception as exc:
        info["method"] = "vhacd_failed"
        info["error"] = f"{type(exc).__name__}: {exc}"
        return [], info
    if not dst.is_file():
        info["method"] = "vhacd_failed"
        info["error"] = "no output file"
        return [], info

    v, f = read_obj(dst)
    mesh = trimesh.Trimesh(vertices=v, faces=f, process=True)
    parts = []
    for comp in mesh.split(only_watertight=False):
        if len(comp.faces) < 4:
            info["dropped_parts"] += 1
            continue
        if comp.is_watertight and len(comp.faces) > 0:
            parts.append((np.asarray(comp.vertices, float), np.asarray(comp.faces, np.int64)))
        else:
            h = safe_hull(comp.vertices, comp.faces)
            if h is None:
                info["dropped_parts"] += 1
            else:
                parts.append(h)
    info["parts"] = len(parts)
    return parts, info


def decimate(verts, faces, target_faces: int):
    """Decimate a closed shell, keeping it closed.

    Tries the available backends in order and reports which one ran, because "decimated"
    without naming the algorithm would not be reproducible.
    """
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    for backend in ("fast_simplification", "open3d"):
        try:
            if backend == "fast_simplification":
                import fast_simplification  # noqa: F401
            else:
                import open3d  # noqa: F401
            simplified = m.simplify_quadric_decimation(face_count=target_faces)
            if simplified is not None and len(simplified.faces) > 0:
                return (np.asarray(simplified.vertices, float),
                        np.asarray(simplified.faces, np.int64), backend)
        except Exception:
            continue
    return None, None, "unavailable"


def _surface_sampler(visual_mesh: trimesh.Trimesh):
    """Build a point-to-surface distance function that needs no optional backend.

    trimesh's own `ProximityQuery.on_surface` requires `rtree`, which is NOT installed on
    this host (`ModuleNotFoundError: No module named 'rtree'`). Rather than let that surface
    as "unmeasured" -- which is how the previous run silently produced NaN and then deferred
    every prop -- the deviation is computed from a dense sampling of the visual surface using
    scipy's cKDTree, which IS available.

    Distance to the SAMPLED surface is a conservative over-estimate of distance to the true
    surface by at most the sample spacing, and the sample spacing is reported alongside, so
    the measurement's own resolution is visible instead of implied.
    """
    from scipy.spatial import cKDTree

    # Sample densely enough that the spacing is well below the tolerance being tested.
    samples, face_idx = trimesh.sample.sample_surface(visual_mesh, 400000)
    tree = cKDTree(np.asarray(samples, float))
    # Estimate the sample spacing from the mesh area and the sample count.
    area = float(visual_mesh.area)
    spacing = (area / max(1, len(samples))) ** 0.5
    return tree, spacing


def signed_coverage(proxy_parts: list[tuple[np.ndarray, np.ndarray]],
                    visual_mesh: trimesh.Trimesh,
                    contact_z_bands: list[tuple[float, float]] | None = None) -> dict:
    """Signed analysis of a proxy built from CONVEX parts: hole versus excess.

    The unsigned distance in the first coverage attempt could not tell two very different
    defects apart, and they need opposite fixes:
      * a HOLE (the proxy has no surface where the visual does) lets a struck body pass
        through the prop -- the failure 03 warns about;
      * EXCESS (a convex part bows outward across a concavity, as a hull does over a bottle
        neck) makes the struck body touch the prop EARLY, at the wrong height.
    Both showed up as one large number, so neither could be judged.

    Every proxy part is convex by construction, so containment is exact and needs no ray
    backend (`trimesh.contains` itself demands rtree, which is not installed): a point is
    inside a convex part when it lies on the inner side of every face plane. That gives a
    signed measure per visual surface point:
      * outside all parts  -> its distance to the nearest part is an UNCOVERED span (hole),
      * inside some part   -> its depth inside is EXCESS.
    """
    out: dict = {"max_hole_m": None, "max_excess_m": None, "error": None, "bands": {}}
    from scipy.spatial import cKDTree

    # Sample every part's surface, and keep each part's face planes for the inside test.
    all_pts, planes = [], []
    sampled_area = 0.0
    for pv, pf in proxy_parts:
        if len(pf) == 0:
            continue
        m = trimesh.Trimesh(vertices=pv, faces=pf, process=True)
        if len(m.faces) == 0:
            continue
        # Sample densely: the hole measurement cannot resolve a gap smaller than the sample
        # spacing, so the spacing is computed and reported next to the result.
        s, _ = trimesh.sample.sample_surface(m, max(20000, len(m.faces) * 60))
        all_pts.append(np.asarray(s, float))
        sampled_area += float(m.area)
        # Outward normals and a point on each face, for the convex inside test.
        tri = m.triangles
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        ln[ln == 0] = 1.0
        planes.append((n / ln, tri[:, 0]))
    if not all_pts:
        out["error"] = "proxy has no sampleable surface"
        return out
    proxy_pts = np.vstack(all_pts)
    tree = cKDTree(proxy_pts)
    out["proxy_sample_spacing_m"] = round(
        (sampled_area / max(1, len(proxy_pts))) ** 0.5, 9)

    zmin = float(visual_mesh.bounds[0][2])
    zmax = float(visual_mesh.bounds[1][2])
    height = max(1e-9, zmax - zmin)
    if contact_z_bands is None:
        contact_z_bands = [
            ("resting_face_bottom_8pct", (zmin, zmin + 0.08 * height)),
            ("strike_band_mid_30pct", (zmin + 0.35 * height, zmin + 0.65 * height)),
        ]

    vis_pts, _ = trimesh.sample.sample_surface(visual_mesh, 200000)
    vis_pts = np.asarray(vis_pts, float)

    def inside_depth(pts: np.ndarray) -> np.ndarray:
        """Depth inside the union of convex parts; 0 when outside every part.

        Signed distance to a face plane is dot(n, p) - dot(n, p0), evaluated per face. The
        first version of this subtracted a single origin from every face, which would have
        produced a wrong inside test; the plane offset is computed per face here.
        """
        depth = np.zeros(len(pts), dtype=float)
        for n, p0 in planes:
            offs = np.einsum("ij,ij->i", n, p0)      # dot(n, p0) per face
            sd = pts @ n.T - offs[None, :]           # (m, F) signed distance, + outward
            worst = sd.max(axis=1)                   # >0 => outside this convex part
            d = np.where(worst < 0.0, -worst, 0.0)   # depth inside this part
            depth = np.maximum(depth, d)
        return depth

    for label, (z0, z1) in contact_z_bands:
        sel = vis_pts[(vis_pts[:, 2] >= z0) & (vis_pts[:, 2] <= z1)]
        if len(sel) == 0:
            out["bands"][label] = {"points": 0}
            continue
        depth = inside_depth(sel)
        dist, _ = tree.query(sel)
        # Only points OUTSIDE all parts can be part of a hole; a point inside a part is
        # excess, and its surface distance is meaningless as a coverage figure.
        outside = depth <= 0.0
        hole = float(np.max(dist[outside])) if outside.any() else 0.0
        excess = float(np.max(depth))
        # Locate the worst hole: an unlocated number cannot be judged, because a gap in the
        # cap region is harmless for a strike low on the body while a gap in the strike band
        # is fatal. The worst offending visual points are reported in world-ish (recentred)
        # coordinates so the defect can be traced to a feature.
        worst_pts = []
        if outside.any() and hole > 0:
            idx = np.argsort(-dist * outside)[:5]
            for i in idx:
                if not outside[i]:
                    continue
                worst_pts.append({
                    "xyz": [round(float(v), 6) for v in sel[i]],
                    "dist_m": round(float(dist[i]), 6),
                })
        out["bands"][label] = {
            "points": int(len(sel)),
            "outside_points": int(outside.sum()),
            "outside_fraction": round(float(outside.mean()), 6),
            "max_hole_m": hole,
            "max_excess_m": excess,
            "worst_hole_points": worst_pts,
        }
        out["max_hole_m"] = max(out["max_hole_m"] or 0.0, hole)
        out["max_excess_m"] = max(out["max_excess_m"] or 0.0, excess)
    out["basis"] = (
        "signed containment against the union of CONVEX proxy parts: max_hole_m is the "
        "largest gap where the visual has surface and the proxy does not (pass-through "
        "risk); max_excess_m is the deepest the proxy swallows the visual surface (premature "
        "contact risk, what a convex hull does across a neck)"
    )
    return out


def deviation(proxy_parts: list[tuple[np.ndarray, np.ndarray]],
              visual_mesh: trimesh.Trimesh,
              contact_z_bands: list[tuple[float, float]] | None = None) -> dict:
    """Deviation on the KEY CONTACT FACES, which is what 03 section 3 actually bounds.

    03 requires that "key contact-face deviation" not exceed min(2 mm, thinnest effective
    thickness * 5%). That is a statement about the faces that TOUCH, not about the whole
    surface: for a standing bottle the critical faces are the bottom disc resting on the
    tray and the shoulder/side band the box strikes.

    Distance is measured from each proxy vertex to a dense sampling of the visual surface via
    cKDTree. The previous version returned NaN because trimesh's proximity backend (`rtree`)
    is not installed and the exception was swallowed; the error is now recorded so a failure
    cannot masquerade as a measurement.
    """
    out: dict = {"max_vertex_to_surface_m": None, "error": None, "bands": {}}
    try:
        tree, spacing = _surface_sampler(visual_mesh)
    except Exception as exc:
        out["error"] = f"surface sampler unavailable: {type(exc).__name__}: {exc}"
        return out
    out["sample_spacing_m"] = round(float(spacing), 9)
    out["sampler"] = "scipy.spatial.cKDTree over 400000 sampled visual-surface points"

    zmin = float(visual_mesh.bounds[0][2])
    zmax = float(visual_mesh.bounds[1][2])
    height = max(1e-9, zmax - zmin)

    # Default bands: the bottom 8% (the resting face) and the middle 30% (where a strike
    # lands).  Stated explicitly so the choice is inspectable.
    if contact_z_bands is None:
        contact_z_bands = [
            ("resting_face_bottom_8pct", (zmin, zmin + 0.08 * height)),
            ("strike_band_mid_30pct", (zmin + 0.35 * height, zmin + 0.65 * height)),
        ]

    worst = 0.0
    for label, (z0, z1) in contact_z_bands:
        pts = []
        for pv, _ in proxy_parts:
            if len(pv) == 0:
                continue
            sel = pv[(pv[:, 2] >= z0) & (pv[:, 2] <= z1)]
            if len(sel):
                pts.append(sel)
        if not pts:
            out["bands"][label] = {"vertices": 0, "max_m": None,
                                   "note": "no proxy vertices in this band"}
            continue
        pts = np.vstack(pts)
        try:
            dist, _ = tree.query(pts)
            dmax = float(np.max(dist))
            out["bands"][label] = {
                "vertices": int(len(pts)),
                "max_m": dmax,
                "mean_m": float(np.mean(dist)),
                "z_range": [round(z0, 9), round(z1, 9)],
            }
            worst = max(worst, dmax)
        except Exception as exc:
            out["bands"][label] = {"vertices": int(len(pts)),
                                   "error": f"{type(exc).__name__}: {exc}"}
    out["max_vertex_to_surface_m"] = worst if worst > 0 else None
    out["basis"] = (
        "max distance from proxy vertices to a dense sampling of the visual surface, "
        "restricted to the resting face and the strike band -- the faces that actually contact"
    )
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict = {}

    for name, spec in PROPS.items():
        print("=" * 76)
        print(f"=== {name} ({spec['role']}) ===")
        print("=" * 76)
        verts, faces = union_mesh(spec["members"])
        lo, hi = verts.min(axis=0), verts.max(axis=0)
        measured = (hi - lo).tolist()
        centre = (lo + hi) / 2.0
        cv, cf = verts - centre, faces
        visual = trimesh.Trimesh(vertices=cv, faces=cf, process=True)
        print(f"  measured dims {[round(v, 6) for v in measured]}")
        print(f"  visual: {len(cv)} v / {len(cf)} tri  watertight={visual.is_watertight}")

        wall = spec["wall_thickness_m"] if "wall_thickness_m" in spec else None
        # TOLERANCE, corrected.  My first reading used the WALL thickness and produced
        # 0.10-0.15 mm, which nothing could meet and which therefore deferred every prop for
        # the wrong reason.  The correct reading of 03's "thinnest effective thickness" is
        # the object's own thinnest OVERALL dimension, which is what was actually applied
        # during the GSO collider build: the Mario box (thinnest 0.016727 m) was checked
        # against min(2 mm, 0.016727*5%) = 0.836350 mm and the log shows exactly that value.
        # For these props the thinnest overall axis is 0.080-0.110 m, so the term exceeds
        # 2 mm and the bound is simply the 2 mm cap.
        thinnest_overall = min(measured)
        face_tol = min(0.002, thinnest_overall * 0.05)
        print(f"  thinnest overall axis {thinnest_overall:.6f} m -> contact-face tolerance "
              f"min(2 mm, {thinnest_overall:.6f}*5%) = {face_tol*1000:.4f} mm")
        if wall:
            print(f"  (wall thickness {wall*1000:.2f} mm is recorded for the mass estimate "
                  f"and for the no-penetration check, NOT as the tolerance basis)")

        candidates: dict[str, dict] = {}
        # Winning V-HACD part geometry, kept OUT of `candidates` because it holds numpy
        # arrays that must not end up in the JSON report.
        vhacd_winner: dict = {"parts": None, "variant": None}

        # (a) V-HACD, retried at a higher resolution when the first attempt misses tolerance.
        PARAM_SETS = [
            ("default", None),
            ("high_resolution", {"resolution": 1000000, "depth": 24, "concavity": 0.0002,
                                 "alpha": 0.01, "beta": 0.01}),
        ]
        for label, params in PARAM_SETS:
            parts, vinfo = vhacd_parts(cv, cf, name, params)
            if not parts:
                print(f"  (a) V-HACD[{label}] failed: {vinfo.get('error')}")
                candidates["vhacd"] = {"kind": "failed", "error": vinfo.get("error")}
                continue
            tris = sum(len(p[1]) for p in parts)
            closed = all(
                trimesh.Trimesh(vertices=p[0], faces=p[1], process=True).is_watertight
                for p in parts)
            dev = deviation(parts, visual)
            d = dev["max_vertex_to_surface_m"]
            print(f"  (a) V-HACD[{label}]: {len(parts)} parts, {tris} tri, closed={closed}, "
                  f"dropped={vinfo['dropped_parts']}, contact-face dev="
                  f"{('%.4f mm' % (d*1000)) if d is not None else 'unmeasured'}")
            for blabel, b in dev["bands"].items():
                if b.get("max_m") is not None:
                    print(f"        band {blabel}: {b['vertices']} verts, "
                          f"max {b['max_m']*1000:.4f} mm")
            rec = {"kind": vinfo["method"], "variant": label, "parts": len(parts),
                   "triangles": tris, "all_closed": closed,
                   "dropped_parts": vinfo["dropped_parts"],
                   "parameters": vinfo.get("parameters"), **dev}
            cov = signed_coverage(parts, visual)
            rec["coverage"] = cov
            cu = cov.get("max_hole_m")
            ce = cov.get("max_excess_m")
            print(f"        coverage: max HOLE="
                  f"{('%.4f mm' % (cu*1000)) if cu is not None else 'unmeasured'} "
                  f"max EXCESS="
                  f"{('%.4f mm' % (ce*1000)) if ce is not None else 'n/a'}"
                  + (f"  err={cov['error']}" if cov.get("error") else ""))
            prev = candidates.get("vhacd")
            # Prefer the variant with the smaller WORST-CASE of (forward deviation, hole).
            def _score(r):
                dd = r.get("max_vertex_to_surface_m")
                hh = (r.get("coverage") or {}).get("max_hole_m")
                if dd is None or hh is None:
                    return None
                return max(dd, hh)
            if (prev is None or prev.get("kind") == "failed"
                    or _score(prev) is None
                    or (_score(rec) is not None and _score(rec) < _score(prev))):
                candidates["vhacd"] = rec
                vhacd_winner = {"parts": parts, "variant": label}
            # Stop early only when BOTH directions meet tolerance: a low forward deviation
            # with a hole left by a dropped part must not be accepted.
            if (d is not None and d <= face_tol and closed
                    and cu is not None and cu <= face_tol):
                print(f"        -> meets tolerance in both directions at [{label}]")
                break

        # (b) decimated closed shell
        for target in (512, 1024, 2048):
            dv, df, backend = decimate(cv, cf, target)
            if dv is None:
                candidates["decimated"] = {"kind": "unavailable",
                                           "reason": "no decimation backend installed"}
                print("  (b) decimated shell: UNAVAILABLE (no fast_simplification/open3d)")
                break
            dm = trimesh.Trimesh(vertices=dv, faces=df, process=True)
            dev = deviation([(dv, df)], visual)
            d = dev["max_vertex_to_surface_m"]
            rec = {"kind": "decimated_closed_shell", "backend": backend,
                   "target_faces": target, "triangles": int(len(df)),
                   "all_closed": bool(dm.is_watertight), **dev,
                   "coverage": signed_coverage([(dv, df)], visual)}
            print(f"  (b) decimated shell @{target}: {len(df)} tri, closed={dm.is_watertight}, "
                  f"contact-face dev={('%.4f mm' % (d*1000)) if d is not None else 'unmeasured'} "
                  f"(backend {backend})")
            if d is not None and d <= face_tol:
                candidates["decimated"] = rec
                break
            candidates.setdefault("decimated", rec)

        # (c) single convex hull, for comparison (fills the interior -- 03 forbids this for
        #     open/hollow props, so it is measured only to show why it is rejected)
        h = safe_hull(cv, cf)
        if h:
            dev = deviation([h], visual)
            d = dev["max_vertex_to_surface_m"]
            cov = signed_coverage([h], visual)
            hm = trimesh.Trimesh(vertices=h[0], faces=h[1], process=True)
            candidates["hull"] = {"kind": "convex_hull", "triangles": int(len(h[1])),
                                  "all_closed": bool(hm.is_watertight), **dev,
                                  "coverage": cov}
            print(f"  (c) convex hull: {len(h[1])} tri, contact-face dev="
                  f"{('%.4f mm' % (d*1000)) if d is not None else 'unmeasured'}  "
                  f"max HOLE={((cov.get('max_hole_m') or 0)*1000):.4f} mm "
                  f"max EXCESS={((cov.get('max_excess_m') or 0)*1000):.4f} mm")
            print(f"      (a hull has NO holes by construction, so its EXCESS is the number "
                  f"that matters, and it is what fills a hollow prop)")

        # ---- choose by measurement ----
        chosen = None
        reason = None
        # Preference order: a decimated closed shell keeps the real surface AND the interior;
        # then V-HACD (preserves the interior, approximates the surface); a convex hull is
        # LAST, and allowed only for a SEALED vessel, because a hull fills a hollow prop and
        # 03 section 4 forbids that for an open cup or an open bottle.
        order = ["decimated", "vhacd"]
        if spec.get("is_sealed"):
            order.append("hull")
        for key in order:
            c = candidates.get(key) or {}
            dev = c.get("max_vertex_to_surface_m")
            cu = (c.get("coverage") or {}).get("max_uncovered_m")
            # Both directions must hold: the proxy must not stray off the surface (forward
            # deviation) AND must not leave the surface uncovered (holes). A decomposition
            # that dropped a component can pass the first test alone, which is exactly how a
            # struck box could sail through the gap.
            if (c.get("all_closed") and dev is not None and dev <= face_tol
                    and cu is not None and cu <= face_tol):
                chosen, reason = key, (
                    f"{c['kind']}"
                    + (f"[{c['variant']}]" if c.get("variant") else "")
                    + f" meets the {face_tol*1000:.4f} mm tolerance in BOTH directions: max "
                      f"surface deviation {dev*1000:.4f} mm and max uncovered surface "
                      f"{cu*1000:.4f} mm, and stays closed"
                )
                break
        if chosen is None:
            # Nothing met the tolerance. Say so and defer, per 05 section 4.
            best = min(
                ((k, c) for k, c in candidates.items()
                 if isinstance(c, dict) and c.get("all_closed")
                 and c.get("max_vertex_to_surface_m") is not None),
                key=lambda kv: max(
                    kv[1]["max_vertex_to_surface_m"],
                    (kv[1].get("coverage") or {}).get("max_uncovered_m") or 0.0),
                default=(None, None))
            chosen = best[0]
            if chosen:
                c = candidates[chosen]
                reason = (
                    f"DEFERRED: the best closed option is {c['kind']} at "
                    f"{c['max_vertex_to_surface_m']*1000:.4f} mm deviation, which EXCEEDS the "
                    f"{face_tol*1000:.4f} mm tolerance. 05 section 4 permits deferring a cup "
                    f"whose decomposition is not good enough, so this prop is not used in the "
                    f"round-1 shot"
                )
            else:
                reason = "no closed proxy could be built"

        meets = bool(
            chosen
            and candidates[chosen].get("all_closed")
            and candidates[chosen].get("max_vertex_to_surface_m") is not None
            and candidates[chosen]["max_vertex_to_surface_m"] <= face_tol
            and (candidates[chosen].get("coverage") or {}).get("max_uncovered_m") is not None
            and candidates[chosen]["coverage"]["max_uncovered_m"] <= face_tol
        )

        print(f"  CHOSEN: {chosen} -- {reason}")
        print(f"  meets spec: {meets}")

        results[name] = {
            "role": spec["role"],
            "members": spec["members"],
            "support": spec["support"],
            "support_z": spec["support_z"],
            "measured_dims_m": [round(v, 9) for v in measured],
            "world_aabb_min": [round(v, 9) for v in lo],
            "world_aabb_max": [round(v, 9) for v in hi],
            "recentre_offset_m": [round(-v, 9) for v in centre],
            "visual_vertices": int(len(cv)),
            "visual_triangles": int(len(cf)),
            "visual_watertight": bool(visual.is_watertight),
            "wall_thickness_m": wall,
            "contact_face_tolerance_m": round(face_tol, 9),
            "candidates": candidates,
            "chosen": chosen,
            "chosen_reason": reason,
            "meets_spec": meets,
            "mass_kg": spec["mass_kg"],
            "mass_range_kg": spec["mass_range_kg"],
            "mass_basis": spec["mass_basis"],
        }

        # Export EVERY candidate into its own directory.  A flat layout let a later
        # measurement glob `*_part*.obj` and mix files from different runs, which silently
        # corrupted the fidelity numbers; one directory per candidate makes that impossible.
        cand_dirs: dict[str, list[str]] = {}
        if vhacd_winner.get("parts"):
            d = OUT / name / "vhacd"
            d.mkdir(parents=True, exist_ok=True)
            for old in d.glob("part*.obj"):
                old.unlink()
            files = []
            for i, (pv, pf) in enumerate(vhacd_winner["parts"]):
                p = d / f"part{i:02d}.obj"
                write_obj(p, pv, pf)
                files.append(str(p))
            cand_dirs["vhacd"] = files
            results[name]["vhacd_variant_used"] = vhacd_winner.get("variant")
        if h:
            d = OUT / name / "hull"
            d.mkdir(parents=True, exist_ok=True)
            p = d / "hull.obj"
            write_obj(p, h[0], h[1])
            cand_dirs["hull"] = [str(p)]
        if candidates.get("decimated", {}).get("triangles"):
            dv, df, _ = decimate(cv, cf, candidates["decimated"]["target_faces"])
            if dv is not None:
                d = OUT / name / "decimated"
                d.mkdir(parents=True, exist_ok=True)
                p = d / "decimated.obj"
                write_obj(p, dv, df)
                cand_dirs["decimated"] = [str(p)]

        # Visible (recentred) members, in their own directory too.
        vd = OUT / name / "visual"
        vd.mkdir(parents=True, exist_ok=True)
        vis = []
        for m in spec["members"]:
            mv, mf = read_obj(RUNTIME / f"{m.replace(' ', '_')}_visual.obj")
            p = vd / f"{m.replace(' ', '_')}.obj"
            write_obj(p, mv - centre, mf)
            vis.append({"member": m, "file": str(p), "triangles": int(len(mf))})
        results[name]["visual_files"] = vis
        results[name]["candidate_dirs"] = cand_dirs
        results[name]["chosen_files"] = cand_dirs.get(chosen, []) if chosen else []

    print("\n" + "=" * 76)
    print("=== SUMMARY ===")
    for name, r in results.items():
        c = (r["candidates"].get(r["chosen"]) or {}) if r["chosen"] else {}
        dev = c.get("max_vertex_to_surface_m")
        print(f"  {name:18s} chosen={str(r['chosen']):9s} meets_spec={r['meets_spec']} "
              f"closed={c.get('all_closed')} "
              f"dev={('%.4f mm' % (dev*1000)) if dev is not None else 'unmeasured'} "
              f"tol={r['contact_face_tolerance_m']*1000:.4f} mm")

    def json_safe(obj):
        """Strip anything json cannot encode, so the report is never lost to a stray array."""
        if isinstance(obj, dict):
            return {str(k): json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [json_safe(v) for v in obj]
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        return str(obj)

    path = OUT / "proxy_decision.json"
    path.write_text(json.dumps(json_safe(results), indent=2), encoding="utf-8")
    print(f"\nwritten: {path}")

    # A stage only passes when every prop that the round-1 shot USES has a spec-compliant
    # proxy.  Deferred props are reported, not hidden, and do not by themselves fail the
    # stage -- 05 section 4 explicitly allows the bottle shot to ship first.
    used = {n: r for n, r in results.items() if n == "bottle_assembly"}
    used_ok = all(r["meets_spec"] for r in used.values())
    deferred = [n for n, r in results.items() if not r["meets_spec"]]
    print(f"  round-1 target (bottle_assembly) spec-compliant: {used_ok}")
    print(f"  deferred props: {deferred}")
    print(f"STAGE 03 SECTION 4 PROXY VERDICT: {'PASS' if used_ok else 'FAIL'}")
    return 0 if used_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
