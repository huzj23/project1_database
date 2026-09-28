"""V5.5 stage 03 section 4: classify WHERE the large ray deviations actually are.

The fidelity pass showed large first-hit deviations that neither forward nor containment
measurement could interpret:
  * glass_a: V-HACD max 112 mm at cos_down=+0.80 (oblique), while downward was 1.28 mm;
  * the bottle: 61 mm on near-vertical downward rays for BOTH the hull and V-HACD.

Two hypotheses could explain that, and they demand opposite responses:
  H1 the proxy is genuinely fat/thin where a body would touch it (a real defect);
  H2 the reference mesh is a hollow SHELL, so a ray aimed at the object enters an opening
     (a cup's mouth, a bottle's base punt or its open top) and the "first hit" lands on an
     INTERIOR surface that no external body can ever touch (a measurement artifact).

This distinguishes them by printing, for the worst rays, the actual first-hit POINT on the
visual and on the proxy, plus whether that visual hit is on the object's OUTER boundary.
Outer-boundary membership is decided without rtree by comparing the hit point against the
visual's convex hull: a hit on the outer boundary lies on the hull surface (within a small
band), while an interior hit lies strictly inside the hull.

The consequence for the stage is direct: if every large deviation is H2, the proxy is sound
for contact and the metric must be restricted to outer-boundary rays; if any is H1, the proxy
must be rejected.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
PROPS = ROOT / "outcomes/v55/scenes/italian_flat/props"


def load(path: Path) -> trimesh.Trimesh:
    return trimesh.load(str(path), process=True, force="mesh")


def first_hit(origin, direction, tri, batch=64):
    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    out = np.full(len(origin), np.nan)
    out_tri = np.full(len(origin), -1, dtype=int)
    eps = 1e-12
    for s in range(0, len(origin), batch):
        o, d = origin[s:s + batch], direction[s:s + batch]
        pvec = np.cross(d[:, None, :], e2[None, :, :])
        det = np.einsum("bmk,mk->bm", pvec, e1)
        ok = np.abs(det) > eps
        inv = np.zeros_like(det)
        inv[ok] = 1.0 / det[ok]
        tvec = o[:, None, :] - v0[None, :, :]
        u = np.einsum("bmk,bmk->bm", tvec, pvec) * inv
        ok &= (u >= -1e-9) & (u <= 1 + 1e-9)
        qvec = np.cross(tvec, e1[None, :, :])
        v = np.einsum("bk,bmk->bm", d, qvec) * inv
        ok &= (v >= -1e-9) & (u + v <= 1 + 1e-9)
        t = np.einsum("mk,bmk->bm", e2, qvec) * inv
        ok &= t > 1e-9
        tw = np.where(ok, t, np.inf)
        best = tw.min(axis=1)
        arg = tw.argmin(axis=1)
        found = np.isfinite(best)
        out[s:s + batch] = np.where(found, best, np.nan)
        out_tri[s:s + batch] = np.where(found, arg, -1)
    return out, out_tri


def hull_distance(mesh: trimesh.Trimesh, pts: np.ndarray) -> np.ndarray:
    """Distance from points to the mesh's convex hull surface (unsigned, no rtree)."""
    hull = mesh.convex_hull
    from scipy.spatial import cKDTree
    s, _ = trimesh.sample.sample_surface(hull, 300000)
    tree = cKDTree(np.asarray(s, float))
    d, _ = tree.query(pts)
    return d


def analyse(name: str, n_rays: int = 4096, seed: int = 55) -> dict:
    vis_files = sorted((PROPS / name / "visual").glob("*.obj"))
    visual = trimesh.util.concatenate([load(p) for p in vis_files])
    visual = trimesh.Trimesh(vertices=np.asarray(visual.vertices, float),
                             faces=np.asarray(visual.faces, np.int64), process=True)
    vtri = np.asarray(visual.triangles, float)

    cand = {"vhacd": sorted((PROPS / name / "vhacd").glob("part*.obj")),
            "hull": sorted((PROPS / name / "hull").glob("*.obj"))}

    lo, hi = visual.bounds
    centre = (lo + hi) / 2.0
    start_r = float(np.linalg.norm(hi - lo) / 2.0) * 3.0
    rng = np.random.default_rng(seed)
    dirs = rng.normal(size=(n_rays, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    origins = centre[None, :] - dirs * start_r
    din = centre[None, :] - origins
    din /= np.linalg.norm(din, axis=1, keepdims=True)
    cos_down = -din[:, 2]

    t_vis, tri_vis = first_hit(origins, din, vtri)
    vis_hit_pts = origins + din * t_vis[:, None]

    # Is each visual hit on the OUTER boundary?  Compare against the convex hull: a hit on
    # the outer surface is ~0 from the hull, an interior hit (inside a mouth or a punt) is
    # strictly inside and therefore a measurable distance from the hull surface.
    hd = hull_distance(visual, vis_hit_pts)
    # Threshold choice matters and the first attempt got it wrong.  A hit on the true outer
    # surface is ~0 from the convex hull, because for a convex region the hull IS the
    # surface.  The first version used 2 mm, which is the same size as the bottle's base
    # PUNT (~1.5 mm deep) and so classified that sealed, downward-facing dimple as outer
    # surface.  The threshold is now tight, and counts are reported across several
    # thresholds so the classification is shown to be insensitive to the exact value.
    OUTER_TOL = 0.0002
    sens = {f"{t*1000:g}mm": int((hd <= t).sum()) for t in
            (0.00005, 0.0001, 0.0002, 0.0005, 0.001, 0.002)}

    rep = {"visual_triangles": int(len(visual.faces)),
           "outer_tol_m": OUTER_TOL,
           "outer_count_sensitivity": sens,
           "candidates": {}}
    print("=" * 74)
    print(f"== {name}: visual {len(visual.vertices)} v / {len(visual.faces)} tri")
    print(f"   hull-distance of visual hits: max={hd.max()*1000:.3f} mm "
          f"p99={np.percentile(hd, 99)*1000:.3f} mm")
    print(f"   outer-boundary ray counts by threshold: {sens}")

    for label, files in cand.items():
        if not files:
            continue
        parts = []
        for f in files:
            m = load(f)
            parts.append((np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)))
        ptri = np.vstack([pv[pf] for pv, pf in parts if len(pf)])
        t_prox, _ = first_hit(origins, din, ptri)
        both = np.isfinite(t_vis) & np.isfinite(t_prox)
        dev = np.abs(t_vis - t_prox)

        outer = both & (hd <= OUTER_TOL)          # rays that touch the real outer surface
        interior = both & (hd > OUTER_TOL)        # rays that reach an INTERIOR surface

        # Report the outer-boundary statistics at EVERY threshold, so the conclusion does
        # not depend on one arbitrary cut.
        by_tol = {}
        for t in (0.00005, 0.0001, 0.0002, 0.0005, 0.001, 0.002):
            o = both & (hd <= t)
            b = o & (dev > 0.002)
            by_tol[f"{t*1000:g}mm"] = {
                "outer_rays": int(o.sum()),
                "outer_over_tol": int(b.sum()),
                "outer_max_m": float(dev[o].max()) if o.any() else None,
            }
        print(f"   {label:6s} outer-only max by threshold: " + "  ".join(
            f"{k}:{(v['outer_max_m'] or 0)*1000:.2f}mm/{v['outer_over_tol']}bad"
            for k, v in by_tol.items()))
        print(f"          ALL max={dev[both].max()*1000:8.3f} mm | "
              f"INTERIOR rays={interior.sum()} max="
              f"{(dev[interior].max()*1000) if interior.any() else 0:8.3f} mm")

        # Where do the outer-boundary failures sit, if any?
        bad = outer & (dev > 0.002)
        det = []
        if bad.any():
            for gi in np.nonzero(bad)[0][:6]:
                det.append({
                    "dev_m": round(float(dev[gi]), 6),
                    "cos_down": round(float(cos_down[gi]), 4),
                    "visual_hit": [round(float(x), 6) for x in vis_hit_pts[gi]],
                    "hull_dist_m": round(float(hd[gi]), 6),
                    "approach": ("downward" if cos_down[gi] > 0.9 else
                                 "upward" if cos_down[gi] < -0.9 else
                                 "horizontal" if abs(cos_down[gi]) < 0.15 else "oblique"),
                })
            print(f"          outer-boundary deviations over tolerance: {bad.sum()}")
            for d in det:
                print(f"            {d['dev_m']*1000:8.3f} mm {d['approach']:10s} "
                      f"cos_down={d['cos_down']:+.3f} hull_dist={d['hull_dist_m']*1000:.3f}")
        else:
            print("          outer-boundary deviations over tolerance: 0")

        rep["candidates"][label] = {
            "triangles": int(len(ptri)),
            "all_max_m": float(dev[both].max()) if both.any() else None,
            "outer_rays": int(outer.sum()),
            "outer_max_m": float(dev[outer].max()) if outer.any() else None,
            "outer_over_tol": int(bad.sum()),
            "interior_rays": int(interior.sum()),
            "interior_max_m": float(dev[interior].max()) if interior.any() else None,
            "outer_over_tol_detail": det,
            "by_threshold": by_tol,
        }
    return rep


def main() -> int:
    out = {}
    for name in ("bottle_assembly", "glass_a", "glass_b"):
        out[name] = analyse(name)
    p = ROOT / "outcomes/v55/scenes/italian_flat/proxy_ray_classification.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {p}")

    print("\n=== VERDICT ===")
    for name, r in out.items():
        v = r["candidates"].get("vhacd", {})
        h = r["candidates"].get("hull", {})
        print(f"  {name:18s} vhacd outer>{2}mm={v.get('outer_over_tol')} "
              f"hull outer>{2}mm={h.get('outer_over_tol')} "
              f"| vhacd interior_rays={v.get('interior_rays')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
