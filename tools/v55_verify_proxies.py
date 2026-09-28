"""V5.5 stage 03 section 4: the FINAL, consolidated collision-proxy verification and choice.

Five earlier metrics are recorded here because each failed for a reason that determines what
the correct metric must be:

  1. whole-surface vertex distance -- dominated by interior detail, unrelated to contact;
  2. contact-band vertex distance -- one-directional, cannot see a hole;
  3. signed containment -- charged V-HACD's filling of a SEALED vessel's interior as 17 mm of
     error and deferred everything for the wrong reason;
  4. ray deviation classified by convex-hull distance -- conflated a bottle's NECK (outer,
     reachable, but far inside the hull) with a cup's cavity (unreachable), so every threshold
     gave a different verdict;
  5. cross-section material intervals -- correct about material placement, but it charges the
     interior of a sealed body, which no external body can reach.

What this file settles on is the union of the things that are each individually defensible,
with every number reported so the reader can check the reasoning:

  A. DIMENSION ERROR    -- proxy AABB vs visual AABB, relative, per axis (03: <= 1%).
  B. PASS-THROUGH       -- rays from outside that hit the visual but not the proxy. Any such
                           ray is a HOLE a struck body could pass through. Must be zero.
  C. FIRST-HIT FIDELITY -- |t_visual - t_proxy| along the approach, the distance a contacting
                           body is actually off by. Reported as the max over all rays, as the
                           max over FRONT-FACING hits (the surface an external body meets), and
                           per approach class (downward / horizontal / upward).
  D. INTERIOR FILLING   -- the contact-band material ratio, reported as DISCLOSURE. Filling a
                           sealed body's cavity is invisible to contact; filling an OPEN
                           vessel's cavity is what 03 section 4 forbids. This is why the choice
                           below depends on whether the prop is SEALED.

The choice follows 03 section 4 directly:
  * a SEALED vessel may use one closed convex proxy, so the candidate with the best accuracy
    is chosen;
  * an OPEN vessel must not be filled, so a hull is DISALLOWED for it and a decomposition is
    required;
  * 05 section 4 permits the round-1 shot to proceed on the bottle alone, so a cup that
    cannot meet the bound is DEFERRED with its number rather than forced.

Moller-Trumbore is implemented directly and vectorised because trimesh's ray engine and
`contains` both require rtree, which is absent on this host (verified, not assumed).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"

TOL_M = 0.002          # min(2 mm, thinnest_overall*5%) -- both props exceed 40 mm, so capped
DIM_TOL = 0.01         # 03: dimension error <= 1%
N_RAYS = 8192
BATCH = 64

PROPS_SPEC = {
    "bottle_assembly": {"is_sealed": True, "n_members": 2},
    "glass_a": {"is_sealed": False, "n_members": 1},
    "glass_b": {"is_sealed": False, "n_members": 1},
}


def load(path: Path) -> trimesh.Trimesh:
    return trimesh.load(str(path), process=True, force="mesh")


def compound(files: list[Path]) -> trimesh.Trimesh:
    return trimesh.util.concatenate([load(f) for f in files])


def first_hit(origin: np.ndarray, direction: np.ndarray, tri: np.ndarray,
              want_tri: bool = False):
    """Vectorised Moller-Trumbore first hit. NaN where a ray misses."""
    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    out = np.full(len(origin), np.nan)
    out_i = np.full(len(origin), -1, dtype=np.int64)
    eps = 1e-12
    for s in range(0, len(origin), BATCH):
        o, d = origin[s:s + BATCH], direction[s:s + BATCH]
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
        found = np.isfinite(best)
        out[s:s + BATCH] = np.where(found, best, np.nan)
        out_i[s:s + BATCH] = np.where(found, tw.argmin(axis=1), -1)
    return (out, out_i) if want_tri else out


def face_normals(tri: np.ndarray) -> np.ndarray:
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1.0
    return n / ln


def material_intervals(origin: np.ndarray, direction: np.ndarray, tri: np.ndarray,
                       max_ep: int = 16) -> np.ndarray:
    """Material endpoint distances per ray, by even-odd pairing, padded to `max_ep`."""
    # All hits are needed, so this loops in batches collecting them.
    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    eps = 1e-12
    out = np.full((len(origin), max_ep), np.nan)
    for s in range(0, len(origin), BATCH):
        o, d = origin[s:s + BATCH], direction[s:s + BATCH]
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
        for i in range(len(o)):
            hits = np.sort(t[i][ok[i]])
            if len(hits) < 2:
                continue
            keep = hits[np.concatenate(([True], np.diff(hits) > 1e-7))]
            if len(keep) % 2:
                keep = keep[:-1]
            n = min(len(keep), max_ep)
            out[s + i, :n] = keep[:n]
    return out


def material_length(ep: np.ndarray) -> np.ndarray:
    a = np.where(np.isnan(ep), 0.0, ep)
    return np.nansum(a[:, 1::2] - a[:, 0::2], axis=1)


def evaluate(name: str, label: str, files: list[Path], visual: trimesh.Trimesh,
             n_rays: int = N_RAYS, seed: int = 55) -> dict:
    vtri = np.asarray(visual.triangles, float)
    vn = face_normals(vtri)
    cf = compound(files)
    ptri = np.asarray(cf.triangles, float)

    # A. dimension error
    vlo, vhi = visual.bounds
    plo, phi = cf.bounds
    vdim = vhi - vlo
    pdim = phi - plo
    rel = np.abs(pdim - vdim) / np.where(vdim > 0, vdim, 1.0)

    # B/C. rays from outside, aimed inward
    lo, hi = vlo, vhi
    centre = (lo + hi) / 2.0
    start_r = float(np.linalg.norm(hi - lo) / 2.0) * 3.0
    rng = np.random.default_rng(seed)
    dirs = rng.normal(size=(n_rays, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    origins = centre[None, :] - dirs * start_r
    din = centre[None, :] - origins
    din /= np.linalg.norm(din, axis=1, keepdims=True)

    t_vis, i_vis = first_hit(origins, din, vtri, want_tri=True)
    t_prox = first_hit(origins, din, ptri)

    hit_v = np.isfinite(t_vis)
    hit_p = np.isfinite(t_prox)
    holes = hit_v & ~hit_p
    both = hit_v & hit_p
    dev = np.abs(t_vis - t_prox)

    # Front-facing = the surface an external body meets. A hit is front-facing when the
    # triangle's outward normal opposes the ray direction.
    valid = i_vis >= 0
    ndot = np.zeros(len(t_vis))
    ndot[valid] = np.einsum("ij,ij->i", vn[i_vis[valid]], -din[valid])
    front = both & (ndot > 0.0)

    cos_down = -din[:, 2]

    def mx(mask):
        return float(dev[mask].max()) if mask.any() else None

    res = {
        "label": label,
        "files": [str(f) for f in files],
        "proxy_triangles": int(len(ptri)),
        "dimension_error_rel": [round(float(x), 9) for x in rel],
        "dimension_error_max_rel": round(float(rel.max()), 9),
        "dimension_within_1pct": bool(rel.max() <= DIM_TOL),
        "proxy_aabb_min": [round(float(x), 9) for x in plo],
        "proxy_aabb_max": [round(float(x), 9) for x in phi],
        "visual_aabb_min": [round(float(x), 9) for x in vlo],
        "visual_aabb_max": [round(float(x), 9) for x in vhi],
        "rays_cast": int(n_rays),
        "rays_hitting_visual": int(hit_v.sum()),
        "hole_rays": int(holes.sum()),
        "has_no_holes": bool(holes.sum() == 0),
        "max_first_hit_dev_m": mx(both),
        "max_first_hit_dev_front_facing_m": mx(front),
        "max_dev_downward_m": mx(both & (cos_down > 0.9)),
        "max_dev_horizontal_m": mx(both & (np.abs(cos_down) < 0.15)),
        "max_dev_upward_m": mx(both & (cos_down < -0.9)),
        "front_facing_rays": int(front.sum()),
        "within_tolerance_front_facing": bool(
            mx(front) is not None and mx(front) <= TOL_M),
        "tolerance_m": TOL_M,
    }

    # D. interior filling, disclosed: material ratio inside the two contact bands.
    # The bands are z-intervals, so only probes that TRAVEL along z can resolve them: a
    # horizontal probe line travelling along x or y crosses the band's z-range at a single
    # height and cannot say anything about material within the band. The first version
    # included axis 0 probes here, which mixed full-height material into a band statistic.
    height = float(hi[2] - lo[2])
    bands = {"resting_face": (lo[2], lo[2] + 0.08 * height),
             "strike_band": (lo[2] + 0.35 * height, lo[2] + 0.65 * height)}
    band_out = {}
    for bn, (z0, z1) in bands.items():
        vmat = pmat = 0.0
        lines = 0
        # ONE probe plane per band on a 16x16 grid. The first version used two planes at
        # 48x48 and did not finish in ten minutes: extracting the hits for a single ray costs
        # a pass over every triangle, so the cost is rays x triangles and has to be kept
        # small. This statistic is a DISCLOSURE of interior filling, not a tolerance check --
        # the tolerance is decided by the front-facing ray test above -- so a modest grid is
        # sufficient and the sample size is recorded with it.
        for frac in (0.5,):
            lines += 1
            g = np.linspace(lo[0], hi[0], 16)
            h = np.linspace(lo[1], hi[1], 16)
            U, V = np.meshgrid(g, h, indexing="ij")
            o = np.zeros((U.size, 3))
            o[:, 0] = U.ravel()
            o[:, 1] = V.ravel()
            o[:, 2] = lo[2] - 0.02              # start below, travel straight up
            d = np.tile(np.array([0.0, 0.0, 1.0]), (len(o), 1))
            ev = material_intervals(o, d, vtri)
            ep = material_intervals(o, d, ptri)

            # Restrict to material inside the band, so the statistic is about the band only.
            def in_band(ep_arr):
                a = np.where(np.isnan(ep_arr), 0.0, ep_arr)
                lo_e = np.maximum(a[:, 0::2], z0 - (lo[2] - 0.02))
                hi_e = np.minimum(a[:, 1::2], z1 - (lo[2] - 0.02))
                return np.clip(hi_e - lo_e, 0.0, None).sum()
            vmat += float(in_band(ev))
            pmat += float(in_band(ep))
        band_out[bn] = {
            "material_visual_m": round(vmat, 6),
            "material_proxy_m": round(pmat, 6),
            "material_ratio": round(pmat / vmat, 6) if vmat > 0 else None,
            "probe_planes": lines,
            "grid": 16,
        }
    res["contact_band_material"] = band_out

    # 03 section 4 decision rules
    sealed = PROPS_SPEC[name]["is_sealed"]
    reasons = []
    ok = True
    if not res["has_no_holes"]:
        ok = False
        reasons.append(f"{res['hole_rays']} pass-through rays (a hole)")
    if not res["dimension_within_1pct"]:
        ok = False
        reasons.append(f"dimension error {res['dimension_error_max_rel']*100:.3f}% > 1%")
    if not res["within_tolerance_front_facing"]:
        ok = False
        ff = res["max_first_hit_dev_front_facing_m"]
        reasons.append(
            f"front-facing deviation {('%.4f mm' % (ff*1000)) if ff is not None else 'n/a'}"
            f" > {TOL_M*1000:.1f} mm")
    res["meets_spec"] = bool(ok)
    res["fail_reasons"] = reasons
    res["is_sealed"] = sealed
    return res


def main() -> int:
    results: dict = {}
    for name in PROPS_SPEC:
        print("=" * 78)
        print(f"=== {name}  (sealed={PROPS_SPEC[name]['is_sealed']}) ===")
        print("=" * 78)
        vfiles = sorted((PROPS / name / "visual").glob("*.obj"))
        if not vfiles:
            print("  no visual files; skipping")
            continue
        visual = compound(vfiles)
        visual = trimesh.Trimesh(vertices=np.asarray(visual.vertices, float),
                                 faces=np.asarray(visual.faces, np.int64), process=True)

        cands = {
            "vhacd": sorted((PROPS / name / "vhacd").glob("part*.obj")),
            "hull": sorted((PROPS / name / "hull").glob("*.obj")),
            "decimated": sorted((PROPS / name / "decimated").glob("*.obj")),
        }
        entry = {}
        for label, files in cands.items():
            files = [f for f in files if f.is_file()]
            if not files:
                continue
            r = evaluate(name, label, files, visual)
            entry[label] = r
            def mm(v):
                return f"{v*1000:8.3f}" if v is not None else "     n/a"
            print(f"  {label:9s} tri={r['proxy_triangles']:5d} "
                  f"dim_err={r['dimension_error_max_rel']*100:7.4f}% "
                  f"holes={r['hole_rays']:4d} "
                  f"front_max={mm(r['max_first_hit_dev_front_facing_m'])} mm "
                  f"all_max={mm(r['max_first_hit_dev_m'])} mm")
            print(f"            down={mm(r['max_dev_downward_m'])} "
                  f"horiz={mm(r['max_dev_horizontal_m'])} "
                  f"up={mm(r['max_dev_upward_m'])} mm  "
                  f"material_ratio="
                  f"{ {k: v['material_ratio'] for k, v in r['contact_band_material'].items()} }")
            if r["fail_reasons"]:
                for why in r["fail_reasons"]:
                    print(f"            FAIL: {why}")

        # Choice per 03 section 4.
        sealed = PROPS_SPEC[name]["is_sealed"]
        allowed = ["decimated", "vhacd"] + (["hull"] if sealed else [])
        passing = [k for k in allowed if entry.get(k, {}).get("meets_spec")]
        if passing:
            # Among those that pass, take the one with the smallest worst-case deviation;
            # prefer a decomposition when it is equally accurate, because it preserves the
            # interior even when a hull would be permitted.
            def key(k):
                r = entry[k]
                return (r["max_first_hit_dev_front_facing_m"] or 0.0,
                        0 if k != "hull" else 1)
            chosen = min(passing, key=key)
            reason = (f"{chosen} passes every bound: dimensions within "
                      f"{entry[chosen]['dimension_error_max_rel']*100:.4f}%, no holes, "
                      f"front-facing deviation "
                      f"{entry[chosen]['max_first_hit_dev_front_facing_m']*1000:.4f} mm <= "
                      f"{TOL_M*1000:.1f} mm"
                      + ("" if sealed else "; a hull was not eligible because the prop is OPEN"))
        else:
            # Nothing passed. Report the closest and defer per 05 section 4.
            elig = {k: entry[k] for k in allowed if k in entry}
            chosen = min(elig, key=lambda k: (
                elig[k]["max_first_hit_dev_front_facing_m"] or 9e9)) if elig else None
            if chosen:
                r = elig[chosen]
                ff = r["max_first_hit_dev_front_facing_m"]
                reason = (
                    f"DEFERRED: best eligible is {chosen} with front-facing deviation "
                    f"{('%.4f mm' % (ff*1000)) if ff is not None else 'n/a'} against "
                    f"{TOL_M*1000:.1f} mm; 05 section 4 permits the round-1 shot to proceed "
                    f"on the bottle alone. Reasons: {'; '.join(r['fail_reasons']) or 'none'}")
            else:
                reason = "no eligible candidate"
        results[name] = {"visual_triangles": int(len(visual.faces)),
                         "candidates": entry, "chosen": chosen, "reason": reason,
                         "is_sealed": sealed}
        print(f"  -> CHOSEN: {chosen}")
        print(f"     {reason}")

    out = SCENES / "proxy_verification.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n" + "=" * 78)
    print("=== VERDICT ===")
    for name, r in results.items():
        b = r["candidates"].get(r["chosen"], {}) if r["chosen"] else {}
        print(f"  {name:18s} sealed={str(r['is_sealed']):5s} chosen={str(r['chosen']):9s} "
              f"meets={b.get('meets_spec')} "
              f"front_max={(b.get('max_first_hit_dev_front_facing_m') or 0)*1000:7.3f} mm "
              f"holes={b.get('hole_rays')} "
              f"dim_err={(b.get('dimension_error_max_rel') or 0)*100:6.4f}%")
    print(f"\nwritten: {out}")

    bottle = results.get("bottle_assembly", {})
    bc = bottle.get("candidates", {}).get(bottle.get("chosen") or "", {})
    stage_ok = bool(bc.get("meets_spec"))
    print(f"\nSTAGE 03 SECTION 4 (round-1 target bottle): "
          f"{'PASS' if stage_ok else 'FAIL'}")
    return 0 if stage_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
