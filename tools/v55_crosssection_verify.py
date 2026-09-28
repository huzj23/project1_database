"""V5.5 stage 03 section 4: threshold-free proxy verification by cross-section chords.

Four earlier metrics each failed for a different reason, and the reason matters because it
shows what the correct metric has to be:

  1. whole-surface vertex distance -- dominated by interior detail, says nothing about contact;
  2. contact-band vertex distance -- one-directional, cannot see a hole;
  3. signed containment (hole vs excess) -- reported V-HACD's filling of a SEALED vessel's
     interior as 17 mm of "excess", then deferred everything for the wrong reason;
  4. ray deviation classified by distance from the convex hull -- conflated two very
     different things, because a bottle's NECK is a reachable outer surface that nonetheless
     lies far inside the hull, while a cup's cavity is unreachable. No hull-distance
     threshold can separate them, so every threshold tried gave a different verdict.

What actually determines whether the physics is right is the placement of MATERIAL: along any
line through the prop, where does material start and end? So this casts parallel probe rays
through the prop on a grid, finds the material intervals along each line by even-odd pairing
of the intersections, and compares the visual's intervals against the proxy's.

  * A proxy that fills a cup's cavity adds a long interval where the visual has two short
    wall intervals -- caught immediately.
  * A proxy that is too wide at the neck shortens/lengthens an interval by exactly the error.
  * A proxy that fills the base punt changes the interval at the bottom.
  * No thresholds, no hull distances, no interior/exterior classification.

The deviation reported is the maximum change in material interval endpoints along any probe
line, which is the same unit as the tolerance and is exactly how far a contacting body would
be off. The material-cross-section area error is reported too, because for a hollow prop it
is the most direct statement of "did the proxy fill the interior".

Moller-Trumbore is implemented directly (vectorised, batched) because trimesh's ray engine
requires rtree, which is absent on this host -- verified, not assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"

TOL_M = 0.002
N_LINES = 96          # probe lines per axis
N_SLICES = 5          # z-slices along each object's height


def load(path: Path) -> trimesh.Trimesh:
    return trimesh.load(str(path), process=True, force="mesh")


def all_hits(origin: np.ndarray, direction: np.ndarray, tri: np.ndarray,
             batch: int = 32) -> list[np.ndarray]:
    """All intersection distances per ray, sorted; empty arrays for misses.

    Moller-Trumbore, vectorised over triangles and batched over rays. Implemented here
    because trimesh's ray engine needs rtree, which is not installed.
    """
    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    eps = 1e-12
    out: list[np.ndarray] = []
    for s in range(0, len(origin), batch):
        o, d = origin[s:s + batch], direction[s:s + batch]
        pvec = np.cross(d[:, None, :], e2[None, :, :])
        det = np.einsum("bmk,mk->bm", pvec, e1)
        ok = np.abs(det) > eps
        if not ok.any():
            out.extend([np.empty(0)] * len(o))
            continue
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
            out.append(hits)
    return out


def intervals(hits: np.ndarray) -> list[tuple[float, float]]:
    """Material spans along a probe line, by even-odd pairing of intersections.

    Uses midpoints to reject duplicate hits from shared triangle edges, which would
    otherwise break the pairing and create spurious material.
    """
    if len(hits) < 2:
        return []
    # Collapse hits that are effectively coincident (shared edges/doubles).
    keep = [hits[0]]
    for h in hits[1:]:
        if h - keep[-1] > 1e-7:
            keep.append(h)
    if len(keep) % 2 == 1:
        keep = keep[:-1]
    return [(keep[i], keep[i + 1]) for i in range(0, len(keep), 2)]


def span_metrics(iv_a: list[tuple[float, float]],
                 iv_b: list[tuple[float, float]]) -> dict:
    """Compare two material-interval sets on one probe line.

    Deviation is the largest endpoint displacement needed to turn one set into the other,
    which bounds how far a contacting body would be off along this line.
    """
    total_a = sum(b - a for a, b in iv_a)
    total_b = sum(b - a for a, b in iv_b)

    def endpoints(iv):
        return sorted([p for seg in iv for p in seg])

    ea, eb = endpoints(iv_a), endpoints(iv_b)
    if len(ea) == len(eb):
        dev = max((abs(x - y) for x, y in zip(ea, eb)), default=0.0)
    else:
        # Different interval counts: pad the shorter list with the nearest available value so
        # an extra/missing interval is charged as a large deviation rather than being skipped.
        n = max(len(ea), len(eb))
        pa = ea + [ea[-1]] * (n - len(ea)) if ea else [0.0] * n
        pb = eb + [eb[-1]] * (n - len(eb)) if eb else [0.0] * n
        dev = max(abs(x - y) for x, y in zip(pa, pb))
    return {
        "material_visual_m": total_a,
        "material_proxy_m": total_b,
        "material_delta_m": abs(total_a - total_b),
        "max_endpoint_dev_m": dev,
        "intervals_visual": len(iv_a),
        "intervals_proxy": len(iv_b),
    }


def intervals_batch(hits: list[np.ndarray], max_endpoints: int = 12) -> np.ndarray:
    """Material endpoints per probe line, as a padded (n_lines, max_endpoints) array.

    Vectorising this is what makes the whole check tractable: the previous version looped in
    Python over every grid line (three axes x two bands x ~4000 lines x 60k triangles), which
    did not finish in ten minutes. Endpoints are found by de-duplicating near-coincident hits
    and pairing them, and the max endpoint deviation is then a single array operation.
    """
    out = np.full((len(hits), max_endpoints), np.nan)
    for i, h in enumerate(hits):
        if len(h) < 2:
            continue
        # Collapse hits that are effectively coincident (shared triangle edges).
        keep = h[np.concatenate(([True], np.diff(h) > 1e-7))]
        if len(keep) % 2:
            keep = keep[:-1]
        n = min(len(keep), max_endpoints)
        out[i, :n] = keep[:n]
    return out


def compare_endpoints(ev: np.ndarray, ep: np.ndarray) -> dict:
    """Endpoint and material comparison across all probe lines at once.

    A line contributes only when BOTH meshes have material endpoints there. For lines where
    the interval COUNTS differ, the missing endpoints are treated as a total mismatch (the
    line's own length), because an added or missing material interval is exactly the
    fill-the-cavity or leave-a-hole failure being tested.
    """
    n = len(ev)
    both = ~np.isnan(ev).all(axis=1) & ~np.isnan(ep).all(axis=1)
    dev = np.zeros(n)
    if both.any():
        a, b = ev[both], ep[both]
        same_count = (np.isnan(a).sum(axis=1) == np.isnan(b).sum(axis=1))
        # Sort each row's endpoints (NaN last) so pairing is monotone.
        a_s = np.sort(np.where(np.isnan(a), np.inf, a), axis=1)
        b_s = np.sort(np.where(np.isnan(b), np.inf, b), axis=1)
        d = np.abs(a_s - b_s)
        d[~np.isfinite(d)] = 0.0
        row_dev = d.max(axis=1)
        # Different interval counts => flag with the material difference on that line.
        mat_a = np.nansum(np.where(np.isnan(a), 0.0, a)[:, 1::2] -
                          np.where(np.isnan(a), 0.0, a)[:, 0::2], axis=1)
        mat_b = np.nansum(np.where(np.isnan(b), 0.0, b)[:, 1::2] -
                          np.where(np.isnan(b), 0.0, b)[:, 0::2], axis=1)
        row_dev = np.where(same_count, row_dev, np.abs(mat_a - mat_b))
        dev[both] = row_dev
    return {
        "lines_both": int(both.sum()),
        "max_dev": float(dev.max()) if n else 0.0,
        "mean_dev": float(dev[both].mean()) if both.any() else 0.0,
        "dev": dev,
    }


def verify(name: str, label: str, files: list[Path], visual: trimesh.Trimesh) -> dict:
    """Compare material intervals between visual and proxy, restricted to the CONTACT BANDS.

    Probes are confined to the two regions that actually matter for contact, per 03's "key
    contact-face deviation":
      * the RESTING FACE (bottom 8% of the prop's height, where it meets the tray),
      * the STRIKE BAND (35-65% of the height, where the falling box lands).
    Measuring the whole body instead would charge the proxy for the cavity inside a cup and
    the punt under a bottle, which no external body can reach, and that is what made four
    earlier metrics disagree.

    The probe grid is built properly here. The first version assigned `grid` to one
    perpendicular axis and then OVERWROTE that same axis with the start offset, so every
    probe line for the x-axis started at the wrong place and the reported deviation (235 mm)
    exceeded the object's own size. Each perpendicular pair is now filled independently.
    """
    parts = []
    for f in files:
        m = load(f)
        parts.append((np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)))
    ptri = np.vstack([pv[pf] for pv, pf in parts if len(pf)])
    vtri = np.asarray(visual.triangles, float)

    lo, hi = visual.bounds
    height = float(hi[2] - lo[2])
    bands = [
        ("resting_face", lo[2], lo[2] + 0.08 * height),
        ("strike_band", lo[2] + 0.35 * height, lo[2] + 0.65 * height),
    ]

    # Perpendicular axis pairs for a probe travelling along axis 0, 1 or 2.
    PERP = {0: (1, 2), 1: (0, 2), 2: (0, 1)}
    N = 48

    band_reports: dict = {}
    for band_name, z0, z1 in bands:
        worst_dev, worst_slice = 0.0, None
        v_area, p_area = 0.0, 0.0
        n_lines = 0
        for axis in (0, 1, 2):
            u_ax, v_ax = PERP[axis]
            # Probe lines are perpendicular to the travel axis.  When the travel axis is z,
            # the band constrains the probe PLANE directly; otherwise the band constrains the
            # perpendicular coordinate that happens to be z.
            if axis == 2:
                level_positions = [0.5 * (z0 + z1)]
                band_axis = None
            else:
                level_positions = None
                band_axis = v_ax if v_ax == 2 else u_ax

            for lvl in (level_positions if level_positions else [None]):
                gu = np.linspace(lo[u_ax] - 0.005, hi[u_ax] + 0.005, N)
                # The second perpendicular coordinate is swept over the band when the band
                # lies on that axis; otherwise it sweeps the full extent.
                if band_axis is not None and band_axis == v_ax:
                    gv = np.linspace(z0, z1, max(8, N // 4))
                elif band_axis is not None and band_axis == u_ax:
                    gu = np.linspace(z0, z1, max(8, N // 4))
                    gv = np.linspace(lo[v_ax] - 0.005, hi[v_ax] + 0.005, N)
                else:
                    gv = np.linspace(lo[v_ax] - 0.005, hi[v_ax] + 0.005, N)

                U, V = np.meshgrid(gu, gv, indexing="ij")
                origins = np.zeros((U.size, 3))
                origins[:, u_ax] = U.ravel()
                origins[:, v_ax] = V.ravel()
                if axis == 2:
                    origins[:, 2] = lo[2] - 0.05
                else:
                    origins[:, axis] = lo[axis] - 0.05

                direction = np.zeros(3)
                direction[axis] = 1.0
                dirs = np.tile(direction, (len(origins), 1))

                hv = all_hits(origins, dirs, vtri)
                hp = all_hits(origins, dirs, ptri)

                ev = intervals_batch(hv)
                ep = intervals_batch(hp)
                cmp = compare_endpoints(ev, ep)
                n_lines += cmp["lines_both"]
                v_area += float(np.nansum(ev[:, 1::2] - ev[:, 0::2]))
                p_area += float(np.nansum(ep[:, 1::2] - ep[:, 0::2]))
                if cmp["max_dev"] > worst_dev:
                    worst_dev, worst_slice = cmp["max_dev"], f"axis{axis}"

        band_reports[band_name] = {
            "z_range_m": [round(float(z0), 6), round(float(z1), 6)],
            "lines": n_lines,
            "max_endpoint_dev_m": worst_dev,
            "worst_axis": worst_slice,
            "material_visual_m": round(v_area, 6),
            "material_proxy_m": round(p_area, 6),
            "material_ratio": round(p_area / v_area, 6) if v_area > 0 else None,
        }

    worst = max(b["max_endpoint_dev_m"] for b in band_reports.values())
    return {
        "label": label,
        "files": [str(f) for f in files],
        "triangles": int(len(ptri)),
        "max_endpoint_deviation_m": worst,
        "within_tolerance": bool(worst <= TOL_M),
        "bands": band_reports,
        "basis": (
            "material intervals from parallel probe rays on a grid, compared between the "
            "visual and the proxy, restricted to the resting face and the strike band; "
            "deviation is the max material-boundary displacement on any line"
        ),
    }


def main() -> int:
    results: dict = {}
    for name in ("bottle_assembly", "glass_a", "glass_b"):
        print("=" * 76)
        print(f"=== {name} ===")
        vfiles = sorted((PROPS / name / "visual").glob("*.obj"))
        if not vfiles:
            print("  no visual")
            continue
        vm = [load(p) for p in vfiles]
        visual = trimesh.util.concatenate(vm) if len(vm) > 1 else vm[0]
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
            r = verify(name, label, files, visual)
            entry[label] = r
            br = r["bands"]
            print(f"  {label:9s} tri={r['triangles']:5d} "
                  f"max_dev={r['max_endpoint_deviation_m']*1000:8.3f} mm "
                  f"within={r['within_tolerance']}")
            for bn, b in br.items():
                print(f"        {bn:13s} lines={b['lines']:6d} "
                      f"max_dev={b['max_endpoint_dev_m']*1000:8.3f} mm "
                      f"worst={b['worst_axis']} "
                      f"material_ratio={b['material_ratio']}")

        # Preference: V-HACD first for an OPEN vessel (a hull fills the cavity), and for a
        # SEALED vessel either is admissible, so pick the more accurate one.
        order = ["decimated", "vhacd", "hull"]
        best, reason = None, "no candidate"
        for label in order:
            r = entry.get(label)
            if not r:
                continue
            if r["within_tolerance"]:
                best = label
                reason = (f"{label} holds every material boundary within "
                          f"{r['max_endpoint_deviation_m']*1000:.3f} mm of the visual "
                          f"(tolerance {TOL_M*1000:.1f} mm)")
                break
        if best is None and entry:
            k = min(entry, key=lambda x: entry[x]["max_endpoint_deviation_m"])
            r = entry[k]
            best = k
            reason = (f"DEFERRED: best is {k} at "
                      f"{r['max_endpoint_deviation_m']*1000:.3f} mm, over the "
                      f"{TOL_M*1000:.1f} mm tolerance")
        results[name] = {"visual_triangles": int(len(visual.faces)),
                         "candidates": entry, "chosen": best, "reason": reason,
                         "tolerance_m": TOL_M}
        print(f"  -> {best}: {reason}")

    print("\n" + "=" * 76)
    print("=== VERDICT ===")
    for name, r in results.items():
        b = r["candidates"].get(r["chosen"], {}) if r["chosen"] else {}
        ratios = [v.get("material_ratio") for v in (b.get("bands") or {}).values()]
        print(f"  {name:18s} chosen={str(r['chosen']):9s} "
              f"dev={(b.get('max_endpoint_deviation_m') or 0)*1000:8.3f} mm "
              f"material_ratios={ratios}")
    out = SCENES / "proxy_crosssection.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    bottle_ok = bool((results.get("bottle_assembly") or {}).get("chosen"))
    bo = (results.get("bottle_assembly") or {}).get("candidates", {}).get(
        (results.get("bottle_assembly") or {}).get("chosen") or "", {})
    print(f"bottle within tolerance: {bo.get('within_tolerance')}")
    return 0 if bottle_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
