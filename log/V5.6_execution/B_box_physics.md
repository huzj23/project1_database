# V5.6 B — Box physics re-verification: can these three GSO game boxes act as dominoes?

**Deliverable JSON:** `outcomes/v56/mixed_box_domino/box_physics_test.json`
**Scripts:** `tools/v56/b_*.py` (all measurements were made on the server, which has pybullet)
**Engine:** pybullet API `202010061` (server conda env), floor = large `GEOM_BOX`

---

## Headline

**The earlier "only one usable box" conclusion is REFUTED.**

The earlier conclusion came from a shape metric — strike-face flatness coverage ≥ 0.85 — which the
new plan explicitly demotes to a *screening hint*. Tested physically, **all three named assets stand
and all three topple a following box of the same kind at every requested gap (0.15h, 0.25h, 0.35h)**.
The two assets the metric rejected on strike-face coverage (Trivial Pursuit 0.210, Ouija 0.266)
perform just as well as the one it accepted (Cranium 0.967). Ouija is in fact the most reliable of
the three. Strike-face flatness is not a valid predictor of domino capability.

---

## 1. Dimensions, mass and the density used

Dimensions are the real `collision_geometry.obj`, measured in each object's **own frame** recovered
from its face normals (GSO assets are scans stored in arbitrary poses, so the stored axes are not the
box's axes). Axes are ordered `[thickness, width, height]`.

| Asset | thickness | width | height | h/t | w/t | hull volume | **assigned mass** |
|---|---|---|---|---|---|---|---|
| Cranium | 55.838 mm | 207.669 mm | 272.574 mm | 4.88 | 3.72 | 3.1245e-3 m³ | **0.6249 kg** |
| Trivial Pursuit | 73.462 mm | 209.265 mm | 272.852 mm | 3.71 | 2.85 | 3.5297e-3 m³ | **0.7059 kg** |
| Ouija | 62.497 mm | 275.466 mm | 408.406 mm | 6.54 | 4.41 | 6.2552e-3 m³ | **1.2510 kg** |

**Density used: 200 kg/m³** (uniform solid over the measured convex-hull volume).

*Why that density.* The library's URDF masses are **scan artefacts and were not used**. The proof is
in the numbers: each recorded mass equals that asset's **visual** hull volume numerically —
Cranium `0.0028040457` vs visual hull `0.0028040457`, Trivial Pursuit `0.0032490056` vs
`0.0032490056`, Ouija `0.0054948609` vs `0.0054948609`. These are unit-density artefacts, not masses.
200 kg/m³ models a light, mostly-air hollow retail game box: far below solid paperboard (~700) and
far above the artefact. Because gravitational torque *and* inertia both scale linearly with density,
the dynamics should be density-invariant — and this was **tested, not assumed**: every case was
repeated at 100, 200 and 600 kg/m³ with identical outcomes (see §4).

## 2. Standing stability — all three stand

Run for 20 s with no trigger, at two spawn clearances (0.5 mm, 0.05 mm) and five yaw angles
(0°, 45°, 90°, 135°, 180°). None of the three ever falls over.

| Asset | final tilt | max tilt over run | tilt drift over last 10 s | verdict |
|---|---|---|---|---|
| Cranium | 0.46° | 1.15° | **0.0000000 °/s** | static rest |
| Trivial Pursuit | 0.79° | 1.37° | 0.0012686 °/s | static rest |
| Ouija | 2.65° | 4.13° | **0.0000000 °/s** | static rest |

All three settle into a **static but slightly tilted pose** — the tilt is constant and the drift over
the final 10 s is zero to within 0.0009 °/s, so these are not rocking or creeping. The cause is the
scanned base, and the hull geometry shows it directly: only **7, 6 and 2** vertices (of 54/64/64)
lie within 1 mm of the base plane, with base z-spreads of 0.82 mm, 0.36 mm and 0.09 mm. Ouija's
2.65° lean is the largest and its base contact is the narrowest (**17%** of its nominal thickness
extent, vs 95% for Cranium), so it is the least clean stander — but it does not fall.

*A first-pass 2 s snapshot flagged two boxes as "not at rest" using a strict zero-tilt test. The 20 s
convergence runs show that was a flaw in the criterion, not instability: the boxes reach a static
tilted pose almost immediately and then do not move.*

## 3. Two-box toppling — all three topple, and at what gap

Striker A upright, target B upright ahead at a clear face-to-face gap expressed as a fraction of the
**shorter box's height**. A is rotated about its own front bottom edge and nothing further is applied.

Primary push ω₀ = 3.0 rad/s — an ordinary finger push, **1.6× to 3.3× each box's own critical
tipping speed** ω_crit (Cranium 1.47, Trivial Pursuit 1.89, Ouija 0.91 rad/s).

| Asset | gap | gap (mm) | A toppled | contact? | B toppled | B tilt | B pushed |
|---|---|---|---|---|---|---|---|
| Cranium | 0.15h | 40.9 | yes | yes | **yes** | 90.8° | 173 mm |
| Cranium | 0.25h | 68.1 | yes | yes | **yes** | 91.6° | 181 mm |
| Cranium | 0.35h | 95.4 | yes | yes | **yes** | 91.7° | 189 mm |
| Trivial Pursuit | 0.15h | 40.9 | yes | yes | **yes** | 91.4° | 183 mm |
| Trivial Pursuit | 0.25h | 68.2 | yes | yes | **yes** | 91.3° | 196 mm |
| Trivial Pursuit | 0.35h | 95.5 | yes | yes | **yes** | 90.7° | 193 mm |
| Ouija | 0.15h | 61.3 | yes | yes | **yes** | 92.3° | 245 mm |
| Ouija | 0.25h | 102.1 | yes | yes | **yes** | 91.7° | 245 mm |
| Ouija | 0.35h | 142.9 | yes | yes | **yes** | 91.2° | 248 mm |

**Cross-pairs also all work:** all 6 ordered pairs at 0.25h topple (B reaching 90.7–91.6°), including
the heavy→light and light→heavy directions. All **12 mixed 3-box chains** (four asset orders × three
gaps) propagated **3/3 boxes**.

**Working gap range.** A fine sweep (0.02h→0.70h, gaps in 14 steps) shows:

* **Ouija: reliable at every gap from 0.02h to 0.70h under all 9 trigger/density settings** — the
  most forgiving of the three.
* **Cranium and Trivial Pursuit: reliable at 0.25h and above** under all settings; at 0.15h they work
  with the primary push but fail under the deliberately weak push (see §5).
* The gap is best understood relative to the striker's **own thickness**: the reliable region starts
  once the gap exceeds about **1.0–1.2× the striker's thickness** (Cranium 1.22×, Trivial Pursuit
  0.93×, Ouija works from 0.13×).

## 4. Density and trigger sweeps

* **Density** (100 / 200 / 600 kg/m³): outcomes identical at all three densities for all three
  assets — confirming the expected mass-invariance, and showing the result does not depend on the
  density choice in §1.
* **Push strength** (1.0 / 2.0 / 3.0 / 4.5 rad/s at 0.25h): 1.0 rad/s is below ω_crit for Cranium
  and Trivial Pursuit, so nothing topples — as the analytic tipping barrier predicts. At 2.0 rad/s
  and above, **every asset topples the target**, with B reaching 90–92°.

## 5. Where a box fails, and exactly how

Only one marginal regime exists, and it is a **trigger-strength effect, not an asset defect**:

At the smallest gaps (≤0.20h) with the **weak** push ω₀ = 2.0 rad/s — which is only **1.06×** ω_crit
for Trivial Pursuit and **1.36×** for Cranium — the striker leans onto the target and stops instead
of toppling it. Measured: A tilts only 5.99° (Cranium) / 7.39° (Trivial Pursuit) at 0.02h; contact
*is* made, but B tilts only 8.27° / 9.40° and stays up. At 0.15h the same weak push gives A 7.83° /
10.13° and B 1.99° / 2.77°.

*Why it happens:* at a gap smaller than roughly the striker's own thickness there is no room for the
striker to rotate before it meets the target, so it jams against it as a prop rather than pivoting
past its balance point. Raising the push to 3.0 rad/s makes 0.15h work for both; Ouija, whose ω_crit
is much lower, is never affected.

*Honest note on the mechanism:* I tested whether the transferable energy at first contact explains
these failures (striker rotational KE vs the target's tipping barrier). It does **not** separate the
groups cleanly — the worst success had a lower energy ratio (0.54) than the best failure (0.93) — so
the marginal failures are best described as a **borderline threshold with overlap**, correlated with
the trigger sitting close to ω_crit, rather than attributable to one clean mechanism. All three
**requested** gaps are clear of this regime under a normal push.

## 6. Collision proxy vs visual mesh (item 5)

Measured on the **same axes** (the collision's own frame). The collision hull is **larger than the
visual on every axis, but only slightly** — 0.5% to 4.1%:

| Asset | axis | collision | visual | difference | relative |
|---|---|---|---|---|---|
| Cranium | thickness | 55.838 mm | 54.855 mm | +0.983 mm | +1.79% |
| Cranium | width | 207.669 mm | 206.464 mm | +1.205 mm | +0.58% |
| Cranium | height | 272.574 mm | 270.766 mm | +1.807 mm | +0.67% |
| Trivial Pursuit | thickness | 73.462 mm | 70.781 mm | +2.682 mm | +3.79% |
| Trivial Pursuit | width | 209.265 mm | 206.963 mm | +2.302 mm | +1.11% |
| Trivial Pursuit | height | 272.852 mm | 271.049 mm | +1.804 mm | +0.67% |
| Ouija | thickness | 62.497 mm | 60.064 mm | +2.433 mm | +4.05% |
| Ouija | width | 275.466 mm | 272.248 mm | +3.218 mm | +1.18% |
| Ouija | height | 408.406 mm | 406.293 mm | +2.114 mm | +0.52% |

The growth is ≤4.1% (≤3.2 mm) on any axis, so the proxies do **not** overlap visually to any
noticeable degree. The visual and collision frames are also slightly misaligned (up to **2.6°**),
which is a second, smaller source of mismatch.

**A hard-coded engine margin, measured.** Part of that difference is not asset geometry at all.
Comparing a control `GEOM_BOX` against a control `GEOM_MESH` built from an **exactly identical** box,
at four sizes from 12 mm to 1 m:

* `GEOM_BOX`: **0.000 mm** added per side at every size.
* `GEOM_MESH`: **1.000 mm added per side** (+4 mm on the AABB), **identical at every size**.

The exact-box control is what makes this measurement valid: for a true box a raycast through the
centre along an axis must hit the extreme surface, so the difference from the known dimension is
purely engine-added. (The same raycast applied to the *real* hulls is not a valid margin probe,
because a GSO hull is not a perfect box — a raycast through the mid-height can hit a face that lies
inside the bounding extent, which is why those per-axis readings are not used to claim a margin.)

So this pybullet build applies a **fixed absolute 1 mm collision margin per side to mesh shapes**,
independent of shape size. Per the task's instruction this was verified rather than assumed, and the
result is reported honestly: **no margin could be *set*** — `collisionMargin` and `margin` are both
rejected with `"'collisionMargin' is an invalid keyword argument for this function"` on both
`GEOM_BOX` and `GEOM_MESH` (re-probed on the server, recorded verbatim in the JSON). No margin was
applied by this test; the 1 mm is an engine default that must be **predicted from**, not configured.

**No shape pathology found.** All three collision proxies are closed (edge-closedness 1.0) and
box-like (hull/bbox volume 0.99, 0.84, 0.89), with no flat-blob or near-zero-thickness problem
(thinnest extents 55.8 / 73.5 / 62.5 mm). Their bases are slightly warped, as described in §2.

## 7. A harness bug that had to be found first — and matters beyond this task

A **first draft of this very test reported that no asset topples.** That result was wrong, and the
cause is worth recording because it can silently corrupt any GSO mesh simulation in this project:

> **pybullet places a `GEOM_MESH` body's centre of mass at the OBJ's own origin.**
> The upright proxies have their base at z = 0, so without an explicit inertial frame the COM sits
> **on the floor**, and gravity then restores the box upright *however far it is tipped*.

The evidence: `getDynamicsInfo` reported `local_inertial_pos = [0, 0, 0]` for a proxy whose mid-height
is 0.136287 m; a mesh released **45° past** its balance point returned to standing at 0.46°. Setting
`baseInertialFramePosition = [0, 0, H/2]` made the **same hull** topple cleanly. Crucially, a
**hand-made exact box OBJ** loaded as `GEOM_MESH` failed *identically* — so this is an engine/harness
property, not the scanned geometry, and **not** a physical finding about the assets.

> **Action for the rest of the project:** any earlier physics result that loaded GSO collision meshes
> without setting `baseInertialFramePosition` may have a COM at the mesh origin and therefore wrong
> tipping behaviour. Worth re-checking before trusting prior physics conclusions.

## 8. Other environment facts confirmed

* `GEOM_MESH` does not collide with `GEOM_PLANE` in this build — all tests use a large `GEOM_BOX`
  floor, with a control-box self-check proving the floor works before any verdict is read.
* Margin arguments rejected on both `GEOM_BOX` and `GEOM_MESH` (see §6).
* `getPhysicsEngineParameters()` exposes no margin-related key.

## 9. Confidence, per asset

| Asset | Stands? | Topples at 0.15/0.25/0.35h? | Widest reliable range | Confidence |
|---|---|---|---|---|
| Cranium | Yes, static (0.46° tilt) | Yes / Yes / Yes | 0.25h–0.70h under all settings | **medium-high** |
| Trivial Pursuit | Yes, static (0.78° tilt) | Yes / Yes / Yes | 0.25h–0.70h under all settings | **medium-high** |
| Ouija | Yes, static (2.65° tilt, least flat base) | Yes / Yes / Yes | **0.02h–0.70h under all settings** | **high** |

**Confidence is not "high" for Cranium and Trivial Pursuit** only because their 0.15h result depends
on the push being firm (ω₀ = 2.0 rad/s fails there); everything at 0.25h and above is robust across
all triggers and densities. Ouija is robust everywhere, including the smallest gaps.

### Is this real physics or a simulation artefact?

Stated explicitly, as required:

* **Real, and cross-checked against analytics.** The trigger thresholds match the closed-form tipping
  barrier ω_crit = √(3g(√(t²+h²)−h)/(t²+h²)) for a box pivoting on its edge: at 1.0 rad/s nothing
  topples (below ω_crit), at 2.0–4.5 rad/s everything does. The density-invariance is likewise what
  the analytic scaling predicts.
* **One genuine engine artefact, quantified.** The fixed 1 mm `GEOM_MESH` margin (§6) is a
  simulation-specific effect. At these box sizes it is ≤4% of an axis, so it does not change any
  verdict, but it would matter for boxes with ~10 mm features.
* **The COM-at-mesh-origin behaviour is a simulation trap**, not physics — identified, fixed, and
  demonstrated with controls (§7).
* **Known limitation.** The boxes' warped scanned bases make the standing pose a static *tilt*
  rather than perfectly flat. This is a real geometric property of the assets (measured from the
  hull vertices), and in these runs it never led to falling; but a slightly tilted start means the
  first contact in a chain is marginally earlier than an idealised box would give.
