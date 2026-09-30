# Video A: the physics is not reachable in this scene. A closed, measured argument.

Status at 2026-09-29 20:30 (+08:00). **Video A's required outcome cannot be produced by real physics in
the Hidden Alley scene with the scene's own board and a real can.** That is a negative result, and it is
established by measurement rather than by a failed search, so it is recorded here in full instead of
being worked around. Plan §5 tolerances were not lowered and no force, hinge, rail, pusher or timing
trick was introduced.

The result was reached against every allowance the plan makes: §5.1.2 permits a minimal adjustment of
the board's position and lean angle inside its original area, §5.1.4 permits changing the siting when
the physical scale does not work, and §5.1.6 explicitly directs changing **the board** or the direction
rather than repeatedly raising the can's mass or speed. All three were used.

## 1. The scene, measured (not inferred)

`a31_cross.py` probed the alley's entire cross-section on both sides, which every earlier attempt had
skipped by looking only at x < 0:

| probe | result |
| --- | --- |
| wall (the board's side) | solid at **x = −2.160** from 65 mm upward; stepped back to −2.180 and −2.200 higher up |
| plinth in front of it | top at **z = +0.010** from x = −2.20..−2.00, i.e. a **50 mm step** up from the alley floor |
| alley floor in front of the lip | z ≈ **−0.048** at x = −1.95, sloping to −0.145 further out |
| flat run at can height | **x = −1.90..−0.90 only (1.0 m)** |
| +X side | **no wall at all** at any can height for any y with a floor (6 mm hits at x = +0.929, nothing above) — it is the open end of the alley |
| beyond y = 4.5 | the −X wall moves out to x = −2.700 and the alley opens up; no wall to lean a board on |

So there is exactly **one** wall, and it is guarded by a 50 mm step.

## 2. The impasse, in closed form

A board leaning on that wall with its foot on the **reachable** alley floor must span the 0.160 m
between the plinth lip (x = −2.000) and the wall (x = −2.160):

```text
sin(theta) >= 0.160 / upright_extent
```

For the recommended board `board_01_wooden_boards_001_c04` (measured upright extent **0.387728 m**):

```text
theta >= asin(0.160 / 0.387728) = 24.37 deg
theta >= ~31 deg for the face at the can's contact height to clear the lip as well
```

and the solver measured what a board at that lean does. Every configuration in the stable+reachable
band was a **ramp**, not a wall:

| run | placement | can's rise | board rotation |
| --- | --- | --- | --- |
| a29 | lean 45.39 deg | **244 mm** | **45.39 → 45.42 deg** |
| a32 (closed box) | lean 52.43 deg | **264 mm** | 52.43 → 57.93 deg |
| a33 (c03 board, 12.88 deg) | lean 12.88 deg | 100 mm | 12.88 → **12.60 deg** |

The one lean that behaved like a wall and genuinely toppled the board was 12.4 deg (a29's p2: max
85.9 deg, final 76.8 deg, held 1.71 s) — but at 12.4 deg the board cannot reach the wall, so it was
free-standing, and its own no-can control toppled it (12.38 → 77.29 deg). It was never stable.

## 3. Everything the plan permits was tried

| escape route | outcome |
| --- | --- |
| strike the board's end along the wall (§5.1.5) | 84 trials, 0 topples; a blow along the board's own long axis translates it (measured slide < 1 mm, yaw 0.0) |
| stand the board **tall** (1.4612 m edge vertical) so it only needs 6.3 deg of lean | `a30`: **36/36 placements fell flat during settling** (settled 86–90 deg, drift to 974 mm). A 1.46 m × 13.6 mm plank will not stand on its end |
| use the scene's **taller** boards (c03 0.8269 m, c02 0.8498 m upright) | `a33`: 8 placements stable and reachable, including c03 at only **12.89 deg** with **311 mm** of face clearance — and still 0/72 topples; the best case drove the board 0.04 deg *shorter*, i.e. the wall braces it |
| closed GEOM_BOX collision proxy instead of the open 5-face shell mesh | `a32`: unchanged (264 mm rise, 5 deg rotation) |
| a heavier, real can (0.74 kg → 3.20 kg, i.e. up to 11.5 kg·m/s) | no topple; the board's lean *decreases* |
| a larger can (0.15 m max diameter) striking higher | no topple |
| re-site along the whole wall (y 0.40–4.20) | no plinth-free run exists; `a21` found the wall exposed at can heights but the board's foot must sit either on the plinth (can cannot reach it) or in front of it (→ the 24.4 deg ramp) |

Two defects in my own earlier work had to be found and fixed before this conclusion was trustworthy,
and both are recorded in `A_physics.md`: the campaign used a **reversed rolling spin**
(ω = (v/r)(d×ẑ) instead of (v/r)(ẑ×d); proven by `a26_spin2.py` — 2.484 m versus 4.625 m of travel on
a flat surface), and board occupancy was sampled by **vertex** height bands on an open shell, which
falsely placed the board's face 179 mm behind the lip.

## 4. What was NOT done

No patch floor, ramp, rail, hinge, timer, invisible pusher, lowered gravity, inflated can mass, or
prescribed trajectory. No acceptance criterion was lowered: "the board jitters or translates" is still a
failure, and 15° of rotation or 5 cm of slip was still not counted as success. No placement was sited on
an unreachable plinth, and no result was reported as a pass while its own control failed.

## 5. Consequence for delivery

Per the plan's separation of verdicts, video A is recorded as **`physics_passed: false`** with the
mechanism documented, rather than delivered as a partial stage. The honest options are:

1. deliver video B (which is complete and validated) and report A as blocked with this evidence;
2. have the user choose a different target object for the can in the same alley — a free-standing object
   that is not wall-braced would not face this impasse, and the alley floor's 1.0 m flat run at
   x = −1.90..−0.90 is genuine;
3. have the user accept a small, declared scene edit that removes the 50 mm plinth step in front of the
   board (it is a drainage plinth, not structural support), which would let the board lean at ~12 deg
   with its foot on open floor — the configuration a29 measured actually toppling.

Options 2 and 3 change the task definition, so they are the user's to choose; option 1 is what can be
delivered now without misrepresenting anything.
