"""Corrected body->visual binding for replaying a solved trajectory (V5.6 section 3.1, 3.2).

Pure Python with its own 4x4 matrix maths and no bpy import, so the regression tests in
`test_body_visual.py` run in the control interpreter in under a second and the correctness of the
transform does not depend on Blender being available.

WHY THE OLD BINDING WAS WRONG
-----------------------------
The solver records, for each body, a `position_m` and a `quaternion_xyzw`. Those describe the BODY
frame. For a prop, the body frame is the collision proxy's local frame, and the proxy was recentred
before use so that its AABB centre sits at the proxy's local ORIGIN. So `position_m` is the world
position of the proxy's AABB CENTRE -- in all three axes.

`v55_render_05.py::anchor_of(obj, "centre_zmin")` instead treated `position_m` as "AABB centre in x
and y, AABB MINIMUM in z", and built the initial matrix as

    m0 = Translation(p0 - R0 @ anchor) @ R0.to_4x4()

Two defects follow, and they are independent:

  * **The 52 mm lift (3.1).** For `glass_b` the collision mesh spans z in [-0.052197, +0.052197], so
    its centre is 52.2 mm above its base, while the visual cup's anchor was taken as the base. The
    visual was therefore raised by 52.2 mm: the recorded base 0.511590 m (against a tray top of
    0.510600 m) was rendered at 0.563787 m, which is the floating cup in the decoded frames. The
    fix is not to subtract a compensating offset -- that would only move the error to another object
    -- but to stop deriving the body frame from the visual at all.

  * **The lost scale (3.2).** `R0.to_matrix().to_4x4()` discards the authored scale, and only
    location and rotation are keyframed, so a non-unit-scale object changes size on replay.

THE CORRECT BINDING
-------------------
Keep the body->visual transform fixed, and move the visual with the body:

    T_WV(t) = T_WB(t) @ inverse(T_WB(0)) @ T_WV(0)

Every term is a full 4x4. `T_WV(0)` is the authored visual world matrix INCLUDING scale and any
local offset, captured once from the runtime copy. `T_WB(0)` and `T_WB(t)` come only from the
recorded trajectory. Nothing is inferred from the visual's bounding box, so the 52 mm class of error
cannot occur, and no per-frame fudge factor is possible.

Because `T_WV(0)` is used verbatim, an assembly's visual parts each keep their own relative matrices:
each part gets the same body transform applied to its own authored initial matrix, which preserves
the assembly's internal layout exactly.
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------------------
# minimal 4x4 matrix and quaternion maths
# ---------------------------------------------------------------------------------------
#
# Implemented here rather than imported so this module has no dependency beyond the standard library.
# Matrices are row-major nested tuples: m[row][col], acting on column vectors.


def mat_identity():
    return ((1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0))


def mat_mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4))
                 for i in range(4))


def mat_translation(v):
    return ((1.0, 0.0, 0.0, float(v[0])),
            (0.0, 1.0, 0.0, float(v[1])),
            (0.0, 0.0, 1.0, float(v[2])),
            (0.0, 0.0, 0.0, 1.0))


def mat_scale(s):
    return ((float(s[0]), 0.0, 0.0, 0.0),
            (0.0, float(s[1]), 0.0, 0.0),
            (0.0, 0.0, float(s[2]), 0.0),
            (0.0, 0.0, 0.0, 1.0))


def mat_quat_xyzw(q):
    """Rotation matrix from a quaternion in xyzw order, which is the project's contract."""
    x, y, z, w = (float(c) for c in q)
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n < 1e-15:
        return mat_identity()
    x, y, z, w = x / n, y / n, z / n, w / n
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return ((1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy), 0.0),
            (2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx), 0.0),
            (2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy), 0.0),
            (0.0, 0.0, 0.0, 1.0))


def mat_inverse(m):
    """General 4x4 inverse by Gauss-Jordan with partial pivoting.

    General rather than assuming a rigid transform, because `T_WV(0)` legitimately carries scale.
    """
    a = [list(row) + [1.0 if i == j else 0.0 for j in range(4)] for i, row in enumerate(m)]
    for col in range(4):
        piv = max(range(col, 4), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-15:
            raise ValueError("singular matrix")
        a[col], a[piv] = a[piv], a[col]
        pv = a[col][col]
        a[col] = [v / pv for v in a[col]]
        for r in range(4):
            if r == col:
                continue
            f = a[r][col]
            if f:
                a[r] = [v - f * w for v, w in zip(a[r], a[col])]
    return tuple(tuple(row[4:]) for row in a)


def apply(m, p):
    """Transform a 3D point (w = 1), returning a 3-tuple."""
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def mat_from_trs(translation, quat_xyzw, scale=(1.0, 1.0, 1.0)):
    return mat_mul(mat_translation(translation), mat_mul(mat_quat_xyzw(quat_xyzw), mat_scale(scale)))


# ---------------------------------------------------------------------------------------
# the body frame, and the corrected binding
# ---------------------------------------------------------------------------------------


def body_world(position_m, quaternion_xyzw):
    """The body frame in world space at one recorded instant.

    The collision proxy is recentred so its local origin is its AABB centre, and it is placed with
    identity orientation at frame 0, so the recorded position IS the body origin. No AABB of the
    visual mesh is consulted -- that was the source of the 52 mm lift.
    """
    return mat_mul(mat_translation(position_m), mat_quat_xyzw(quaternion_xyzw))


def visual_world_matrix(t_wb_t, t_wb_0, t_wv_0):
    """V5.6 section 3.2: T_WV(t) = T_WB(t) * inverse(T_WB(0)) * T_WV(0)."""
    return mat_mul(t_wb_t, mat_mul(mat_inverse(t_wb_0), t_wv_0))


def initial_visual_matrix(source_world, runtime_world):
    """`T_WV(0)`, the visual's initial world matrix, from the runtime copy.

    The runtime copy is what is rendered, so its matrix is the one to use. `source_world` is passed
    for the alignment report rather than for use here; a mismatch between the two is a stage-03
    alignment question and is reported rather than silently corrected here.
    """
    return runtime_world


# ---------------------------------------------------------------------------------------
# the superseded implementation, kept so the regression test can demonstrate it failing
# ---------------------------------------------------------------------------------------


def legacy_visual_world_matrix(p0, q0, p_t, q_t, t_wv_0, anchor_local):
    """The previous binding, reproduced exactly so the regression test can prove it is wrong.

    It builds `m0 = Translation(t0 - R0 @ anchor) @ R0`, which (a) drops the scale carried by
    `t_wv_0`, and (b) forces the visual's AABB-derived `anchor_local` onto the recorded body
    position instead of letting `position_m` denote the body origin.
    """
    r0 = mat_quat_xyzw(q0)
    anchored = apply(r0, anchor_local)
    t0 = (t_wv_0[0][3], t_wv_0[1][3], t_wv_0[2][3])
    m0 = mat_mul(mat_translation((t0[0] - anchored[0], t0[1] - anchored[1], t0[2] - anchored[2])),
                 r0)
    rel = mat_mul(mat_translation(p_t),
                  mat_mul(mat_quat_xyzw(q_t),
                          mat_mul(mat_inverse(mat_quat_xyzw(q0)),
                                  mat_translation((-p0[0], -p0[1], -p0[2])))))
    return mat_mul(rel, m0)


def local_aabb_anchor(vertices):
    """The anchor the legacy code derived from the visual mesh: centre in x/y, minimum in z."""
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, min(zs))


def max_point_error(predicted, reference):
    """Largest distance between corresponding points, in metres."""
    if len(predicted) != len(reference):
        raise ValueError("point counts differ")
    return max(math.dist(p, r) for p, r in zip(predicted, reference))
