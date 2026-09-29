# V5.6 §3 finding: PyBullet places a `GEOM_MESH` centre of mass at the OBJ file origin

Found 2026-09-29 ~15:00 (+08:00) while re-verifying the box candidates, and checked against our own
pipeline the same hour. Tool: `tools/v56/check_com_origin.py`.

## 1. The finding

This PyBullet build (`202010061`) places a `GEOM_MESH` body's **centre of mass at the OBJ file's own
origin**. It does not compute the centroid from the geometry. The demonstration that established it
was decisive: an upright box proxy whose base sat at `z = 0` in the file had its COM **on the floor**,
so gravity restored it upright however far it was tipped — a box released **70° past its balance
point sprang back to standing**. The identical hull toppled correctly once an explicit inertial-frame
offset of `[0, 0, H/2]` was supplied. A hand-made exact-box OBJ failed the same way, so the cause is
the harness, not the asset geometry.

`MultibodySolver` builds every body as

```python
pb.createMultiBody(mass, pb.createCollisionShape(pb.GEOM_MESH, fileName=...),
                   basePosition=..., baseOrientation=...)
```

with **no `baseInertialFramePosition`**, so for our pipeline the file origin *is* the COM.

## 2. Why our pipeline is nevertheless correct here — measured, not assumed

The pipeline's proxy convention is that a collision proxy is **recentred so that its AABB centre is
the mesh origin**, and `position_m` denotes that centre. Under that convention the COM lands on the
geometric centre, which is the right place.

That is a convention that has to *hold*, so it was measured rather than trusted. Every collision proxy
in the delivered stage-05 run was checked:

| proxy | dims (m) | AABB centre offset from file origin | COM above lowest point |
| --- | --- | --- | --- |
| `bottle_assembly_collision.obj` | 0.10959 × 0.10951 × 0.29592 | **0.000 mm** | 147.961 mm → can topple |
| `glass_a_collision.obj` | 0.08070 × 0.08070 × 0.10439 | **0.042 mm** | 52.197 mm → can topple |
| `glass_b_collision.obj` | 0.08070 × 0.08070 × 0.10439 | **0.104 mm** | 52.197 mm → can topple |
| `striker_vessel_collision.obj` | 0.12998 × 0.12998 × 0.18513 | **0.000 mm** | 92.564 mm → can topple |
| `environment_static_collision.obj` | (static) | — | — |

**Result: all four dynamic proxies are recentred on their own origin to within 0.104 mm, so every COM
landed at the geometric centre.** The V5.5 stage-05 results — 89.015 mm translation, 79.419° tilt,
first contact at step 170 — are therefore **not** affected by this bug, and the delivered sample
stands. Evidence: `outcomes/v55/italian_flat/box_hits_bottle/20260929T110000/com_origin_check.json`.

## 3. The independent second confirmation of §3.1

The same measurement reproduces the §3.1 number from a completely different direction. `glass_b`'s
proxy spans 0.10439 m in z, so its centre sits **52.197 mm** above its lowest point — exactly the
half-height that §3.1 identified, and exactly the lift the legacy `anchor_of(..., "centre_zmin")`
applied to the visual. Two independent measurements now agree to the thousandth of a millimetre:

| source | value |
| --- | --- |
| §3.1: `bodies.json` centre z 0.563786922 − tray floor 0.510600 | 52.197 mm |
| this check: proxy z-extent 0.10439 m ÷ 2 | 52.197 mm |
| `test_body_visual.py` legacy-binding regression | 52.197 mm |

## 4. What this means going forward, and the one place it could still bite

1. **`baseInertialFramePosition` is now a declared requirement.** Any GSO or scene mesh used as a
   dynamic collider must either be recentred on its AABB centre, or have its inertial frame set
   explicitly. `check_com_origin.py` is the gate for it: it exits non-zero when a proxy is not
   recentred, so the condition cannot pass silently.
2. **This is the live risk for video B.** The box candidates are GSO assets whose
   `collision_geometry.obj` files are in *authored* coordinates, not recentred. If used directly they
   would get a misplaced COM. Video B will therefore build its own fitted proxies for the boxes —
   which §6.1 explicitly permits ("确为长方盒可制作贴合的box/低面凸代理") — recentred on their AABB
   centre, and will run this check on them.
3. **Any earlier project result that loaded GSO collision meshes without recentring should be
   regarded as suspect for tipping behaviour until re-checked.** Within this repository the delivered
   stage-05 run is the one that matters and it has now been checked and cleared. The stage-08 box
   screening was a geometric measurement, not a physics result, so it is unaffected.
4. **Disclosure.** This is a genuine harness-level trap: it fails silently and produces a body that
   looks correct but cannot be knocked over. It is recorded here rather than absorbed, and the check
   is committed so that the next person hits the error message rather than the wrong physics.
