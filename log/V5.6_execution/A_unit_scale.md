# V5.6 A: Hidden Alley unit scale and board geometry

Measured 2026-09-29 14:40 (+08:00) by `tools/v56/a_unit_scale.py`.
Evidence: `outcomes/v56/hidden_alley_can_board/unit_scale.json`.

## 1. The unit question, and why it mattered

An earlier bootstrap record for this scene
(`outcomes/v55/bootstrap/20260928T194500/scale/hidden_alley_local.json`) contains two numbers that
look contradictory:

| field | value |
| --- | --- |
| `scale_length` | 10.0 |
| `scene_bbox.size` | 1226.93 × 1226.93 × 1239.79 |

If one scene unit were 10 m, the boards (2.76 units across) would be 27.6 m long. If the 1226-unit
bbox were the set, the alley would be 1.2 km wide. Both are absurd, so the question had to be settled
before any physics: a factor-of-10 error would make the can the wrong size relative to the board and
invalidate every threshold in the plan.

## 2. Measured answer: 1 scene unit = 1 metre

| evidence | value | what it implies |
| --- | --- | --- |
| unit system | METRIC | metres are the intended unit |
| `scale_length` | 10.0 | a Blender display/export scale; **not** applied to the stored geometry |
| mesh objects total | 1363 | — |
| objects > 100 units | **15** | the `scene_bbox` is produced by these, not by the set |
| objects ≤ 100 units | 1348 | the set itself |
| set-scale object sizes | smallest 0.031, **median 1.675**, largest 90.9 units | ordinary set dressing, in metres |
| camera `hidden_alley_camera` | clip **0.1 … 1000**, lens 24 mm | coherent for a metres-scale set; a 10× larger set would need clip_end in the thousands |

The 1226-unit bbox is therefore attributed to **15 named oversized backdrop objects**, not to the
alley. `scale_length = 10.0` is a display setting only and does not change the physical size of the
stored geometry.

**Cross-check the physics step must still make:** the can diameter must be asserted as a fraction of
the board's measured thickness and that ratio reported, so a residual scale error cannot survive into
the solve silently. This is recorded in the JSON as `must_be_confirmed_by`.

## 3. The boards

| object | dims (units = m) | object scale | location |
| --- | --- | --- | --- |
| `wooden_boards` | 2.7619 × **0.0495** × 2.9979 | 1.0 | (−1.3507, −5.1295, 0.7876) |
| `wooden_boards.001` | 0.4145 × 3.1102 × 2.4901 | **0.8873** | (−2.1031, 3.6927, 1.19) |
| `wooden_boards.002` | 2.7619 × **0.0495** × 2.9979 | 1.0 | (−1.3052, −5.0703, 1.2113) |

Two things to note, both of which change how the board is used:

1. **`wooden_boards` and `wooden_boards.002` are thin slabs — 49.5 mm thick, 2.76 m wide, 3.0 m
   tall.** They are plank-wall geometry: the earlier audit counted 6 mesh-connected components in
   `wooden_boards`, so if those 6 components span the 2.76 m width, a single plank is roughly
   **0.46 m wide × 49.5 mm thick × 3.0 m tall**. That is a tall plank rather than a short one, and
   the plan asks for a *shorter* board if one exists. Whether a shorter complete plank exists among
   the components is exactly what the extraction step is determining.
2. **`wooden_boards.001` carries a non-unit object scale of 0.8873.** Its effective physical size is
   therefore 0.3678 × 2.7597 × 2.2095 m, not the raw 0.4145 × 3.1102 × 2.4901. This is the same
   class of defect as V5.6 §3.2: any code that reads `dimensions` without applying object scale gets
   the size wrong by 11%. The extraction and any proxy built from it must apply it.

## 4. Tipping geometry, as arithmetic rather than impression

For a board of thickness `t` standing on its base and leaning on nothing, the angle gravity must be
brought over the leading bottom edge is `atan((t/2) / (h/2))`:

| board | t | h | tipping angle |
| --- | --- | --- | --- |
| a single 0.46 m-wide plank | 0.0495 m | 3.0 m | **0.95°** |
| `wooden_boards.001` at its effective scale | 0.3678 m | 2.2095 m | **9.46°** |

The first number is the important one and it is not the number the plan's caution would predict: a
tall thin plank is **extremely** easy to rotate, because its base is only 49.5 mm wide. Its difficulty
is not the tipping barrier but the fact that it **leans against a wall**, so it cannot fall forward —
the can must either knock it sideways or make it lose its support. That matches the plan's own
guidance (§5.1.5: approach diagonally along the wall so the board loses support or topples sideways)
and it means the honest risk for A is *"the board will rotate or slide rather than fall"*, not
*"the board is too heavy"*.

This is an estimate from the bounding box, not a measurement of the real support condition, and it
must be settled by the no-trigger stability test and the actual solve rather than by this table.

## 5. Open items

- Whether the 6 connected components of `wooden_boards` are 6 complete planks or fragments of fewer
  boards — under investigation; a component count is not a piece count.
- Whether the boards actually rest on the ground or are floating geometry, and whether they are free
  leaning or part of a fixed wall assembly.
- The mass: to be assigned from the measured volume and a stated timber density, never from a
  URDF value.
