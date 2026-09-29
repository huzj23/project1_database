"""Quantify how rough the -X ground actually is, so the reach question is answered with numbers.

`a3_reach_x.py` found that ZERO of 252 candidate -X runs have a height range under 10 mm. That is
either a real terrain problem or an artefact of how the heightfield was built, and the difference
matters enormously: if the floor really is that rough, a can cannot roll a long flat path toward the
board and video A's premise fails; if it is an artefact (e.g. the field includes the wall's footprint,
or a raised kerb, or the plinth's own edge rasterised into the floor), then a flat -X lane may exist
after all.

This prints, for a grid of sample points across the alley floor:
  * the floor height, so the shape of the terrain is visible as a table;
  * which cells are empty (no floor triangle), which is how the plinth gap and the wall show up;
  * a per-lane profile along X at several Y values, which is the direct answer to "can a can roll
    from x=A to x=B at this y".

No physics; this is terrain description.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

ROOT = Path(r"D:\workspace\project1_database")
RUN = ROOT / "outcomes/v56/hidden_alley_can_board/20260929T142714"
z = np.load(RUN / "ground/heightfields.npz")
gx, gy, floor, scatter, wall_x, Hz = z["gx"], z["gy"], z["floor"], z["scatter"], z["wall_x"], z["Hz"]

print("=" * 100)
print("floor heightfield description")
print(f"  grid {floor.shape}: {len(gx)} x samples ({gx[0]:.3f}..{gx[-1]:.3f}, "
      f"step {(gx[1]-gx[0])*1000:.1f} mm), {len(gy)} y samples ({gy[0]:.3f}..{gy[-1]:.3f}, "
      f"step {(gy[1]-gy[0])*1000:.1f} mm)")

fin = np.isfinite(floor)
print(f"  filled cells: {fin.sum()} / {floor.size} ({100.0*fin.sum()/floor.size:.1f}%)")
print(f"  height over filled cells: min {floor[fin].min():+.4f}  max {floor[fin].max():+.4f}  "
      f"range {(floor[fin].max()-floor[fin].min())*1000:.1f} mm")
vals, counts = np.unique(np.round(floor[fin], 3), return_counts=True)
print(f"  distinct 1 mm height levels: {len(vals)}; the most common:")
for v, c in sorted(zip(vals, counts), key=lambda t: -t[1])[:8]:
    print(f"    z={v:+.3f} m  in {c} cells ({100.0*c/fin.sum():.1f}%)")

# Which x columns are mostly empty? The plinth and the wall show up here as gaps.
print("\n  coverage by x column (an empty column means no floor there):")
prev = None
for i in range(0, len(gx), 5):
    frac = np.isfinite(floor[i]).mean()
    if prev is None or abs(frac - prev) > 0.05:
        print(f"    x={gx[i]:+.3f}  filled {100*frac:5.1f}%  median z "
              f"{np.nanmedian(floor[i]) if np.isfinite(floor[i]).any() else float('nan'):+.4f}")
        prev = frac

# Direct lane profiles: this is the answer to "can a can roll here".
print("\n=== lane profiles along X (floor z in mm, '.' = no floor cell) ===")
lane_ys = [1.4, 1.7, 2.0, 2.3, 2.6, 2.9, 3.2]
xs_show = [x for x in gx if -2.2 <= x <= 1.2]
hdr = "  y\\x   " + "".join(f"{x:7.2f}" for x in xs_show[::10])
print(hdr)
for y in lane_ys:
    j = int(np.argmin(np.abs(gy - y)))
    row = []
    for x in xs_show[::10]:
        i = int(np.argmin(np.abs(gx - x)))
        v = floor[i, j]
        row.append("      ." if not np.isfinite(v) else f"{v*1000:7.0f}")
    print(f"  {y:4.1f}  " + "".join(row))

# The specific question: at each y, what is the longest run in -X whose height range stays under a
# threshold, and where does it end?
print("\n=== longest run per lane, at several roughness allowances ===")
for tol_mm in (5.0, 10.0, 20.0, 30.0):
    best = None
    for y in np.arange(gy[0] + 0.05, gy[-1] - 0.05, 0.05):
        j = int(np.argmin(np.abs(gy - y)))
        col = floor[:, j]
        for i0 in range(len(gx) - 1, -1, -1):
            if not np.isfinite(col[i0]):
                continue
            for i1 in range(i0 - 1, -1, -1):
                if not np.isfinite(col[i1]):
                    break
                seg = col[i1:i0 + 1]
                if (seg.max() - seg.min()) * 1000 > tol_mm:
                    break
                L = gx[i0] - gx[i1]
                if best is None or L > best[0]:
                    best = (L, float(y), float(gx[i1]), float(gx[i0]),
                            float((seg.max() - seg.min()) * 1000))
    if best:
        print(f"  tolerance {tol_mm:5.1f} mm: longest run {best[0]:.3f} m at y={best[1]:.2f}, "
              f"x {best[2]:+.3f}..{best[3]:+.3f}, range {best[4]:.2f} mm")
    else:
        print(f"  tolerance {tol_mm:5.1f} mm: no run found")

# And specifically for the lane that would meet the board's face.
board_lo, board_hi = 1.4266, 2.8876
print(f"\n=== runs that END at the board's face (x >= -2.02) within the board's y span ===")
print(f"  board y span {board_lo:.3f}..{board_hi:.3f}")
found_any = False
for y in np.arange(board_lo, board_hi, 0.1):
    j = int(np.argmin(np.abs(gy - y)))
    col = floor[:, j]
    # Walk backward from the board face while the height stays within 20 mm of the height there.
    i_end = None
    for i in range(len(gx)):
        if gx[i] >= -2.02 and np.isfinite(col[i]):
            i_end = i
            break
    if i_end is None:
        continue
    z_end = col[i_end]
    i_start = i_end
    for i in range(i_end - 1, -1, -1):
        if not np.isfinite(col[i]) or abs(col[i] - z_end) > 0.020:
            break
        i_start = i
    L = gx[i_end] - gx[i_start]
    if L >= 0.3:
        found_any = True
        print(f"  y={y:.2f}: from x {gx[i_start]:+.3f} to {gx[i_end]:+.3f} = {L:.3f} m, "
              f"ends at z {z_end*1000:+.0f} mm (20 mm tolerance)")
if not found_any:
    print("  none: no lane reaches the board face even with a 20 mm height tolerance")

print("\n=== scatter (stones/grass/leaves) in the board's approach lane ===")
si, sj = np.nonzero(np.isfinite(scatter) & (scatter > floor + 0.004))
m = (gy[sj] >= board_lo) & (gy[sj] <= board_hi) & (gx[si] >= -2.2) & (gx[si] <= 0.6)
print(f"  {m.sum()} scatter cells in x -2.2..0.6, y {board_lo:.2f}..{board_hi:.2f}")
if m.sum():
    for x0 in np.arange(-2.0, 0.6, 0.2):
        mm = m & (gx[si] >= x0) & (gx[si] < x0 + 0.2)
        print(f"    x {x0:+.2f}..{x0+0.2:+.2f}: {mm.sum():4d} scatter cells")
