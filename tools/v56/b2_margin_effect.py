"""b2_margin_effect.py -- how does the GEOM_MESH margin actually change CONTACT, not just the AABB?

WHY THIS IS A SEPARATE MEASUREMENT
----------------------------------
The task's ground truth says this build applies a fixed 1.000 mm collision margin per side to mesh
shapes. The in-process `getAABB` probe in `b2_chain.py` measures the AABB growing by 4.000 mm PER
AXIS (2.000 mm per side) for exact boxes of 10 mm to 100 mm thickness, i.e. twice the stated number,
and identical at every size. An AABB that grows by m per side does NOT by itself prove that contact
is RESOLVED m outboard of the geometry: pybullet's margin is a collision-detection buffer, and
depending on the build the contact can still be solved at the true surface.

That distinction is exactly what decides the chain's gaps, because the requested gaps are 0.15-0.25 of
a 272-408 mm height, i.e. 41-102 mm, and 2 mm per side is 4 % of a Cranium's thickness. So this
script measures three things that do not depend on any theory of what a margin "is":

  1. **Resting height.** An exact mesh box of known height, dropped on the floor box, settles at some
     z. If contact is resolved at the true surface the centre is at h/2; if it is resolved m outboard
     the centre is at h/2 + m. This is a direct, unambiguous reading.
  2. **The first-contact pitch.** Two identical exact MESH boxes are placed at a known centre-to-centre
     pitch with gravity ON. The pitch at which they first touch (found by bisection on the pitch) is
     `t + 2*e` where `e` is the effective per-side outward offset. The same bisection with GEOM_BOX
     primitives gives `t + 0` if boxes have no margin, which is the control that makes the mesh number
     interpretable.
  3. **The reported contact distance.** `getContactPoints` returns a `contactDistance` per contact;
     its value at the moment of first touch says whether the solver reports separation between true
     surfaces or between grown surfaces.

Everything is measured in the same process that the chain runs in, and the box dimensions used are the
REAL proxy dimensions, not toy sizes, so the number is directly usable in the gap arithmetic.

Run on the server:
    python tools/v56/b2_margin_effect.py --proxies <dir> --out <json>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pybullet as pb

sys.path.insert(0, str(Path(__file__).resolve().parent))

GRAVITY = -9.81
DT = 1.0 / 480.0


def exact_box_obj(path: Path, dx, dy, dz):
    hx, hy, hz = dx / 2, dy / 2, dz / 2
    v = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
         (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (2, 3, 7), (2, 7, 6), (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)]
    path.write_text("\n".join(f"v {a:.12f} {b:.12f} {c:.12f}" for a, b, c in v) + "\n"
                    + "\n".join(f"f {a + 1} {b + 1} {c + 1}" for a, b, c in f) + "\n",
                    encoding="utf-8")


class W:
    def __init__(self, gravity=GRAVITY):
        self.cid = pb.connect(pb.DIRECT)
        pb.setGravity(0.0, 0.0, gravity, physicsClientId=self.cid)
        pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=200, numSubSteps=1,
                                     enableConeFriction=1, physicsClientId=self.cid)
        s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[6.0, 6.0, 0.25],
                                    physicsClientId=self.cid)
        self.floor = pb.createMultiBody(0, s, basePosition=(0.0, 0.0, -0.25),
                                        physicsClientId=self.cid)
        pb.changeDynamics(self.floor, -1, lateralFriction=0.5, restitution=0.0,
                          physicsClientId=self.cid)

    def set_gravity(self, g):
        pb.setGravity(0.0, 0.0, g, physicsClientId=self.cid)

    def close(self):
        pb.disconnect(self.cid)

    def shape(self, kind, dims, obj=None):
        if kind == "box":
            return pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[d / 2 for d in dims],
                                           physicsClientId=self.cid)
        return pb.createCollisionShape(pb.GEOM_MESH, fileName=str(obj), flags=0,
                                       physicsClientId=self.cid)

    def body(self, sh, pos, mass=0.1):
        return pb.createMultiBody(mass, sh, basePosition=pos, physicsClientId=self.cid)

    def step(self, n):
        for _ in range(n):
            pb.stepSimulation(physicsClientId=self.cid)


def resting_height(w: W, kind, dims, obj, mass=0.1, settle_s=2.0):
    """Drop an exact box and read where its centre settles. h/2 => true-surface contact."""
    sh = w.shape(kind, dims, obj)
    b = w.body(sh, (2.0, 2.0, dims[2] / 2 + 0.004), mass)
    w.step(int(settle_s / DT))
    p, _q = pb.getBasePositionAndOrientation(b, physicsClientId=w.cid)
    cps = pb.getContactPoints(bodyA=b, bodyB=w.floor, physicsClientId=w.cid)
    out = {
        "expected_centre_z_if_true_surface_m": dims[2] / 2.0,
        "measured_centre_z_m": round(p[2], 9),
        "offset_from_true_surface_m": round(p[2] - dims[2] / 2.0, 9),
        "floor_contacts": len(cps),
        "contact_distance_values_m": sorted({round(c[8], 9) for c in cps}),
        "contact_normal_z_values": sorted({round(c[7][2], 6) for c in cps}),
    }
    pb.removeBody(b, physicsClientId=w.cid)
    return out


def first_contact_pitch(w: W, kind, dims, obj, iters=30):
    """Bisect the centre-to-centre pitch at which two identical boxes first touch.

    TWO THINGS ARE DELIBERATE HERE, AND BOTH WERE GOT WRONG FIRST.
    ------------------------------------------------------------
    (a) **Direction.** For two boxes of thickness t the pair overlaps (so definitely reports contacts)
        at a pitch below t, and is definitely clear well above t. The bracket is therefore
        `[lo = touching, hi = clear]` and the bisection walks the CLEAR side down onto the touching
        side. A first version had it the other way round and grew the "touching" bound to 584 m
        without ever touching; that run is preserved in `margin_effect.json`'s history.
    (b) **Gravity must be OFF.** With gravity on, a mesh box resting on the floor sits 1 mm high
        (measured: `resting_height.exact_mesh_10mm_thick.offset_from_true_surface_m = 0.000989`), so
        two boxes at a pitch near t are not only touching but pressed, and the measured boundary is a
        contact-SOLVER threshold rather than a first-touch threshold. The first run with gravity on
        returned e = 1.319 mm at t = 40 mm and 2.767 mm at the Cranium proxy -- not a fixed margin at
        all, which is what exposed the contamination. Here gravity is zeroed, both bodies have their
        velocities zeroed every substep, so the ONLY variable is the pitch.

    The returned pitch is `t + 2*e`, `e` being the effective per-side outward offset of the collision
    surface: 0 for a shape that resolves contact at the true geometry.
    """
    dims_list = list(dims)
    t = dims_list[0]          # the pair is separated along x, the thickness axis
    n_samples = 0
    g_saved = pb.getPhysicsEngineParameters(physicsClientId=w.cid).get("gravity", None)
    w.set_gravity(0.0)

    def touches(pitch):
        nonlocal n_samples
        n_samples += 1
        sh_a = w.shape(kind, dims_list, obj)
        sh_b = w.shape(kind, dims_list, obj)
        a = w.body(sh_a, (0.0, 0.0, 3.0))
        b = w.body(sh_b, (pitch, 0.0, 3.0))
        for _ in range(4):
            pb.stepSimulation(physicsClientId=w.cid)
            pb.resetBaseVelocity(a, linearVelocity=(0, 0, 0), angularVelocity=(0, 0, 0),
                                 physicsClientId=w.cid)
            pb.resetBaseVelocity(b, linearVelocity=(0, 0, 0), angularVelocity=(0, 0, 0),
                                 physicsClientId=w.cid)
        cps = pb.getContactPoints(bodyA=a, bodyB=b, physicsClientId=w.cid)
        got = bool(cps)
        detail = ({"n": len(cps), "contactDistance_m": sorted({round(c[8], 9) for c in cps}),
                   "normal_x": sorted({round(c[7][0], 6) for c in cps})} if cps else None)
        pb.removeBody(a, physicsClientId=w.cid)
        pb.removeBody(b, physicsClientId=w.cid)
        return got, detail

    # a monotone scan first, so the bracket rests on measured behaviour rather than on a guess
    scan_p = [t * (0.5 + 0.25 * i) for i in range(17)]      # 0.5t .. 4.5t
    scan = [touches(p)[0] for p in scan_p]
    flips = sum(1 for i in range(len(scan) - 1) if scan[i] != scan[i + 1])
    monotone = (flips == 1)
    first_clear = next((scan_p[i] for i in range(len(scan)) if not scan[i]), None)
    last_touch = next((scan_p[i] for i in reversed(range(len(scan))) if scan[i]), None)
    if g_saved is not None:
        w.set_gravity(g_saved)
    if first_clear is None or last_touch is None:
        return {"error": "the monotone scan never showed both a touching and a clear pitch",
                "scan_pitches_m": [round(p, 6) for p in scan_p], "scan_touches": scan,
                "samples": n_samples, "touches_is_monotone_in_pitch": bool(monotone),
                "gravity_used_m_s2": 0.0}
    if not monotone:
        return {"error": "touches is not monotone in the pitch; a bisection here would be "
                         "meaningless", "scan_pitches_m": [round(p, 6) for p in scan_p],
                "scan_touches": scan, "samples": n_samples, "gravity_used_m_s2": 0.0}

    lo, hi = last_touch, first_clear          # lo touches, hi is clear
    w.set_gravity(0.0)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if touches(mid)[0]:
            lo = mid
        else:
            hi = mid
    if g_saved is not None:
        w.set_gravity(g_saved)
    pitch = 0.5 * (lo + hi)
    e = (pitch - t) / 2.0
    return {
        "first_contact_pitch_m": round(pitch, 8),
        "thickness_m": t,
        "effective_per_side_offset_m": round(e, 8),
        "effective_total_gap_added_m": round(pitch - t, 8),
        "final_bracket_width_m": round(hi - lo, 12),
        "touches_is_monotone_in_pitch": True,
        "scan_touches": scan,
        "scan_pitches_m": [round(p, 6) for p in scan_p],
        "samples": n_samples,
        "gravity_used_m_s2": 0.0,
        "contact_detail_at_just_touching": touches(lo)[1],
        "contact_detail_at_just_clear": touches(hi)[1],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxies", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--build", required=True)
    A = ap.parse_args()
    prox = Path(A.proxies)
    build = Path(A.build)
    build.mkdir(parents=True, exist_ok=True)

    cran = prox / "Hasbro_Cranium_Performance_and_Acting_Game__proxy_collision.obj"
    # read the real proxy dims from the file, rather than repeating the numbers
    def obj_dims(p):
        mn = [1e18] * 3
        mx = [-1e18] * 3
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("v "):
                q = line.split()
                for i in range(3):
                    v = float(q[i + 1])
                    mn[i] = min(mn[i], v)
                    mx[i] = max(mx[i], v)
        return [mx[i] - mn[i] for i in range(3)]
    dims = obj_dims(cran)

    out = {"pybullet_api_version": pb.getAPIVersion(), "probe": "margin effect on CONTACT",
           "real_cranium_proxy_dims_t_w_h_m": [round(d, 9) for d in dims],
           "method": ("1. resting height of an exact box (h/2 => true-surface contact). "
                      "2. bisected first-contact centre pitch between two identical boxes "
                      "(t + 2e => effective per-side outward offset e); a GEOM_BOX pair is the "
                      "control. 3. reported contactDistance at first touch.")}
    w = W()
    try:
        small = (0.055838, 0.207669, 0.272574)
        tiny = (0.04, 0.04, 0.010)
        out["resting_height"] = {}
        for label, kind, dm, ob in (
                ("exact_mesh_10mm_thick", "mesh", tiny, build / "ex_mesh_10.obj"),
                ("exact_box_10mm_thick", "box", tiny, None),
                ("exact_mesh_cranium_proxy", "mesh", tuple(dims), cran),
                ("exact_box_cranium_dims", "box", tuple(dims), None)):
            if kind == "mesh":
                exact_box_obj(ob, *dm)
            out["resting_height"][label] = resting_height(w, kind, dm, ob)
        out["first_contact_pitch"] = {}
        for label, kind, dm, ob in (
                ("exact_mesh_10mm_thick", "mesh", tiny, build / "ex_mesh_10.obj"),
                ("exact_box_10mm_thick", "box", tiny, None),
                ("exact_mesh_cranium_proxy", "mesh", tuple(dims), cran),
                ("exact_box_cranium_dims", "box", tuple(dims), None)):
            out["first_contact_pitch"][label] = first_contact_pitch(w, kind, dm, ob)
    finally:
        w.close()

    rh = out["resting_height"]
    out["conclusion"] = {
        "mesh_rests_higher_than_true_surface_m": rh["exact_mesh_10mm_thick"][
            "offset_from_true_surface_m"],
        "box_rests_at_true_surface": abs(
            rh["exact_box_10mm_thick"]["offset_from_true_surface_m"]) < 5e-4,
        "mesh_effective_per_side_offset_10mm_m": out["first_contact_pitch"][
            "exact_mesh_10mm_thick"].get("effective_per_side_offset_m"),
        "box_effective_per_side_offset_10mm_m": out["first_contact_pitch"][
            "exact_box_10mm_thick"].get("effective_per_side_offset_m"),
        "mesh_effective_per_side_offset_cranium_m": out["first_contact_pitch"][
            "exact_mesh_cranium_proxy"].get("effective_per_side_offset_m"),
    }
    Path(A.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
