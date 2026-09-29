"""Can a can actually REACH the board? Evaluate approaches in the -X direction.

WHY THIS IS SEPARATE FROM `a2_path_select.py`
That script ranked runs by flatness first, and the flat ground in this alley runs along Y beside the
wall. But the board's slab is 1.461 m long along Y, 0.388 m tall, and only 0.0136 m thick along X, so
its thin edge faces +/-X: a can rolling along the flat +/-Y line passes the board's END rather than
striking it. The only approach that meets the board face-on is along -X, toward the wall.

So this answers the question that actually decides video A: **is there a long, flat -X run that
reaches the board's face?**

It also works out the plinth step, because that is the other half of the problem:
  * `Floor_main` top is z = -0.040
  * the plinth `base_tripple_01.003` top is z = +0.010, spanning x -2.2..-2.0
  * the board's foot rests at z = 0.0097, i.e. on the plinth top
So a can rolling on the floor must climb a 50 mm step onto the plinth before it can touch the board,
and whether a 130 mm-diameter can does that is a physics question this script only quantifies.

Writes `path_x_candidates.json`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\workspace\project1_database")
RUN = ROOT / "outcomes/v56/hidden_alley_can_board/20260929T142714"
HF = RUN / "ground/heightfields.npz"
OUT = RUN / "ground"

CAN_RADIUS = 0.065          # from the measured 0.12998 m collision diameter
FLOOR_Z = -0.040
PLINTH_TOP = 0.010
STEP_M = PLINTH_TOP - FLOOR_Z


def sample(field, gx, gy, x, y):
    i = np.searchsorted(gx, x) - 1
    j = np.searchsorted(gy, y) - 1
    if i < 0 or j < 0 or i >= len(gx) - 1 or j >= len(gy) - 1:
        return float("nan")
    tx = (x - gx[i]) / (gx[i + 1] - gx[i])
    ty = (y - gy[j]) / (gy[j + 1] - gy[j])
    a = field[i, j] * (1 - tx) + field[i + 1, j] * tx
    b = field[i, j + 1] * (1 - tx) + field[i + 1, j + 1] * tx
    return float(a * (1 - ty) + b * ty)


def main() -> int:
    z = np.load(HF)
    gx, gy, floor, scatter, wall_x = z["gx"], z["gy"], z["floor"], z["scatter"], z["wall_x"]
    board = json.loads((ROOT / "outcomes/v56/hidden_alley_can_board/board_selection.json")
                       .read_text(encoding="utf-8"))
    rec = board["recommended_board"]
    bx0, by0, _ = rec["world_aabb_min"]
    bx1, by1, _ = rec["world_aabb_max"]
    print("=" * 100)
    print("X-direction reach analysis  (the only approach that meets the board's face)")
    print(f"  board x {bx0:.4f}..{bx1:.4f}  y {by0:.4f}..{by1:.4f}")
    print(f"  board thickness along X = {bx1 - bx0:.4f} m -> its thin edge faces +/-X")
    print(f"  plinth top {PLINTH_TOP:+.3f} m vs floor top {FLOOR_Z:+.3f} m -> step {STEP_M * 1000:.0f} mm")
    print(f"  can radius {CAN_RADIUS * 1000:.0f} mm; a {STEP_M * 1000:.0f} mm step is "
          f"{STEP_M / CAN_RADIUS:.2f} x radius")

    si, sj = np.nonzero(np.isfinite(scatter) & (scatter > floor + 0.004))
    spts = np.stack([gx[si], gy[sj]], axis=1)
    print(f"  scatter cells above floor: {len(spts)}")

    # The board spans y 1.427..2.888. Runs aimed at its face must sit within that y band, near its
    # centre, and travel in -X ending at the board's x.
    y_centre = (by0 + by1) / 2.0
    cands = []
    for y_lane in np.arange(by0 + 0.15, by1 - 0.15, 0.10):
        for x_start in (0.90, 0.60, 0.30, 0.00, -0.30, -0.60, -0.90):
            for x_end in (bx1 + 0.02, bx1 - 0.05, bx1 - 0.10, bx1 - 0.20):
                if x_start - x_end < 0.5:
                    continue
                cands.append((float(y_lane), float(x_start), float(x_end)))

    results = []
    for y_lane, x0, x1 in cands:
        L = x0 - x1
        n = max(int(L / 0.02) + 1, 8)
        xs = np.linspace(x0, x1, n)
        ys = np.full(n, y_lane)
        hs = np.array([sample(floor, gx, gy, float(x), float(y)) for x, y in zip(xs, ys)])
        if not np.all(np.isfinite(hs)):
            continue
        coef = np.polyfit(np.arange(n), hs, 1)
        resid = hs - np.polyval(coef, np.arange(n))
        rng = float(hs.max() - hs.min())
        # Where does the floor give way to the plinth within the run? The heightfield's floor is
        # Floor_main only (the plinth is separate geometry), so a run that reaches x < -2.0 leaves the
        # floor field entirely; that is exactly the geometric reach limit.
        d2 = (spts[:, 0][:, None] - xs[None, :]) ** 2 + (spts[:, 1][:, None] - ys[None, :]) ** 2
        clear = float(np.sqrt(d2.min())) if len(spts) else None
        results.append({
            "y_lane": y_lane, "x_start": x0, "x_end": x1, "length_m": L,
            "diameters": L / (2 * CAN_RADIUS),
            "height_range_mm": rng * 1000, "residual_rms_mm": float(np.sqrt((resid ** 2).mean())) * 1000,
            "slope": float(coef[0]),
            "scatter_clearance_m": clear,
            "reaches_board": x1 <= bx1 + 0.021,
            "end_x_vs_wall": x1 - (-2.2),
        })

    good = [r for r in results if r["height_range_mm"] <= 10.0]
    print(f"\n{len(results)} X-direction candidate runs; {len(good)} with a height range <= 10 mm")
    good.sort(key=lambda r: (r["height_range_mm"], -r["length_m"]))
    print(f"\n  {'y_lane':>7s} {'x_start':>8s} {'x_end':>8s} {'len':>6s} {'diam':>5s} "
          f"{'range_mm':>9s} {'rms_mm':>7s} {'scatter':>8s} {'to board':>9s}")
    for r in good[:18]:
        sc = r["scatter_clearance_m"]
        print(f"  {r['y_lane']:7.3f} {r['x_start']:8.2f} {r['x_end']:8.2f} {r['length_m']:6.2f} "
              f"{r['diameters']:5.1f} {r['height_range_mm']:9.2f} {r['residual_rms_mm']:7.2f} "
              f"{(f'{sc * 1000:.0f}mm' if sc is not None else 'n/a'):>8s} "
              f"{'yes' if r['reaches_board'] else 'no':>9s}")

    # The decisive question, stated as arithmetic.
    print("\n=== REACH VERDICT ===")
    flat_run = good[0] if good else None
    if flat_run:
        print(f"  flattest -X run: y={flat_run['y_lane']:.3f}, x {flat_run['x_start']:.2f} -> "
              f"{flat_run['x_end']:.2f}, length {flat_run['length_m']:.2f} m, "
              f"height range {flat_run['height_range_mm']:.2f} mm")
    print(f"  the board's face is at x = {bx1:.4f}; the plinth occupies x -2.20..-2.00")
    print(f"  so a can travelling in -X on the FLOOR reaches x = -2.00 (the plinth face) after a run")
    print(f"  of {(-2.00) - (flat_run['x_start'] if flat_run else 0.0):.2f} m from the flattest start,")
    print(f"  and must then climb the {STEP_M * 1000:.0f} mm step onto the plinth to touch the board.")
    print(f"  A {STEP_M * 1000:.0f} mm step against a {2 * CAN_RADIUS * 1000:.0f} mm can is "
          f"{STEP_M / (2 * CAN_RADIUS) * 100:.0f}% of its diameter: a can CAN be expected to ride up")
    print(f"  a step well under its radius, and {CAN_RADIUS * 1000:.0f} mm is its radius, so this is")
    print(f"  geometrically plausible but must be solved, not assumed.")

    (OUT / "path_x_candidates.json").write_text(json.dumps({
        "can_radius_m": CAN_RADIUS, "step_m": STEP_M, "floor_z": FLOOR_Z, "plinth_top_z": PLINTH_TOP,
        "board_aabb": {"min": rec["world_aabb_min"], "max": rec["world_aabb_max"]},
        "candidates": results, "flat_candidates": good[:30], "flattest": flat_run,
        "verdict": ("the flat +/-Y runs cannot strike the board's face because the board's long axis "
                    "is along Y; a -X approach is required, and it must climb the "
                    f"{STEP_M * 1000:.0f} mm floor-to-plinth step to reach the board"),
    }, indent=2), encoding="utf-8")
    print(f"\nwritten: {OUT / 'path_x_candidates.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
