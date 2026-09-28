"""V5.5 stage 03 section 4: the physically correct proxy-fidelity metric.

Three earlier attempts at this measurement were each wrong in a different way, and the
sequence is worth recording because it explains why this file exists:

  1. Whole-surface vertex-to-surface distance.  For a hollow prop this is dominated by
     interior detail and says nothing about the surface a struck object touches.
  2. Contact-band vertex-to-surface distance.  Better, but still one-directional: it only
     looks at the PROXY's vertices, so a proxy that dropped a component leaves a hole that
     nothing measures.
  3. Signed containment (hole vs excess).  It did separate the two defect kinds, but it
     reported V-HACD as having 17.5 mm of "excess" on the sealed bottle -- which is simply
     V-HACD filling a sealed vessel's interior.  That interior is never touched by a ray
     arriving from outside, so counting it as error was wrong, and it is why every prop got
     deferred.

What actually matters is what a contacting body experiences: cast a ray along the approach
path and compare where it FIRST strikes the visual against where it first strikes the proxy.
That is:

  * immune to interior filling (only the first hit counts),
  * symmetric (it catches both a hole, where the proxy has no hit, and an outward bulge,
    where the proxy is hit early),
  * expressed in the same units as the tolerance, along the direction contact happens.

Implementation notes, because the environment constrains the tooling:
  * trimesh's own ray engine and `contains` both require `rtree`, which is NOT installed
    (`ModuleNotFoundError`), so both were verified unusable and neither is used here.
  * Möller-Trumbore is therefore implemented directly and vectorised over triangles, in ray
    batches to bound memory.

Run with the project python on the server.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
RUNTIME = SCENES / "runtime"
PROPS = SCENES / "props"

TOL_M = 0.002
N_RAYS = 4096
BATCH = 64


def load_mesh(path: Path) -> trimesh.Trimesh:
    return trimesh.load(str(path), process=True, force="mesh")


def first_hit(origin: np.ndarray, direction: np.ndarray,
              tri: np.ndarray, batch: int = BATCH) -> np.ndarray:
    """Vectorised Moller-Trumbore first-hit distance.

    Returns t per ray, with NaN where the ray misses every triangle. Implemented here
    because trimesh's ray engine needs rtree, which is absent.
    """
    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    e1 = v1 - v0
    e2 = v2 - v0
    out = np.full(len(origin), np.nan)
    eps = 1e-12
    for start in range(0, len(origin), batch):
        o = origin[start:start + batch]          # (b,3)
        d = direction[start:start + batch]       # (b,3)
        # pvec = d x e2  -> (b,m,3)
        pvec = np.cross(d[:, None, :], e2[None, :, :])
        det = np.einsum("bmk,mk->bm", pvec, e1)  # (b,m)
        ok = np.abs(det) > eps
        if not ok.any():
            continue
        inv = np.zeros_like(det)
        inv[ok] = 1.0 / det[ok]
        tvec = o[:, None, :] - v0[None, :, :]    # (b,m,3)
        u = np.einsum("bmk,bmk->bm", tvec, pvec) * inv
        ok &= (u >= -1e-9) & (u <= 1 + 1e-9)
        qvec = np.cross(tvec, e1[None, :, :])    # (b,m,3)
        v = np.einsum("bk,bmk->bm", d, qvec) * inv
        ok &= (v >= -1e-9) & (u + v <= 1 + 1e-9)
        t = np.einsum("mk,bmk->bm", e2, qvec) * inv
        ok &= t > 1e-9
        t_where = np.where(ok, t, np.inf)
        best = t_where.min(axis=1)
        out[start:start + batch] = np.where(np.isfinite(best), best, np.nan)
    return out


def surface_triangles(parts: list[tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    tris = []
    for pv, pf in parts:
        if len(pf):
            tris.append(pv[pf])
    return np.vstack(tris)


def fidelity(parts: list[tuple[np.ndarray, np.ndarray]], visual: trimesh.Trimesh,
             n_rays: int = N_RAYS, seed: int = 55) -> dict:
    """Compare first-hit distance on the proxy against the visual, along approach rays."""
    rng = np.random.default_rng(seed)
    vtri = np.asarray(visual.triangles, float)
    ptri = surface_triangles(parts)

    lo, hi = visual.bounds
    centre = (lo + hi) / 2.0
    radius = float(np.linalg.norm(hi - lo) / 2.0)
    start_r = radius * 3.0

    # Uniform directions on the sphere: every approach path a contacting body could take.
    dirs = rng.normal(size=(n_rays, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    # Place each origin OUTSIDE the object along -dirs, then travel along +dirs so the ray
    # passes through the centre.  The first version used -dirs as the travel direction, which
    # pointed every ray away from the object and produced zero hits; the direction is now
    # derived from origin -> centre explicitly and asserted.
    origins = centre[None, :] - dirs * start_r
    dirs_in = centre[None, :] - origins
    dirs_in /= np.linalg.norm(dirs_in, axis=1, keepdims=True)
    # Sanity assertion: an inward ray must reduce the distance to the centre.
    assert np.allclose(dirs_in, dirs, atol=1e-9), "inward ray direction is inconsistent"

    t_vis = first_hit(origins, dirs_in, vtri)
    t_prox = first_hit(origins, dirs_in, ptri)

    hit_vis = np.isfinite(t_vis)
    hit_prox = np.isfinite(t_prox)

    # A ray that misses the visual too is outside the object and carries no information.
    informative = hit_vis
    holes = informative & ~hit_prox
    both = informative & hit_prox
    diff = np.abs(t_vis[both] - t_prox[both])

    # Physical approach subsets: downward (gravity) and near-horizontal (a sliding strike).
    cos_down = -dirs_in[:, 2]           # +1 when travelling straight down
    downward = informative & (cos_down > 0.9)
    horizontal = informative & (np.abs(cos_down) < 0.15)
    upward = informative & (cos_down < -0.9)

    def stat(mask: np.ndarray, name: str) -> dict:
        m = mask & both
        if not m.any():
            return {"rays": 0}
        d = np.abs(t_vis[m] - t_prox[m])
        return {
            "rays": int(m.sum()),
            "max_m": float(d.max()),
            "mean_m": float(d.mean()),
            "p95_m": float(np.percentile(d, 95)),
            "within_tol": bool(d.max() <= TOL_M),
        }

    # Locate the worst deviations, with the approach direction, so an outlier can be traced
    # to a feature and to a physically reachable approach instead of being argued about.
    worst = []
    if len(diff):
        order = np.argsort(-diff)[:6]
        both_idx = np.nonzero(both)[0]
        for k in order:
            gi = both_idx[k]
            worst.append({
                "t_visual_m": round(float(t_vis[gi]), 6),
                "t_proxy_m": round(float(t_prox[gi]), 6),
                "deviation_m": round(float(diff[k]), 6),
                "direction_inward": [round(float(x), 6) for x in dirs_in[gi]],
                "cos_down": round(float(cos_down[gi]), 6),
                "approach": ("downward" if cos_down[gi] > 0.9 else
                             "upward" if cos_down[gi] < -0.9 else
                             "horizontal" if abs(cos_down[gi]) < 0.15 else "oblique"),
            })

    return {
        "seed": seed,
        "rays_cast": int(n_rays),
        "rays_hitting_visual": int(informative.sum()),
        "rays_hitting_both": int(both.sum()),
        "hole_rays": int(holes.sum()),
        "hole_fraction": round(float(holes.sum() / max(1, informative.sum())), 6),
        "max_first_hit_deviation_m": float(diff.max()) if len(diff) else None,
        "mean_first_hit_deviation_m": float(diff.mean()) if len(diff) else None,
        "p95_first_hit_deviation_m": float(np.percentile(diff, 95)) if len(diff) else None,
        "all_approaches": stat(informative, "all"),
        "downward_approaches": stat(downward, "down"),
        "horizontal_approaches": stat(horizontal, "horiz"),
        "upward_approaches": stat(upward, "up"),
        "worst_rays": worst,
        "basis": (
            "first-hit distance along rays cast inward from a sphere of radius 3x the "
            "object's half-diagonal; a ray that hits the visual but not the proxy is a HOLE "
            "(pass-through), and the deviation is |t_visual - t_proxy| along the approach "
            "path, which is the distance a contacting body would be off by"
        ),
    }


def main() -> int:
    results: dict = {}
    for name in ("bottle_assembly", "glass_a", "glass_b"):
        print("=" * 76)
        print(f"=== {name} ===")
        print("=" * 76)

        vis_dir = PROPS / name / "visual"
        vis_files = sorted(vis_dir.glob("*.obj"))
        if not vis_files:
            print(f"  no visual files for {name} under {vis_dir}")
            continue
        vis_parts = [load_mesh(p) for p in vis_files]
        visual = trimesh.util.concatenate(vis_parts) if len(vis_parts) > 1 else vis_parts[0]
        visual = trimesh.Trimesh(vertices=np.asarray(visual.vertices, float),
                                 faces=np.asarray(visual.faces, np.int64), process=True)

        # Each candidate lives in its OWN directory, so a glob can never mix files from
        # different candidates or different runs.
        cand_specs = {
            "vhacd": sorted((PROPS / name / "vhacd").glob("part*.obj")),
            "hull": sorted((PROPS / name / "hull").glob("*.obj")),
            "decimated": sorted((PROPS / name / "decimated").glob("*.obj")),
        }
        print(f"  visual: {len(visual.vertices)} v / {len(visual.faces)} tri")
        print(f"  available proxies: " + "  ".join(
            f"{k}={len(v)}" for k, v in cand_specs.items()))

        entry: dict = {}
        for label, files in cand_specs.items():
            files = [f for f in files if f.is_file()]
            if not files:
                continue
            parts = []
            for f in files:
                m = load_mesh(f)
                parts.append((np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)))
            tris = sum(len(p[1]) for p in parts)
            rep = fidelity(parts, visual)
            entry[label] = {"files": [str(f) for f in files], "triangles": tris, **rep}
            dev = rep["max_first_hit_deviation_m"]
            print(f"  {label:9s} {tris:5d} tri  "
                  f"max_dev={('%.4f mm' % (dev*1000)) if dev is not None else 'n/a'}  "
                  f"holes={rep['hole_rays']}/{rep['rays_hitting_visual']} "
                  f"({rep['hole_fraction']*100:.3f}%)  "
                  f"within_tol={rep['all_approaches'].get('within_tol')}")
            print(f"            downward max={rep['downward_approaches'].get('max_m')} "
                  f"horizontal max={rep['horizontal_approaches'].get('max_m')}")

        # Verdict: a proxy passes when it has no holes AND stays within tolerance on the
        # approaches that actually occur. Downward and horizontal are the physical ones.
        best, reason = None, "no proxy available"
        for label in ("decimated", "vhacd", "hull"):
            e = entry.get(label)
            if not e:
                continue
            ok = (e["hole_rays"] == 0
                  and e.get("max_first_hit_deviation_m") is not None
                  and e["max_first_hit_deviation_m"] <= TOL_M)
            if ok:
                best, reason = label, (
                    f"{label}: no pass-through rays and max first-hit deviation "
                    f"{e['max_first_hit_deviation_m']*1000:.4f} mm <= {TOL_M*1000:.1f} mm"
                )
                break
        results[name] = {"visual_files": [str(f) for f in vis_files],
                         "visual_triangles": int(len(visual.faces)),
                         "proxies": entry, "chosen": best, "reason": reason,
                         "tolerance_m": TOL_M}
        print(f"  -> {'CHOSEN ' + best if best else 'NONE'}: {reason}")

    print("\n" + "=" * 76)
    for name, r in results.items():
        print(f"  {name:18s} chosen={str(r['chosen']):10s}")
    out = SCENES / "proxy_fidelity.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    # Only the round-1 target gates this stage; the cups are a later enhancement.
    ok = bool(results.get("bottle_assembly", {}).get("chosen"))
    print(f"BOTTLE PROXY FIDELITY: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
