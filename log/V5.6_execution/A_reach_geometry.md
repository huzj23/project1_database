# V5.6 video A: reach geometry — the constraint that decides whether A is possible

Measured 2026-09-29 17:00–17:10 (+08:00). Tools: `tools/v56/a3_approach_geometry.py`,
`a3_reach_x.py`, `a3_terrain_report.py`. Evidence:
`outcomes/v56/hidden_alley_can_board/20260929T142714/ground/`.

Two delegated attempts at this solve failed without producing a result, so the geometry was settled
directly as arithmetic first. This note records what was measured, because it changes what A can be.

## 1. The board's actual orientation

Recovered from the exported OBJ's own face normals (not from its bounding box):

| quantity | value |
| --- | --- |
| thickness | **0.013568 m**, direction (−0.9752, −0.0260, −0.2197) → faces ±X |
| vertical extent | 0.387728 m, direction (−0.2198, 0, +0.9755) |
| length | 0.387965 m along ~Z/… |
| centre | (−2.0851, 2.1571, 0.2045) |
| lowest point | z = 0.0097 m |

The board is therefore a slab whose **thin 13.6 mm edge faces ±X** and whose broad faces point up and
down, tilted by the 12.697° lean. Its COM sits **194.8 mm** above its support.

## 2. Two decisive numbers

**The board stands only because the wall props it.** Its free-standing tipping angle is

```text
atan((t/2) / (w/2)) = atan(0.006784 / 0.193864) = 2.004 deg
```

but it actually leans **12.697°** — **6.3× past** the angle at which it would fall on its own. Nothing
about its stability is intrinsic; the wall/skirting prop is the entire reason it is standing. So the
workable mechanism is *removing or shifting that prop*, not pushing the board over, exactly as plan
§5.1.5 warns.

**Energy is not the constraint.** Mass at 500 kg/m³ is `0.3880 × 0.3877 × 0.01357 × 500 = 1.020 kg`,
and the COM rises only from 193.86 mm to 193.98 mm to pass the tip point, i.e. `ΔE = 0.0012 J`. A
0.2184 kg can at 0.8–2.0 m/s carries 0.0699–0.4368 J, which is **59× to 368×** the barrier.

So A's risk is **not** "the board is too heavy" and not "there is too little energy". It is geometry.

## 3. The real blocker: the alley floor is a dished drainage profile

`a3_terrain_report.py` sampled the exported floor heightfield. The alley floor is **flat along Y and
smoothly sloped along X** — a shallow drainage dish, not a flat plane:

```text
  y\x     -2.20  -2.00  -1.80  -1.60  -1.40  -1.20  -1.00  -0.80  -0.60  -0.40  -0.20   0.00   0.20
   1.4      -43    -47    -50    -55    -61    -69    -79    -91   -104   -119   -134   -145   -138
   2.6      -43    -47    -50    -55    -61    -69    -79    -91   -104   -119   -134   -145   -138
```
(floor z in mm; identical at every y from 1.4 to 2.9)

The floor spans **105.8 mm** in height, deepest at x ≈ 0.00 and rising to −43 mm at the wall. Every
lane is the *same* profile because the dish is a function of x only. Consequences:

| finding | value |
| --- | --- |
| runs flat along **Y** (constant x) | **0.00 mm** range over 1.0–2.0 m — genuinely flat |
| runs along **X** (needed to strike the board's face) | **0 of 252** candidates under 10 mm range |
| longest run under a 5 mm tolerance, anywhere | 1.280 m, at **y = 5.00** — far from the board |
| longest run under 20 mm, anywhere | 1.940 m, at y = 5.00 |
| lanes ending at the board's face within 20 mm | **none** |

And the board is at x ≈ −2.08, so a can travelling in −X on the floor reaches the plinth face at
x = −2.00 and must then climb a **50 mm step** (floor −0.040 → plinth top +0.010) to touch the board.
Additionally **246 scatter cells** (stones) sit in x −2.00..−1.80, right where that step is.

## 4. What this means, stated honestly

The two requirements in plan §5.1.4 — a path of **≥ 1.0 m and ≥ 6 can diameters on the ground** before
contact — and the requirement in §5.1 that the board visibly falls are, in this location, in tension:

- the flat runs are along ±Y, and a can on them travels **parallel to the board's long axis**, past its
  end rather than into its face;
- the run that would strike the face is along −X and crosses the dished profile, gaining ~100 mm of
  height over the distance available before the step, and then meets a 50 mm step with stones at its
  foot.

This does **not** mean A is impossible. It means the approach cannot be a straight line down the
dish. The candidates that remain, all of which must be settled by the solver rather than assumed:

1. **A curved/angled approach**: start along the flat Y lane to accumulate the required ≥1.0 m of
   ground travel, then angle in toward the board so contact is on its edge. The path length counts
   along the ground, and §5.1.4 does not require a straight line.
2. **A different board from the same group** whose long axis is oriented so a flat lane does strike
   its face. The alternates c1/c2/c3 have different orientations; c1 is 2.34 m long and near-vertical
   (lean 2.353°), which presents a much larger face to a Y-travelling can.
3. **A modest, recorded placement adjustment** within the original board area, which §5.1.2 explicitly
   permits ("可在原板区内最小调整位置/靠角并记录") — e.g. rotating the chosen board so its face is
   presented to the flat lane, recording the old and new values.

Option 2 is the most promising and is being tested first, because it needs no geometry change at all:
**c1's near-vertical 2.34 m board presents its broad 2.34 × 0.43 m face along the flat Y lane**, so a
can rolling down a genuinely 0.00 mm-flat lane can strike it face-on.

## 5. What must NOT be done, and will not be

- No patch floor, ramp, rail, or invisible guide to smooth the dish — §5.1.3 forbids invisible
  supports and §4 forbids altering the native ground.
- No raising the can's mass or speed beyond a defensible figure to force a result.
- No lowering gravity.
- No declaring A passed on a partial result: if the board only slides or rotates a few degrees, §5.3
  says that is not the goal, and it will be reported as unmet rather than dressed up.
