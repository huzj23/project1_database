# V5.6 — A: Hidden Alley can-board extraction

**Task.** From `ph_hidden_alley.blend`, identify and extract ONE physical wooden
board that a rolling can could knock over.
**Author:** delegated subagent. **Date of work:** 2026-09-29.
**Source file:** `models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend`
**Source SHA-256:** `be1247889cee3ce10028ee1ef1066a96728b3c2aa191ad12b51cc3b578fa4ae9` (481,373,656 bytes)
**Blender used:** local 4.2.23 LTS, `--background --factory-startup`. Server Blender not used (it segfaults on this file).
**Scripts (all under `tools/v56/`, all prefixed `a_`):** `a_board_components.py`, `a_dump_topology.py`, `a_probe_view.py`, `a_neighbours.py`, `a_analyze_boards.py`, `a_export_boards.py`, `a_verify_exports.py`, `a_make_report.py`.
**No file was deleted. Nothing under `third_party/` or `models/` was modified. No render was produced.**

---

## 1. The headline result

There are **three** `wooden_boards*` objects, and they are **two completely different things**:

| Object | Components | World region | Verdict |
|---|---|---|---|
| `wooden_boards` | 6 | x −1.44…1.30, **y −5.17…−5.12**, z −0.53…2.44 | Fixed iron-gate infill. **Behind the camera.** Unusable. |
| `wooden_boards.002` | 6 | x −1.40…1.35, **y −5.11…−5.06**, z −0.11…2.86 | Same gate, second layer. **Behind the camera.** Unusable. |
| `wooden_boards.001` | 5 | x −2.20…−1.82, **y 0.47…3.58**, z −0.05…2.39 | **Loose boards leaning on the building wall. In frame. Usable.** |

Sixteen of the seventeen components examined are therefore rejected before any
physics consideration, and for two independent reasons.

### Why 6+6 components are NOT six-plus-six boards

The task warned that a component count is not automatically a board count because
loose unwelded vertices can split one board into pieces. I checked this properly
rather than assuming it:

* Each of the 6 components in `wooden_boards` is **8 vertices / 5 faces** with
  **0 loose vertices**, and **all three board objects have 0 loose vertices in
  total**. There is no unwelded-vertex inflation anywhere in these meshes.
* The script counts face-less components separately
  (`n_components_loose_verts_only`), and it is **0 for all three objects**. That
  is the direct test for the failure mode the task warned about.
* I also re-ran the split with a 1 mm provisional vertex weld (`--connect-eps 0.001`)
  as a cross-check. The component counts were **unchanged** (6 / 5 / 6), so the
  edge-connectivity result is not an artifact of coincident-but-unwelded corners.
* Since the connected-component count here *does* equal the count of
  face-bearing pieces, the honest reading is: **`wooden_boards` is 6 separate
  physical slab pieces, `.002` is 6 more, `.001` is 5 more** — 17 pieces in
  total. They are separate *pieces*, but they are not 17 *free-standing boards*;
  see §3.

### A dimension-measurement trap I had to fix

My first pass derived board dimensions from edge-vector clustering but picked up
**quad diagonals** as if they were edges, producing nonsense (a "2.89 m" edge and a
crossed parallelogram). The corrected method takes all pairwise vertex
differences, clusters them by direction, and within each direction keeps the
**shortest** member as the primitive edge (longer members are face/body
diagonals). It then selects the three shortest **mutually orthogonal** families.

Two independent confirmations that this is right:

1. Edge perpendicularity comes out at **90.000 / 90.000 / 90.000 deg** for every
   component.
2. A corner-basis test — can all 8 vertices be written as `origin + a·e₁ + b·e₂ + c·e₃`
   with `a,b,c ∈ {0,1}`? — returns a **maximum corner residual of 5.7e-07 m**
   (0.57 µm) for the recommended board. So each component is an **exact
   rectangular slab**, and `L × W × T` is exact rather than an AABB approximation.

**The AABB is never used for board dimensions in this report.** For a leaning
board the AABB overstates the true size; e.g. the recommended board's AABB is
0.135 × 1.461 × 0.390 m while its true slab is 1.461 × 0.388 × 0.0136 m.

---

## 2. Unit scale

**1 scene unit = 1 m. Confirmed** — and I did not spend time re-deriving it, per
the parent's instruction; `outcomes/v56/hidden_alley_can_board/unit_scale.json` is
cited as the authority. My independent runs corroborate it: unit system `METRIC`,
length unit `METERS`, camera clip 0.1…1000, and 1331 of 1367 mesh objects are
under 20 units across, with a median max-dimension of 1.675 units.

`scale_length = 10.0` is a Blender **display** factor. It is **not applied** to
any number in this report. This matters: multiplying the reported sizes by 10
would make a 1.46 m board into a 14.6 m board.

**Object scale IS applied.** `wooden_boards.001` has a uniform object scale of
**0.887279987**. Every length I report is measured in world space, i.e. after
`matrix_world`, so the object scale is already included. The raw local edge
lengths are **1/0.88728 = 1.1271× larger** — e.g. the recommended board's
thickness is 15.29 mm in local coordinates and **13.57 mm** in world coordinates.
Quoting the local number would overstate the board by 12.7 %.

---

## 3. Free-leaning board, or fixed wall geometry? — evidence

`wooden_boards.001`'s five components are **loose props leaning against the wall**,
not wall geometry. The evidence, strongest first:

**(a) No component interpenetrates the wall mesh.** I ran a triangle-triangle BVH
overlap test (`mathutils.bvhtree`) of each component against **every mesh whose
AABB is within 0.25 m**. This is a real intersection test, not an AABB guess.
Result for `wooden_boards.001`: components intersect only ground scatter
(`leaves`, `stones`) and the wall plinth (`base_tripple_01.003`). **`apartment_walls`
appears in no component's intersection list.** Geometry carved out of a wall
would interpenetrate it.

**(b) Every component is tilted off vertical.** Lean from vertical, measured as
the tilt of the slab's near-vertical in-plane axis:

| comp | lean | | comp | lean |
|---|---|---|---|---|
| c0 | 8.475° | | c3 | 7.097° |
| c1 | 2.353° | | c4 | **12.697°** |
| c2 | 2.621° | | | |

Built-in wall panels would be at 0°. Not one of these is.

**(c) Wall contact is a measured small gap.** Rays cast from points on each
component's own surface toward the wall (−X) reach the wall/trim at
**6.7 mm (c2), 27.2 mm (c4), 42.1 mm (c1), 123.5 mm (c3), 7.4 mm (c0)**. A welded
wall panel would show 0 mm.

**(d) Different material from the wall.** The boards are `ph_gate_boards`; the
building wall is the `modular_urban_*_facade_*` family.

**(e) Base contact.** The components stand at the wall foot on the plinth
`base_tripple_01.003` (x −2.2…−2.0, top z = 0.010). `c0` and `c3` additionally
embed ~5 mm into the ground layer (`Floor_main` top z = −0.040).

**(f) No animation data, no parent, each is a static 8-vertex/5-face slab.**

### The structural surprise that changed my reading

Every one of the five components is an **open 5-face shell** — one broad face is
missing (4 boundary edges, 1 broad face present, 1 missing). Which side is open
is not the same for all components:

* the open side faces **the wall** for **c1, c2, c3, c4**;
* the open side faces **away from the wall** for **c0**.

This is why "the board leans its broad face on the wall" is true only for `c0`.
For c1–c4 the wall-side contact is at the slab's **thin top end edge**, so the
boards **rest their upper end on the wall and lean**, propping rather than
laying flat against it. It is also a strong indication that these are decorative
props placed by the artist: a structural wall panel would not be modelled as a
one-sided open shell.

I want to be explicit about the limits of this reading, because it is the one
thing I could not fully pin down (see §6).

---

## 4. Recommended board

**`wooden_boards.001`, edge-connected component index 4** — exported as
`board_01_wooden_boards_001_c04.obj`.

| Quantity | Value |
|---|---|
| World AABB | min (−2.152816, 1.426557, 0.009686) → max (−2.017358, 2.887637, 0.399251) |
| **Length** | **1.461221 m** (horizontal, parallel to the wall along −Y) |
| **Width / in-plane** | **0.387728 m** |
| **Thickness** | **0.013568 m** (13.57 mm) |
| Height (vertical extent) | 0.389565 m |
| Lean from vertical | **12.697°** (the most leaned of all five) |
| Volume | 0.007687 m³ (= verified `L × W × T`) |
| **Mass** | **3.84 kg** @ 500 kg/m³; range **3.07–5.38 kg** @ 400–700 kg/m³ |
| Resting on | top of `base_tripple_01.003`, hit at z = 0.010; penetrates it by 3 triangle pairs |
| Leaning against | wall-side rays stop on the skirting trim `dado_tripple_01.003` at 27.2 mm, **not** on `apartment_walls` |
| Interpenetrates wall? | **No** (0 overlapping triangles with `apartment_walls`) |

A can (66 mm dia × 122 mm) is roughly **4.9× the board's thickness** and **17 % of
its height** — a plausible scale relationship, which is a sanity check on the
1 unit = 1 m claim rather than a substitute for it.

### Alternates (ranked)

| Rank | File | L × H × T (m) | Mass @500 | Lean | Frame area |
|---|---|---|---|---|---|
| 1 | `board_01_wooden_boards_001_c04.obj` | 1.4612 × 0.3877 × 0.01357 | 3.84 kg | 12.697° | 0.69 % |
| 2 | `board_02_wooden_boards_001_c03.obj` | 1.3076 × 0.8269 × 0.01357 | 7.34 kg | 7.097° | 1.59 % |
| 3 | `board_03_wooden_boards_001_c02.obj` | 1.3076 × 0.8498 × 0.01357 | 7.54 kg | 2.621° | 0.96 % |
| 4 | `board_04_wooden_boards_001_c01.obj` | 2.3386 × 0.4274 × 0.01357 | 6.78 kg | 2.353° | 1.92 % |

All five `wooden_boards.001` components are 13.57 mm thick and all are
rectangular slabs. `c0` (2.4387 m tall, 12.30 kg) was rejected as too tall and
heavy.

**Ranking rule:** rectangular slab **and** inside the camera frame; then
**shortest height first** (a can must be able to topple it), then lightest mass.
Lean is reported but **not** used to rank, because "more leaned ⇒ easier to
topple" is a hypothesis this task does not test.

**The tradeoff the parent should decide:** `c4` is the physics-optimal pick but the
**smallest in frame** (0.69 % of frame vs c0 1.98 %, c1 1.92 %, c3 1.59 %).
`c3` is the compromise — 0.82 m tall, 7.34 kg, 7.1° lean, **2.3× more frame area**
than c4.

### Volume and mass: what I did NOT do

The task brief said the `abs_volume` in my first component dump was meaningless.
**Correct, and I had already caught and discarded it.** The cause is now
diagnosed precisely: every component is an **open 5-face shell**, so the
divergence-theorem signed volume does not apply. The script now reports
`is_closed_solid: false` and `boundary_edge_count: 4` and uses the **verified
slab box volume `L × W × T`** instead. **Volume is never taken from the mesh.**

**Mass basis:** `mass = slab volume × density`. The scene does not determine the
timber species — the material is a texture (`ph_gate_boards`) with no density
input — so I report **three stated densities**: 400 kg/m³ (pine/softwood),
**500 kg/m³ (mid softwood, headline)**, 700 kg/m³ (hardwood). The headline
3.84 kg is not a measurement; it is a computed value under a stated assumption,
and the defensible range is 3.07–5.38 kg.

---

## 5. Exports and independent verification

All under `outcomes/v56/hidden_alley_can_board/boards/`, **world coordinates
preserved** (vertices are local vertices transformed by `matrix_world`, no other
transform; OBJ written in Blender's native Z-up right-handed frame).

| File | Contents |
|---|---|
| `board_01_wooden_boards_001_c04.obj` | chosen board, 8 v / 5 f |
| `board_02…c03.obj`, `board_03…c02.obj`, `board_04…c01.obj` | alternates, 8 v / 5 f each |
| `support_wall_ground.obj` | wall/plinth/floor/stones within 0.6 m of the chosen board's AABB: 3007 v / 5267 f (5592 tris), AABB (−2.200, 0.500, −0.740) → (−1.367, 3.602, 1.000) |
| `*.json` sidecars + `export_manifest.json` | per export: source object, component index, **exact vertex and face indices used**, source `.blend` SHA-256, world matrix, exported AABB |

**Independent verification** (`a_verify_exports.py`) re-imports each OBJ into an
**empty** Blender scene and re-measures from scratch, so the numbers are
confirmed against the artefact the solver will load, not against the writer's
in-memory state:

* vertex/face counts match the sidecars — **true for all 5 files**;
* re-imported world AABB vs sidecar — **max error 0.0 m** for the chosen board
  (1e-06 m on one alternate, which is sidecar rounding);
* re-imported edge lengths for the chosen board **0.013568 / 0.387728 / 1.461221 m**,
  matching the analysis to 1e-06 m;
* exact-rectangular-box corner residual **5.7e-07 m**.

Sidecars record vertex index lists, so each export can be traced back to exact
source vertices.

Support OBJ contributors: `apartment_walls` (176 f), `base_tripple_01.003` (4 f),
`Floor_main` (145 f), `stones` (4942 f).

---

## 6. What surprised me, and what I could not resolve

1. **NOT VISUALLY CONFIRMED — the biggest gap.** I rendered nothing. Rendering
   was stopped at the parent's request to protect the per-frame cost measurement,
   and my in-flight render produced **zero PNGs** before being stopped. Everything
   above is metric: projection, ray casts, triangle overlap. **Nobody has looked at
   this board.** A single scheduled render is needed to confirm `c4` reads as a
   board on screen and is not occluded by `grass`, `weed_plants`, `leaves` or
   `stones`, all of which are dense in this area (1.05 M / 113 k / 28 k / 185 k verts).

2. **"Short boards propped upright" vs "long boards lying almost flat" — not fully
   excluded.** The lean magnitudes (2.35–12.70°) and the fact that the wall contact
   sits at each slab's thin top *end* edge for c1–c4 both indicate short boards
   propped upright. But a long board lying almost flat and propped at one end
   would produce a superficially similar signature, and my method cannot recover a
   face the artist deleted. My triangle-overlap test on `wooden_boards.001 c0`
   returns **only** `leaves` and `stones` — it does **not** confirm c0 physically
   crosses any other board. **I am not claiming the boards form a leaning stack
   resting on each other.**

3. **The `lean_from_vertical_deg` definition bit me and I fixed it.** My first
   version reported `90 − (thickness-axis tilt)` for *all* components, which is
   only correct when the board's long axis is vertical. For `wooden_boards.001 c3`
   and `c4` the long axis is **horizontal**, and the formula returned **82.9°** and
   **77.3°** for boards that actually lean **7.1°** and **12.7°**. Any report
   quoting ~83° for these boards is using the broken convention. The corrected
   definition is the tilt of the slab's near-vertical in-plane axis.

4. **Which surface is "the floor"** near the wall is unsettled:
   `base_tripple_01.003` top is z = 0.0097, `Floor_main` top is z = −0.040, and the
   `stones`/`grass`/`leaves` scatter occupies z ≈ −0.155…0.0. The board's lowest
   vertex sits at z = 0.009686 (on the plinth), but a can rolling toward it would
   travel on a different surface.

5. **Whether a can can actually topple this board is NOT established and is NOT
   claimed.** The `toppling_geometry` block reports static tip angle and moment
   arms as pure geometry. For the recommendation the static tip angle is **1.995°**
   versus a **12.697°** actual lean, so the board is already ~6.4× past its static
   tip threshold — i.e. it stays up because it is propped, and the question is
   whether a can can remove that prop. **No impact test has been run.** Per V5.6
   §5.1.5 I am not asserting a topple from contact geometry.

6. **Physical placement is uncertain.** The boards lean against the wall on the
   **same side the can must approach from**. The wall blocks motion toward it, so a
   can cannot topple a leaning board by pushing it wallward; it can only drive the
   foot outward (rotating the board about its top wall contact) or slide it along
   the wall. This is a head-on low hit. **Hypothesis, not measurement.**

7. **Artist intent unknown.** A 7–13° tilt plus a millimetre-scale wall gap is
   consistent with a deliberately placed leaning board, and equally consistent
   with an approximately placed prop. This is inferred from geometry, not documented.

8. **The support OBJ is not a watertight solid** and includes scattered `stones`
   geometry. A solver should treat it as static obstacle geometry only. `grass`
   and `leaves` were **omitted entirely** (too large); only `stones` polygons
   inside the clip box are included.

9. **The camera does not see the rejected group at all.** The scene camera sits at
   y = −4.4245 with measured forward vector `(0.000001, 1.000000, 0.000027)` — it
   looks toward **+Y**. `wooden_boards` (y = −5.13) and `.002` (y = −5.07) are
   **behind** it. I confirmed this two ways: every component's NDC depth is
   negative, and each NDC box lies outside [0,1]. This means the "1367 meshes"
   scene contains a whole gate assembly the reference frame never shows.

---

## 7. Deliverables

* Report: `outcomes/v56/hidden_alley_can_board/board_selection.json`
* Boards + support: `outcomes/v56/hidden_alley_can_board/boards/`
* This note: `log/V5.6_execution/A_board_extraction.md`
* Raw evidence: `outcomes/v56/hidden_alley_can_board/_work/` (`analysis.json`,
  `components.json`, `components_weld1mm.json`, `topology.txt`, `view_probe.json`,
  `view_map.txt`, `scene_aabb_index.json`, `verification.json`)
