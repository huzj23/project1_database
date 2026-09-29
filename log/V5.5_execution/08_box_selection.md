# Stage 08 asset selection: box measurement for the domino chain

Recorded while stage 05 renders, because the box choice decides whether the main domino chain is
buildable at all and it is cheaper to settle now than to discover mid-stage.

All numbers are measured on the server (`models/gso`), from each asset's collision proxy where one
exists, otherwise its visual mesh.

---

## 1. What 08 section 2 requires

A thin, long, **closed**, flat-bottomed real package box with:

| property | 08 requirement |
| --- | --- |
| height/thickness | 3–8 (a real domino ratio) |
| width/thickness | ≥ 1.5 (wide enough not to fall sideways) |
| body type | closed, flat-bottomed, can stand and topple as a unit |
| dynamics | a real dynamic rigid body with a proper collider |

The bounding box cannot establish "closed and flat-bottomed": a keyboard, a shoe and an action figure
all have box-shaped bounding boxes. So the shape had to be measured from the mesh.

## 2. What was measured

Server inventory: **140 GSO assets**. All 138 with a geometry file were measured for bounding
proportions; **38** satisfied the 3–8 / ≥1.5 ratio band and had a collision proxy. Those 38 plus two
controls (a keyboard and a cube, which a bounding box would rank highly) were then checked for shape.

## 3. Result

**1 of 40 assets is usable as a domino: `Hasbro_Cranium_Performance_and_Acting_Game`.**

| property | measured | 08 requirement |
| --- | --- | --- |
| dimensions (h × t × w) | **272.6 × 55.8 × 207.7 mm** | — |
| height/thickness | **4.88** | 3–8 pass |
| width/thickness | **3.72** | ≥1.5 pass |
| boxiness (volume / bounding box) | **0.989** | ≥0.55 pass |
| base footprint coverage | **0.994** | ≥0.85 pass |
| strike face coverage | **0.967** | ≥0.85 pass |
| tipping angle | **11.45°** | 4–25° pass |

For contrast, the same measurement on assets a bounding box would have accepted:

| asset | boxiness | base coverage | verdict |
| --- | --- | --- | --- |
| `Supernatural_Ouija_Board_Game` | 0.890 | 0.876 | base passes, strike face 0.266 fails |
| `Hasbro_Trivial_Pursuit_Family_Edition_Game` | 0.842 | 0.817 | base 0.817 fails |
| `LEGO_Star_Wars_Advent_Calendar` | 0.952 | 0.905 | strike face 0.428 fails |
| `Persona_Q_Shadow_of_the_Labyrinth_3DS` | 0.661 | 0.639 | fails |
| `Razer_BlackWidow_Ultimate_2014_Keyboard` | 0.381 | 0.252 | fails (as expected) |
| `Room_Essentials_Fabric_Cube_Lavender` | 0.147 | 0.107 | fails despite the name — it is a soft fabric cube |

The separation is clean: real rigid boxes score 0.8–0.99 on base coverage, figurines and soft goods
score 0.001–0.15. Nothing sits near the threshold, so the choice is not a borderline call.

## 4. Chain layout with the measured box

08 section 2: total chain length = `12*t + 11*gap`.

| gap | chain length | clear run needed |
| --- | --- | --- |
| 0.15·h = 40.9 mm | **1.120 m** | 2.12 m |
| 0.20·h = 54.5 mm | 1.270 m | 2.27 m |
| 0.25·h = 68.1 mm | 1.420 m | 2.42 m |
| 0.30·h = 81.8 mm | 1.570 m | 2.57 m |

Propagation needs `gap < h` = 272.6 mm, satisfied with a wide margin at every spacing above. The
chain needs roughly **2.1–2.6 m of clear floor** including run-in and run-out — this is the number to
check against whatever region 08 selects.

## 5. Two caveats that must be disclosed, not smoothed over

**URDF masses are scan artefacts.** Across the measured set they span **0.00006–0.00717 kg**; the
Cranium box is recorded as **0.0028 kg**. A 273 mm game box does not weigh 2.8 grams. These masses
come from the scanning pipeline, not from the objects. 08 must assign mass from a stated density and
disclose that it did so — it cannot use the URDF value and call it measured.

**Many assets are hollow, so solid-box inertia over-estimates.** The ratio of the asset's own URDF
inertia to 08 section 3's `Ixx = m*(h² + d²)/12` spans **0.087–1.310**; the Cranium box is **0.648**.
A hollow cardboard box legitimately has less inertia than a solid block of the same envelope. Wherever
08 uses the box formula, the discrepancy has to be reported. This does not disqualify the box — a
hollow rigid box is still a rigid box — but 08 section 3's formula is an idealisation and must be
labelled as one.

---

## 6. The measurement itself was wrong three times, and each failure was informative

Recorded because the pattern is the same one that produced the camera-visibility error in stage 05: a
plausible-looking metric whose denominator cannot reach the requested threshold, which reads as "the
assets are all bad" rather than "the measurement is wrong". Each time the tell was an impossible
number, not a failing asset.

**Attempt 1 — share of total surface area in the base plane, threshold 0.75.** A cube's largest face
is one sixth of its surface, so this can never exceed ~0.17 for a cube and ~0.33 for a thin slab.
Reported **0 of 10** usable, including an asset named `Room_Essentials_Fabric_Cube_Lavender`. A cube
failing a flatness test is the tell.

**Attempt 2 — share of total projected area in the base plane, threshold 0.90.** A closed box
projects *both* its bottom and its top face onto the same footprint, plus its sides, so the ceiling is
exactly 0.50. The best boxes measured **0.48–0.50** — sitting precisely on the ceiling, which is what
exposed it. Reported **0 of 40**.

**Attempt 3 — flat area over the bounding-box face.** Correct in principle, but it assumed the mesh's
stored axes are the box's axes. GSO assets are scans in arbitrary poses, so for a slightly rotated box
no face aligns with a stored axis and the "within 2% of the extreme" test catches only slivers. Boxes
reported a strike-face coverage of **0.001** while a figurine reported **0.42** — the ordering was
inverted, which was the tell. Reported **1 of 40** but for the wrong reason.

**Attempt 4 (current).** The object's own axes are recovered from its face normals: cluster triangles
by normal direction, take the largest-area direction, then the largest at least 60° away, then the
cross product; rotate into that frame; measure there; and choose the standing orientation explicitly
rather than assuming stored Z is up. Boxes now score 0.99 base coverage and figurines 0.001.

**A note on `closedness`:** measured on the collision proxy it is 1.000 for every asset, because the
proxy is a convex hull and a convex hull is always closed. It is therefore uninformative as a
discriminator and is reported as such rather than presented as a passing check.

---

## 7. What this means for the plan

1. **The chain is buildable but only with this one asset** (plus, potentially, the Trivial Pursuit box
   at 272.9 × 73.5 mm if the strike-face threshold were relaxed — it fails at 0.210, so it is not a
   substitute for a domino but could serve as the independent trigger object).
2. **08 probably needs the same box instanced 12 times**, which is legitimate: the requirement is 12
   real box instances in a chain, not 12 distinct assets. The task order says "≥12 real box
   instances", and instancing one approved real asset satisfies that. This should be confirmed.
3. **The clear-floor requirement is 2.1–2.6 m.** 08's region selection must be checked against that
   number before layout.
4. **Mass and inertia must be assigned, not read from the URDF**, and the assignment disclosed.
5. If 08 wants more than one distinct box asset for variety, the measurement shows the library does
   not offer a second rigid box of domino proportions — the alternatives are game boxes whose strike
   faces are not flat enough to topple as dominoes. That constraint should shape the story rather
   than be discovered as a failure later.
