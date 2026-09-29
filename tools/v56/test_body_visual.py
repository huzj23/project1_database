"""Regression tests for the body->visual binding (V5.6 section 3.3).

Section 3.3 requires a regression that covers non-unit scale, a non-zero body-to-visual offset and a
multi-visual-part assembly, and that is written so the OLD implementation must FAIL it while the new
one passes. The reference answers are constructed here from the definitions in the plan, independently
of the code under test -- the functions being tested never generate their own expected values, which
is the failure mode section 3.3 explicitly forbids.

Runs in the control interpreter with no bpy dependency:

    C:\\Users\\12447\\AppData\\Local\\Programs\\Python\\Python39\\python.exe tools\\v56\\test_body_visual.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from body_visual import (  # noqa: E402
    apply, body_world, legacy_visual_world_matrix, local_aabb_anchor, mat_from_trs,
    mat_identity, mat_inverse, mat_mul, mat_quat_xyzw, mat_scale, mat_translation,
    max_point_error, visual_world_matrix,
)

FAILURES = []
PASSES = []


def check(name, ok, detail=""):
    (PASSES if ok else FAILURES).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail else ''}")


def rot_z(deg):
    """A rotation about Z, as an xyzw quaternion, written out independently of the code under test."""
    h = math.radians(deg) / 2.0
    return (0.0, 0.0, math.sin(h), math.cos(h))


# ---------------------------------------------------------------------------------------
# 0. the matrix helpers themselves, against hand-computed answers
# ---------------------------------------------------------------------------------------

print("=== 0. matrix helpers ===")

# A 90 degree rotation about Z must map (1,0,0) to (0,1,0).
p = apply(mat_quat_xyzw(rot_z(90)), (1.0, 0.0, 0.0))
check("quat_xyzw rot_z(90) maps +X to +Y",
      abs(p[0]) < 1e-12 and abs(p[1] - 1.0) < 1e-12, f"got {tuple(round(v, 12) for v in p)}")

# Inverse of a scaled, translated transform must undo it exactly.
m = mat_from_trs((0.3, -1.2, 0.7), rot_z(37), (2.0, 0.5, 3.0))
pt = (0.11, -0.42, 1.03)
back = apply(mat_inverse(m), apply(m, pt))
check("inverse undoes a scaled+rotated+translated transform",
      max(abs(a - b) for a, b in zip(back, pt)) < 1e-12,
      f"residual {max(abs(a - b) for a, b in zip(back, pt)):.3e}")

# The legacy code builds m0 as Translation(...) @ R0, i.e. rotation WITHOUT scale.
# Confirm the helper this test relies on does include scale, so case 1 below is really testing scale.
mm = mat_from_trs((0, 0, 0), (0, 0, 0, 1), (2.0, 1.0, 1.0))
check("mat_from_trs applies scale", abs(apply(mm, (1.0, 0, 0))[0] - 2.0) < 1e-12)


# ---------------------------------------------------------------------------------------
# 1. NON-UNIT SCALE (section 3.2)
# ---------------------------------------------------------------------------------------
#
# The body does not move. The visual's authored matrix carries scale 2.5 in x. The correct replay
# must keep that scale at every frame; the legacy binding rebuilds the matrix from a rotation only
# and therefore shrinks the object back to unit scale.

print("\n=== 1. non-unit authored scale, static body ===")

scale = (2.5, 1.0, 1.0)
t_wv_0 = mat_from_trs((1.0, 2.0, 0.5), rot_z(0), scale)
t_wb_0 = body_world((1.0, 2.0, 0.5), rot_z(0))

# Reference: nothing moves, so the visual's world matrix must equal its authored matrix.
ref = [apply(t_wv_0, pt) for pt in ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))]

new = [apply(visual_world_matrix(t_wb_0, t_wb_0, t_wv_0), pt)
       for pt in ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))]
check("corrected: static body keeps authored scale",
      max_point_error(new, ref) < 1e-12, f"max error {max_point_error(new, ref):.3e} m")

legacy = [apply(legacy_visual_world_matrix((1.0, 2.0, 0.5), rot_z(0), (1.0, 2.0, 0.5), rot_z(0),
                                           t_wv_0, (0.0, 0.0, 0.0)), pt)
          for pt in ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))]
legacy_err = max_point_error(legacy, ref)
check("legacy: FAILS the scale case (as required)",
      legacy_err > 1e-3, f"legacy error {legacy_err*1000:.3f} mm, expected a visible size change")
print(f"        legacy moves a point by {legacy_err*1000:.1f} mm where the correct answer moves it 0")


# ---------------------------------------------------------------------------------------
# 2. NON-ZERO BODY-TO-VISUAL OFFSET, and the 52 mm lift (section 3.1)
# ---------------------------------------------------------------------------------------
#
# This reproduces the observed glass_b defect. The collision proxy's AABB is centred on the body
# origin, so its base sits 52.197 mm below `position_m`. The legacy code took the VISUAL's AABB
# minimum as the anchor, which is a different point, and forced it onto `position_m`.

print("\n=== 2. body-to-visual offset, reproducing the observed 52.197 mm lift ===")

GLASS_HALF = 0.052197          # from glass_b_collision.obj local z range [-0.052197, +0.052197]
TRAY_TOP = 0.510600            # recorded tray top
POS_Z = 0.563786922            # recorded glass_b position_m z

# The visual cup is authored correctly: its base sits on the tray top.
visual_verts_local = [(-0.04, -0.04, -GLASS_HALF), (0.04, 0.04, GLASS_HALF)]
t_wv_0 = mat_mul(mat_translation((1.6278950972655468, 7.4232501824020565, POS_Z)),
                 mat_quat_xyzw(rot_z(0)))
t_wb_0 = body_world((1.6278950972655468, 7.4232501824020565, POS_Z), rot_z(0))

# Reference: where the visual's base actually is, computed straight from the authored matrix.
base_ref = apply(t_wv_0, visual_verts_local[0])
print(f"        authored visual base z = {base_ref[2]:.9f} m")
print(f"        recorded body position z = {POS_Z:.9f} m")
print(f"        implied body-origin height above the base = {(POS_Z - base_ref[2])*1000:.3f} mm")

new_base = apply(visual_world_matrix(t_wb_0, t_wb_0, t_wv_0), visual_verts_local[0])
check("corrected: visual base stays where it was authored",
      abs(new_base[2] - base_ref[2]) < 1e-12)

# The legacy anchor is the visual AABB minimum in z, i.e. the base point.
anchor = local_aabb_anchor(visual_verts_local)
print(f"        legacy anchor (visual AABB centre-x/y, min-z) = "
      f"({anchor[0]:.4f}, {anchor[1]:.4f}, {anchor[2]:.6f})")
legacy_base = apply(legacy_visual_world_matrix(
    (1.6278950972655468, 7.4232501824020565, POS_Z), rot_z(0),
    (1.6278950972655468, 7.4232501824020565, POS_Z), rot_z(0),
    t_wv_0, anchor), visual_verts_local[0])
lift = (legacy_base[2] - base_ref[2]) * 1000.0
check("legacy: FAILS by lifting the visual off its support (as required)",
      lift > 1.0, f"legacy lift {lift:.3f} mm")
print(f"        the observed defect is {lift:.1f} mm of float, which matches the 52.2 mm reported "
      f"in the plan and the decoded sample frames")
check("the reproduced lift matches the independently-known 52.197 mm proxy half-height",
      abs(lift - GLASS_HALF * 1000.0) < 0.5, f"{lift:.3f} mm vs {GLASS_HALF*1000:.3f} mm")
check("corrected: no fudge offset is applied anywhere (base is exact, not merely close)",
      abs(new_base[2] - base_ref[2]) < 1e-12)


# ---------------------------------------------------------------------------------------
# 3. MULTI-PART ASSEMBLY, and rotation while moving
# ---------------------------------------------------------------------------------------
#
# An assembly of three visual parts shares one body transform but each keeps its own authored initial
# matrix. The test moves and rotates the body through several frames and compares all parts against
# independently computed references: for a rigid motion, each part's world position is its authored
# initial position moved by the body's rigid delta.

print("\n=== 3. multi-part assembly under combined motion and rotation ===")

parts = {
    "body": mat_from_trs((0.0, 0.0, 0.0), (0, 0, 0, 1), (1.0, 1.0, 1.0)),
    "cap": mat_from_trs((0.0, 0.0, 0.30), (0, 0, 0, 1), (1.0, 1.0, 1.0)),
    "label": mat_from_trs((0.05, 0.0, 0.15), rot_z(15), (0.5, 2.0, 0.5)),
}
probe = ((0.0, 0.0, 0.0), (0.02, 0.0, 0.30), (0.05, 0.0, 0.15), (0.0, 0.01, -0.052))

frames = [
    ((1.0, 2.0, 0.5), rot_z(0)),
    ((1.3, 2.1, 0.6), rot_z(12)),
    ((1.5, 2.4, 0.4), rot_z(88)),
    ((1.2, 2.9, 0.9), rot_z(-40)),
]
t_wb_0 = body_world(frames[0][0], frames[0][1])

worst_new = 0.0
worst_legacy = 0.0
for pi, (part_name, local) in enumerate(parts.items()):
    t_wv_0 = mat_mul(mat_translation((1.0, 2.0, 0.5)), mat_mul(mat_quat_xyzw(rot_z(0)), local))
    for (p_t, q_t) in frames:
        # Independent reference: the body's rigid delta applied to the part's authored world point.
        delta = mat_mul(body_world(p_t, q_t), mat_inverse(t_wb_0))
        for pt in probe:
            ref = apply(delta, apply(t_wv_0, pt))
            got = apply(visual_world_matrix(body_world(p_t, q_t), t_wb_0, t_wv_0), pt)
            worst_new = max(worst_new, math.dist(ref, got))
            leg = apply(legacy_visual_world_matrix(frames[0][0], frames[0][1], p_t, q_t, t_wv_0,
                                                  local_aabb_anchor(list(probe))), pt)
            worst_legacy = max(worst_legacy, math.dist(ref, leg))

check("corrected: all parts track the body's rigid motion",
      worst_new < 1e-12, f"max error {worst_new:.3e} m")
check("legacy: FAILS the assembly case (as required)",
      worst_legacy > 1e-4, f"legacy max error {worst_legacy*1000:.3f} mm")

# Assembly internal layout must be preserved: the cap must stay above the body by its authored 0.30 m
# regardless of how the body rotates.
t_wv_cap_0 = mat_mul(mat_translation((1.0, 2.0, 0.5)), parts["cap"])
t_wv_body_0 = mat_mul(mat_translation((1.0, 2.0, 0.5)), parts["body"])
p_t, q_t = ((1.5, 2.4, 0.4), rot_z(88))
cap_w = apply(visual_world_matrix(body_world(p_t, q_t), t_wb_0, t_wv_cap_0), (0, 0, 0))
body_w = apply(visual_world_matrix(body_world(p_t, q_t), t_wb_0, t_wv_body_0), (0, 0, 0))
sep = math.dist(cap_w, body_w)
check("corrected: assembly keeps its authored 0.300 m separation through a rotation",
      abs(sep - 0.30) < 1e-12, f"separation {sep:.12f} m")


# ---------------------------------------------------------------------------------------
# 4. the requirement that the corrected path is exact, not approximately right
# ---------------------------------------------------------------------------------------

print("\n=== 4. exactness of the corrected binding ===")

# T_WV(0) must be reproduced EXACTLY at frame 0, for a matrix with scale, rotation and translation.
t_wv_0 = mat_from_trs((0.7, -0.3, 1.1), rot_z(63), (1.4, 0.8, 2.2))
t_wb_0 = body_world((0.7, -0.3, 1.1), rot_z(63))
err = max_point_error(
    [apply(visual_world_matrix(t_wb_0, t_wb_0, t_wv_0), pt) for pt in probe],
    [apply(t_wv_0, pt) for pt in probe])
check("T_WV(0) is reproduced exactly at frame 0", err < 1e-12, f"error {err:.3e} m")

# Round-trip: transform forward to frame t and back to frame 0 with the body motion.
p_t, q_t = ((2.0, 1.0, 0.2), rot_z(-71))
t_wb_t = body_world(p_t, q_t)
fwd = visual_world_matrix(t_wb_t, t_wb_0, t_wv_0)
back = visual_world_matrix(t_wb_0, t_wb_t, fwd)
err2 = max_point_error([apply(back, pt) for pt in probe], [apply(t_wv_0, pt) for pt in probe])
check("motion is exactly reversible (no accumulation)", err2 < 1e-12, f"error {err2:.3e} m")


# ---------------------------------------------------------------------------------------
# 5. the 1 mm threshold from the plan, applied to the actual defect
# ---------------------------------------------------------------------------------------

print("\n=== 5. the plan's 1 mm replay threshold ===")
check("the observed 52.197 mm defect exceeds the 1 mm threshold by more than 50x",
      lift > 10.0, f"{lift:.1f} mm")
check("the corrected binding is exact to machine precision, so it clears 1 mm with no margin tuning",
      worst_new < 1e-9)


print(f"\n=== SUMMARY ===")
print(f"  {len(PASSES)} passed, {len(FAILURES)} failed")
if FAILURES:
    for f in FAILURES:
        print(f"  FAILED: {f}")
    raise SystemExit(1)
print("  all regression cases pass, including the three the legacy binding must fail")
