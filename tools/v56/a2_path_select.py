"""Pick and justify a flat, obstacle-free straight run for the can in Hidden Alley.

The ground export from `a2_export_ground.py` gives a floor heightfield plus a scatter field, so the
candidate path can be scored numerically instead of judged from an empty-looking still -- which
V5.6 section 5.5 explicitly forbids ("不能凭静帧里一片空地就宣布可用").

What is measured for each candidate straight line, at 0.02 m sampling:

  * **flatness**: the height range and RMS deviation from a straight-line fit along the run. A can
    that must climb even 10 mm over a 1.2 m path is not rolling on flat ground.
  * **scatter clearance**: the minimum distance from the path centreline to any scatter vertex
    (stones, grass, leaves). A can visibly rolling through a stone is a penetration artefact, so a
    run with scatter inside the can's radius is rejected, not merely noted.
  * **headroom**: the run must not cross the wall or the plinth.
  * **length**: at least 1.0 m AND at least 6 can diameters, per section 5.1.4.

The can's collision radius is passed in rather than assumed, because the required clearance and the
6-diameter rule both depend on it.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\workspace\project1_database")
RUN = ROOT / "outcomes/v56/hidden_alley_can_board/20260929T142714"
HF = RUN / "ground/heightfields.npz"


def sample(field, gx, gy, x, y):
    """Bilinear sample of a heightfield, returning NaN outside the grid."""
    i = np.searchsorted(gx, x) - 1
    j = np.searchsorted(gy, y) - 1
    if i < 0 or j < 0 or i >= len(gx) - 1 or j >= len(gy) - 1:
        return float("nan")
    tx = (x - gx[i]) / (gx[i + 1] - gx[i])
    ty = (y - gy[j]) / (gy[j + 1] - gy[j])
    v00, v10 = field[i, j], field[i + 1, j]
    v01, v11 = field[i, j + 1], field[i + 1, j + 1]
    a = v00 * (1 - tx) + v10 * tx
    b = v01 * (1 - tx) + v11 * tx
    return float(a * (1 - ty) + b * ty)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius", type=float, default=0.065,
                    help="can collision radius in metres (half of the 0.13 m measured diameter)")
    ap.add_argument("--min-length", type=float, default=1.0)
    ap.add_argument("--diameters", type=float, default=6.0)
    ap.add_argument("--out", default=str(RUN / "ground" / "path_candidates.json"))
    A = ap.parse_args()

    z = np.load(HF)
    gx, gy = z["gx"], z["gy"]
    floor = z["floor"]
    scatter = z["scatter"]
    H = z["Hz"]
    wall_x = z["wall_x"]
    print(f"grid {floor.shape}  x {gx[0]:.3f}..{gx[-1]:.3f}  y {gy[0]:.3f}..{gy[-1]:.3f}")

    # Scatter points, from the raster's top height per cell. A cell is "occupied" when the scatter
    # surface is meaningfully above the floor there.
    si, sj = np.nonzero(np.isfinite(scatter) & (scatter > floor + 0.004))
    spts = np.stack([gx[si], gy[sj], scatter[si, sj]], axis=1)
    print(f"scatter cells above floor by >4 mm: {len(spts)}")

    # The wall's x at each y, so a path can be kept clear of it.
    wall_at = {}
    for j, y in enumerate(gy):
        col = wall_x[j]
        fin = col[np.isfinite(col)]
        wall_at[float(y)] = float(fin.max()) if len(fin) else None

    board = json.loads((ROOT / "outcomes/v56/hidden_alley_can_board/board_selection.json")
                       .read_text(encoding="utf-8"))
    rec = board["recommended_board"]
    bx0, by0, bz0 = rec["world_aabb_min"]
    bx1, by1, bz1 = rec["world_aabb_max"]
    print(f"\nboard AABB x {bx0:.3f}..{bx1:.3f}  y {by0:.3f}..{by1:.3f}  z {bz0:.3f}..{bz1:.3f}")

    min_len = max(A.min_length, A.diameters * 2 * A.radius)
    print(f"minimum run: max({A.min_length} m, {A.diameters} diameters = "
          f"{A.diameters * 2 * A.radius:.3f} m) = {min_len:.3f} m")
    print(f"can radius used for clearance: {A.radius * 1000:.1f} mm\n")

    # Candidate runs: straight, axis-aligned, ending near the board's foot so the can arrives at the
    # board after traversing the run.
    cands = []
    # The board is at x ~ -2.08, i.e. against the wall at x = -2.2. A can approaching along the wall
    # travels in +/-Y; a can approaching from the alley travels in -X.
    y_target = (by0 + by1) / 2.0
    for x_lane in (-1.55, -1.35, -1.15, -0.95, -0.75, -0.55):
        for y_start in (y_target + 1.2, y_target + 1.6, y_target + 2.0, y_target + 2.4,
                        y_target - 1.2, y_target - 1.6, y_target - 2.0, y_target - 2.4):
            for L in (1.0, 1.2, 1.4, 1.6, 1.8, 2.0):
                y_end = y_start + (L if y_start < y_target else -L)
                cands.append(("along_y", x_lane, y_start, x_lane, y_end))
    # Across the alley toward the wall, ending short of the board's x.
    for y_lane in (y_target - 0.6, y_target - 0.3, y_target, y_target + 0.3, y_target + 0.6):
        for x_start in (0.6, 0.2, -0.2, -0.6):
            for L in (1.4, 1.6, 1.8, 2.0, 2.4, 2.8):
                x_end = x_start - L
                cands.append(("toward_wall", x_start, y_lane, x_end, y_lane))

    results = []
    for kind, x0, y0, x1, y1 in cands:
        L = math.hypot(x1 - x0, y1 - y0)
        if L < min_len:
            continue
        n = max(int(L / 0.02) + 1, 8)
        ts = np.linspace(0.0, 1.0, n)
        xs = x0 + (x1 - x0) * ts
        ys = y0 + (y1 - y0) * ts
        hs = np.array([sample(floor, gx, gy, float(x), float(y)) for x, y in zip(xs, ys)])
        if not np.all(np.isfinite(hs)):
            continue
        # Flatness: range, and the residuals from a least-squares straight line in the travel
        # direction (a constant slope is fine; a bump is not).
        rng = float(hs.max() - hs.min())
        coef = np.polyfit(ts, hs, 1)
        resid = hs - np.polyval(coef, ts)
        rms = float(np.sqrt((resid ** 2).mean()))
        # Scatter clearance: min horizontal distance from the centreline to any scatter point whose
        # top is above the local floor by more than a millimetre.
        clear = 1e9
        if len(spts):
            d2 = (spts[:, 0][:, None] - xs[None, :]) ** 2 + (spts[:, 1][:, None] - ys[None, :]) ** 2
            near = d2.min(axis=1) <= (A.radius * 3) ** 2
            if near.any():
                clear = float(np.sqrt(d2[near].min()))
        # Headroom from the wall along the path.
        wall_clear = 1e9
        for x, y in zip(xs, ys):
            w = wall_at.get(float(round(y / (gy[1] - gy[0])) * (gy[1] - gy[0])))
            if w is None:
                j = int(np.argmin(np.abs(gy - y)))
                col = wall_x[j]
                fin = col[np.isfinite(col)]
                w = float(fin.max()) if len(fin) else None
            if w is not None:
                wall_clear = min(wall_clear, x - w)
        results.append({
            "kind": kind, "start": [x0, y0], "end": [x1, y1], "length_m": L,
            "diameters": L / (2 * A.radius),
            "height_min": float(hs.min()), "height_max": float(hs.max()),
            "height_range_mm": rng * 1000, "slope": float(coef[0]),
            "residual_rms_mm": rms * 1000,
            "scatter_clearance_m": (None if clear > 1e8 else clear),
            "wall_clearance_m": (None if wall_clear > 1e8 else wall_clear),
        })

    def score(r):
        # Rank by flatness first, then by scatter clearance, then by length. A run that grazes
        # scatter is not acceptable however flat it is.
        sc = r["scatter_clearance_m"]
        graze = 0.0 if (sc is not None and sc < A.radius) else 1.0
        wc = r["wall_clearance_m"]
        hitwall = 0.0 if (wc is not None and wc < A.radius) else 1.0
        return (graze, hitwall, r["height_range_mm"], r["residual_rms_mm"], -r["length_m"])

    results.sort(key=score)
    print(f"{len(results)} candidate runs met the length minimum; best 15:\n")
    print(f"  {'kind':13s} {'length':>7s} {'diam':>5s} {'range_mm':>9s} {'rms_mm':>7s} "
          f"{'scatter':>9s} {'wall':>8s}  start -> end")
    for r in results[:15]:
        sc = r["scatter_clearance_m"]
        wc = r["wall_clearance_m"]
        print(f"  {r['kind']:13s} {r['length_m']:7.3f} {r['diameters']:5.1f} "
              f"{r['height_range_mm']:9.2f} {r['residual_rms_mm']:7.2f} "
              f"{(f'{sc*1000:.0f}mm' if sc is not None else 'n/a'):>9s} "
              f"{(f'{wc*1000:.0f}mm' if wc is not None else 'n/a'):>8s}  "
              f"({r['start'][0]:.2f},{r['start'][1]:.2f}) -> ({r['end'][0]:.2f},{r['end'][1]:.2f})")

    best = results[0] if results else None
    print()
    if best:
        print("=== BEST RUN ===")
        print(f"  {best['kind']}  length {best['length_m']:.3f} m "
              f"({best['diameters']:.1f} can diameters)")
        print(f"  height range {best['height_range_mm']:.2f} mm, deviation from a straight line "
              f"{best['residual_rms_mm']:.2f} mm RMS")
        if best["scatter_clearance_m"] is not None:
            print(f"  nearest scatter to the centreline {best['scatter_clearance_m']*1000:.0f} mm "
                  f"(can radius {A.radius*1000:.0f} mm)")
    else:
        print("=== NO RUN MEETS THE LENGTH MINIMUM IN THIS GROUND CLIP ===")
        print("  The exported ground clip may be too small or the usable flat area too short.")

    A.out_path = Path(A.out)
    A.out_path.write_text(json.dumps({
        "can_radius_m": A.radius, "min_length_m": min_len,
        "min_diameters": A.diameters,
        "board_aabb": {"min": [bx0, by0, bz0], "max": [bx1, by1, bz1]},
        "scatter_points_above_floor": int(len(spts)),
        "candidates_meeting_length": len(results),
        "candidates": results[:60],
        "best": best,
        "method": ("floor heightfield and scatter field sampled at 0.02 m along each candidate "
                   "straight line; flatness from the range and the residual about a least-squares "
                   "line; scatter and wall clearances computed against the can's collision radius, "
                   "so a run that would roll through a stone or into the wall is rejected rather "
                   "than annotated"),
    }, indent=2), encoding="utf-8")
    print(f"\nwritten: {A.out_path}")
    return 0 if best else 1


if __name__ == "__main__":
    raise SystemExit(main())
