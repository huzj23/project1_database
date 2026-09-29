"""V5.6 B steps 2-3: the PHYSICAL domino test for the three named box candidates.

Why this script exists
----------------------
An earlier measurement concluded that only ONE box in the library is usable as a domino, using a
shape metric (strike-face flatness coverage >= 0.85). The plan states that metric is only a
SCREENING HINT and cannot prove that a closed flat-bottomed box fails to knock over another box.
This script answers the physical question in pybullet instead of by shape:

  1. STANDING STABILITY -- each box alone on a flat floor, ~2 s, no trigger. A box that will not
     stand still is unusable regardless of its shape metric.
  2. TWO-BOX COLLISION -- striker A upright, target B upright `gap` ahead, gap a fraction of the
     SHORTER box's height (0.15h, 0.25h, 0.35h). A is tipped about its own front bottom edge and the
     run records: did A topple, did A actually CONTACT B, did B topple, and B's rotation and
     translation.

THE CRITICAL HARNESS DETAIL (found by control experiment, and the reason an earlier draft of this
test produced a false "nothing topples" result):

    pybullet places a GEOM_MESH body's centre of mass at the OBJ's OWN ORIGIN. The upright proxies
    are written with the box's base at z = 0, so a mesh body created without an explicit inertial
    frame has its COM ON THE FLOOR. Gravity then restores the box upright no matter how far it is
    tipped -- a mesh released 70 deg PAST its balance point sprang back to standing, which no rigid
    box can do. `baseInertialFramePosition` must therefore be set to the true COM ([0, 0, H/2] for a
    proxy whose origin is at the base). Control runs proving this are in `b_control2.py` /
    `b_rootcause.py`: the identical hull topples cleanly once the COM is fixed, and a hand-made
    EXACT box OBJ as GEOM_MESH fails identically when it is not, so this is a harness bug and not a
    property of the scanned geometry.

Other environment facts respected here, re-checked rather than assumed:

  * This pybullet build (202010061) REJECTS a collision-margin argument on GEOM_BOX and GEOM_MESH.
    `probe_margin_api()` records the literal rejections, so no margin is claimed to be applied.
  * GEOM_MESH does not collide with GEOM_PLANE in this build, so the floor is a large GEOM_BOX.
  * URDF masses are scan artefacts (these game boxes record 0.0028 kg, which is numerically their
    visual hull volume). Mass is assigned as density x measured hull volume, and the run is repeated
    at other densities to show the outcome does not hinge on that choice.

Writes `outcomes/v56/mixed_box_domino/box_physics_test.json` on the server.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pybullet as pb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b_geom  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
GSO = ROOT / "models/gso"
OUT = ROOT / "outcomes/v56/mixed_box_domino"
BUILD = OUT / "build"
OUT.mkdir(parents=True, exist_ok=True)
BUILD.mkdir(parents=True, exist_ok=True)

ASSETS = [
    "Hasbro_Cranium_Performance_and_Acting_Game",
    "Hasbro_Trivial_Pursuit_Family_Edition_Game",
    "Supernatural_Ouija_Board_Game",
]

DT = 1.0 / 240.0
GRAVITY = -9.81
SOLVER_ITERS = 120

#: Mass = DENSITY x measured hull volume. The library's URDF masses are scan artefacts, so they are
#: not used. 200 kg/m^3 represents a light, mostly-air hollow retail game box -- well below solid
#: paperboard (about 700) and well above the artefact. Because gravitational torque AND inertia both
#: scale linearly with density, the toppling dynamics are expected to be density-invariant; the
#: density sweep TESTS that rather than asserting it.
DENSITY_PRIMARY = 200.0
DENSITY_SWEEP = (100.0, 600.0)

FRICTION_BOX = 0.5
FRICTION_FLOOR = 0.5
RESTITUTION = 0.0

SETTLE_S = 1.0
STANDING_S = 2.0          # the task's ~2 s standing test
SIM_S = 4.0
CLEARANCE_M = 0.0005

#: Trigger: a pure rotation about A's own front bottom edge at omega0 rad/s.
#:
#: The speed is NOT arbitrary. A box of thickness t and height h tips about that edge only if the
#: trigger supplies the energy to raise the COM from h/2 to hypot(t,h)/2, giving a MINIMUM angular
#: speed w_crit = sqrt(3 g (hypot(t,h) - h) / hypot(t,h)^2), independent of mass. For these three
#: assets w_crit = 1.467, 1.892 and 0.905 rad/s. A first draft used 0.30 rad/s, which is BELOW all
#: three: no box could have toppled and the run would have "proved" a failure that was purely an
#: under-powered push. The primary trigger is 3.0 rad/s, comfortably above every w_crit (1.6x to
#: 3.3x; edge speeds 0.42-0.62 m/s, an ordinary finger push), and the sweep includes 1.0 rad/s,
#: which is below two of the three, so the transition is measured rather than assumed.
OMEGA0 = 3.0
OMEGA0_SWEEP = (1.0, 2.0, 3.0, 4.5)

GAP_FRACTIONS = (0.15, 0.25, 0.35)
TOPPLE_DEG = 60.0
TIPPED_DEG = 15.0


def quat_to_matrix(q):
    R = pb.getMatrixFromQuaternion(q)
    return [[R[0], R[1], R[2]], [R[3], R[4], R[5]], [R[6], R[7], R[8]]]


def tilt_deg(q) -> float:
    """Angle between the body's own up axis and world up, in degrees."""
    return math.degrees(math.acos(max(-1.0, min(1.0, pb.getMatrixFromQuaternion(q)[8]))))


def yaw_of(q) -> float:
    R = pb.getMatrixFromQuaternion(q)
    return math.degrees(math.atan2(R[3], R[0]))


def classify(tilt: float) -> str:
    if tilt >= TOPPLE_DEG:
        return "toppled"
    if tilt >= TIPPED_DEG:
        return "tilted_not_toppled"
    return "standing"


# ---------------------------------------------------------------------------------------------
# proxy build
# ---------------------------------------------------------------------------------------------

SPEC: dict = {}
for aid in ASSETS:
    src = GSO / aid / "collision_geometry.obj"
    verts, tris, info = b_geom.upright_vertices(src)
    dst = BUILD / f"{aid}__upright_collision.obj"
    b_geom.write_obj(dst, verts, tris)
    t, w, h = info["thickness_m"], info["width_m"], info["height_m"]
    vol = info["hull_volume_m3"]
    L = math.hypot(t, h)
    w_crit = math.sqrt(3.0 * abs(GRAVITY) * (L - h) / (L * L)) if L > h else 0.0
    SPEC[aid] = {
        "obj": str(dst), "dims_m": info["dims_m"],
        "thickness_m": t, "width_m": w, "height_m": h,
        "hull_volume_m3": vol,
        "triangles": info["triangles"], "vertices": info["vertices"],
        # The COM of the proxy, in the proxy's own frame whose origin is the BASE centre.
        "com_local_m": [0.0, 0.0, h / 2.0],
        "tipping_math": {
            "tip_angle_deg": math.degrees(math.atan2(t, h)),
            "com_rise_to_tip_m": (L - h) / 2.0,
            "w_crit_rad_s": w_crit,
            "primary_omega0_over_w_crit": (OMEGA0 / w_crit) if w_crit > 0 else None,
            "primary_trigger_edge_speed_m_s": OMEGA0 * L / 2.0,
            "primary_trigger_sufficient": bool(OMEGA0 > w_crit),
        },
    }


def probe_margin_api() -> dict:
    """Re-check whether any collision margin can be set in this exact build, and report the errors."""
    cid = pb.connect(pb.DIRECT)
    out = {"pybullet_api_version": pb.getAPIVersion(), "attempts": {}}
    try:
        tmp = BUILD / "margin_probe.obj"
        v, t = b_geom.read_obj(GSO / ASSETS[0] / "collision_geometry.obj")
        b_geom.write_obj(tmp, v, t)
        for label, geom, kw in (
            ("GEOM_BOX:collisionMargin", pb.GEOM_BOX, {"collisionMargin": 0.001}),
            ("GEOM_BOX:margin", pb.GEOM_BOX, {"margin": 0.001}),
            ("GEOM_MESH:collisionMargin", pb.GEOM_MESH, {"collisionMargin": 0.001}),
            ("GEOM_MESH:margin", pb.GEOM_MESH, {"margin": 0.001}),
        ):
            try:
                if geom == pb.GEOM_BOX:
                    pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[0.02, 0.02, 0.005],
                                            physicsClientId=cid, **kw)
                else:
                    pb.createCollisionShape(pb.GEOM_MESH, fileName=str(tmp),
                                            physicsClientId=cid, **kw)
                out["attempts"][label] = {"accepted": True}
            except TypeError as exc:
                out["attempts"][label] = {"accepted": False, "error": str(exc)}
        params = pb.getPhysicsEngineParameters(physicsClientId=cid)
        out["engine_parameter_margin_keys"] = [k for k in params if "margin" in k.lower()]
    finally:
        pb.disconnect(cid)
    out["any_margin_accepted"] = any(a.get("accepted") for a in out["attempts"].values())
    out["conclusion"] = (
        "NO collision-margin argument is accepted by this build. No margin was applied anywhere in "
        "this test; overlap correctness rests on the measured geometry and a zero-initial-"
        "penetration check." if not out["any_margin_accepted"] else
        "a margin argument was accepted by this build")
    return out


class Harness:
    """A DIRECT pybullet world: box floor, convex-hull mesh boxes with an EXPLICIT inertial frame."""

    def __init__(self, floor_extent=1.5, floor_thickness=0.25):
        self.cid = pb.connect(pb.DIRECT)
        pb.setGravity(0.0, 0.0, GRAVITY, physicsClientId=self.cid)
        pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=SOLVER_ITERS,
                                     numSubSteps=1, enableConeFriction=1,
                                     physicsClientId=self.cid)
        s = pb.createCollisionShape(pb.GEOM_BOX,
                                    halfExtents=[floor_extent, floor_extent, floor_thickness],
                                    physicsClientId=self.cid)
        self.floor = pb.createMultiBody(0, s, basePosition=(0.0, 0.0, -floor_thickness),
                                        physicsClientId=self.cid)
        pb.changeDynamics(self.floor, -1, lateralFriction=FRICTION_FLOOR,
                          restitution=RESTITUTION, physicsClientId=self.cid)

    def close(self):
        pb.disconnect(self.cid)

    def mesh_body(self, spec: dict, mass: float, x: float, y: float = 0.0,
                  yaw_deg: float = 0.0) -> int:
        """A dynamic convex-hull body whose COM is set to the proxy's true mid-height.

        Setting `baseInertialFramePosition` is ESSENTIAL: without it pybullet uses the OBJ origin
        (the box's base) as the COM, which puts the centre of mass on the floor.
        """
        col = pb.createCollisionShape(pb.GEOM_MESH, fileName=spec["obj"], flags=0,
                                      physicsClientId=self.cid)
        if col < 0:
            raise RuntimeError(f"createCollisionShape failed for {spec['obj']} (id {col})")
        quat = pb.getQuaternionFromEuler([0.0, 0.0, math.radians(yaw_deg)],
                                         physicsClientId=self.cid)
        body = pb.createMultiBody(mass, col, basePosition=(x, y, CLEARANCE_M),
                                  baseOrientation=quat,
                                  baseInertialFramePosition=spec["com_local_m"],
                                  physicsClientId=self.cid)
        pb.changeDynamics(body, -1, lateralFriction=FRICTION_BOX,
                          restitution=RESTITUTION, physicsClientId=self.cid)
        return body

    def self_check(self) -> dict:
        half = 0.01
        s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[half] * 3, physicsClientId=self.cid)
        b = pb.createMultiBody(0.05, s, basePosition=(0.35, 0.35, half + 0.04),
                               physicsClientId=self.cid)
        for _ in range(int(1.5 / DT)):
            pb.stepSimulation(physicsClientId=self.cid)
        pos, _ = pb.getBasePositionAndOrientation(b, physicsClientId=self.cid)
        cps = pb.getContactPoints(bodyA=b, bodyB=self.floor, physicsClientId=self.cid)
        ok = abs(pos[2] - half) < 0.002 and len(cps) > 0
        pb.removeBody(b, physicsClientId=self.cid)
        return {"expected_z": half, "actual_z": pos[2], "delta_m": pos[2] - half,
                "floor_contacts": len(cps), "ok": bool(ok)}

    def step(self, n=1):
        for _ in range(n):
            pb.stepSimulation(physicsClientId=self.cid)


def verify_proxy(spec: dict, density: float) -> dict:
    """Round-trip: does pybullet see the same box the measurement recorded, with a sane COM?

    If the rewrite, the frame or the inertial frame were wrong, every run would silently use a
    different box. This loads the proxy and checks pybullet's own AABB against the recorded dims,
    plus the inertial position pybullet actually reports.
    """
    h = Harness()
    try:
        mass = density * spec["hull_volume_m3"]
        body = h.mesh_body(spec, mass, 0.0, 0.0)
        h.step(int(0.6 / DT))
        lo, hi = pb.getAABB(body, physicsClientId=h.cid)
        dyn = pb.getDynamicsInfo(body, -1, physicsClientId=h.cid)
        pos, _q = pb.getBasePositionAndOrientation(body, physicsClientId=h.cid)
        cps = pb.getContactPoints(bodyA=body, bodyB=h.floor, physicsClientId=h.cid)
        dims = [hi[i] - lo[i] for i in range(3)]
        measured = [spec["thickness_m"], spec["width_m"], spec["height_m"]]
        return {
            "pybullet_aabb_dims_m": [round(v, 6) for v in dims],
            "measured_dims_t_w_h_m": [round(v, 6) for v in measured],
            "abs_error_m": [round(abs(dims[i] - measured[i]), 6) for i in range(3)],
            "local_inertial_pos_reported": [round(v, 6) for v in dyn[3]],
            "expected_com_local_m": spec["com_local_m"],
            "com_is_at_mid_height": bool(abs(dyn[3][2] - spec["height_m"] / 2.0) < 1e-6),
            "resting_z_m": round(pos[2], 9),
            "floor_contacts": len(cps),
            "rests_on_floor": bool(len(cps) > 0 and abs(pos[2]) < 0.01),
        }
    finally:
        h.close()


pybullet_report = probe_margin_api()
proxy_check = {aid: verify_proxy(s, DENSITY_PRIMARY) for aid, s in SPEC.items()}


# ---------------------------------------------------------------------------------------------
# one experiment
# ---------------------------------------------------------------------------------------------

def run_case(striker: str, target: str, gap_frac: float, density: float,
             omega0: float = OMEGA0, standing_only: bool = False, sim_s: float = SIM_S) -> dict:
    """One simulation, returning a fully quantitative record of what happened."""
    sa, sb = SPEC[striker], SPEC[target]
    ma = density * sa["hull_volume_m3"]
    mb = density * sb["hull_volume_m3"]
    h_short = min(sa["height_m"], sb["height_m"])
    gap_m = gap_frac * h_short

    h = Harness()
    rec: dict = {
        "case": ("standing" if standing_only else "two_box"),
        "striker": striker, "target": target,
        "gap_fraction_of_shorter_height": gap_frac,
        "gap_m": gap_m, "shorter_height_m": h_short,
        "density_kg_m3": density,
        "striker_mass_kg": ma, "target_mass_kg": mb,
        "omega0_rad_s": (None if standing_only else omega0),
        "striker_thickness_m": sa["thickness_m"], "target_thickness_m": sb["thickness_m"],
    }
    try:
        rec["self_check"] = h.self_check()

        xa = 0.0
        xb = sa["thickness_m"] / 2.0 + gap_m + sb["thickness_m"] / 2.0
        body_a = h.mesh_body(sa, ma, xa)
        rec["target_x_m"] = xb
        body_b = None if standing_only else h.mesh_body(sb, mb, xb)

        h.step(int(SETTLE_S / DT))
        _pa, qa = pb.getBasePositionAndOrientation(body_a, physicsClientId=h.cid)
        rec["striker_tilt_after_settle_deg"] = tilt_deg(qa)
        rec["striker_contacts_after_settle"] = len(
            pb.getContactPoints(bodyA=body_a, bodyB=h.floor, physicsClientId=h.cid))
        if body_b is not None:
            _p_b, q_b = pb.getBasePositionAndOrientation(body_b, physicsClientId=h.cid)
            rec["target_tilt_after_settle_deg"] = tilt_deg(q_b)
            rec["target_contacts_after_settle"] = len(
                pb.getContactPoints(bodyA=body_b, bodyB=h.floor, physicsClientId=h.cid))
            rec["settle_contacts_between_a_and_b"] = len(
                pb.getContactPoints(bodyA=body_a, bodyB=body_b, physicsClientId=h.cid))

        if standing_only:
            # --- the ~2 s standing test: no trigger at all ------------------------------------
            n = int(STANDING_S / DT)
            worst_tilt = 0.0
            max_drift = 0.0
            for i in range(n):
                pb.stepSimulation(physicsClientId=h.cid)
                if i % 8:
                    continue
                p, q = pb.getBasePositionAndOrientation(body_a, physicsClientId=h.cid)
                worst_tilt = max(worst_tilt, tilt_deg(q))
                max_drift = max(max_drift, math.sqrt(p[0] ** 2 + p[1] ** 2))
            p, q = pb.getBasePositionAndOrientation(body_a, physicsClientId=h.cid)
            lin, ang = pb.getBaseVelocity(body_a, physicsClientId=h.cid)
            contacts = len(pb.getContactPoints(bodyA=body_a, bodyB=h.floor,
                                               physicsClientId=h.cid))
            rec.update({
                "standing_max_tilt_deg": worst_tilt,
                "standing_final_tilt_deg": tilt_deg(q),
                "standing_max_xy_drift_m": max_drift,
                "standing_final_speed_m_s": math.sqrt(sum(v * v for v in lin)),
                "standing_final_spin_rad_s": math.sqrt(sum(v * v for v in ang)),
                "standing_floor_contacts": contacts,
            })
            rec["standing_stable"] = bool(
                rec["standing_final_tilt_deg"] < 2.0
                and rec["standing_final_speed_m_s"] < 1e-3
                and rec["standing_final_spin_rad_s"] < 1e-3
                and contacts > 0)
        else:
            # --- trigger: rotate A about its own front bottom edge ----------------------------
            pv = (omega0 * sa["height_m"] / 2.0, 0.0, omega0 * sa["thickness_m"] / 2.0)
            pb.resetBaseVelocity(body_a, linearVelocity=pv,
                                 angularVelocity=(0.0, omega0, 0.0), physicsClientId=h.cid)
            rec["trigger_linear_velocity_m_s"] = pv

            max_tilt_a = max_tilt_b = 0.0
            a_topple_t = b_topple_t = first_contact_t = None
            contact_samples = 0
            max_contact_pts = 0
            b_xs = []
            for i in range(int(sim_s / DT)):
                pb.stepSimulation(physicsClientId=h.cid)
                if i % 4:
                    continue
                _p, qa = pb.getBasePositionAndOrientation(body_a, physicsClientId=h.cid)
                p_b, q_b = pb.getBasePositionAndOrientation(body_b, physicsClientId=h.cid)
                tA, tB = tilt_deg(qa), tilt_deg(q_b)
                max_tilt_a = max(max_tilt_a, tA)
                max_tilt_b = max(max_tilt_b, tB)
                if a_topple_t is None and tA >= TOPPLE_DEG:
                    a_topple_t = i * DT
                if b_topple_t is None and tB >= TOPPLE_DEG:
                    b_topple_t = i * DT
                cps = pb.getContactPoints(bodyA=body_a, bodyB=body_b, physicsClientId=h.cid)
                if cps:
                    contact_samples += 1
                    max_contact_pts = max(max_contact_pts, len(cps))
                    if first_contact_t is None:
                        first_contact_t = i * DT
                b_xs.append(p_b[0])

            rec.update({
                "striker_max_tilt_deg": max_tilt_a,
                "striker_toppled": bool(max_tilt_a >= TOPPLE_DEG),
                "striker_topple_time_s": a_topple_t,
                "target_max_tilt_deg": max_tilt_b,
                "target_toppled": bool(max_tilt_b >= TOPPLE_DEG),
                "target_topple_time_s": b_topple_t,
                "contact_between_a_and_b_made": bool(contact_samples > 0),
                "first_contact_time_s": first_contact_t,
                "contact_sample_count": contact_samples,
                "max_contact_points": max_contact_pts,
                "target_x_range_m": [min(b_xs), max(b_xs)],
            })

        # --- final states, after a settle so velocities are meaningful ------------------------
        h.step(int(0.5 / DT))
        pa, qa = pb.getBasePositionAndOrientation(body_a, physicsClientId=h.cid)
        va, wa = pb.getBaseVelocity(body_a, physicsClientId=h.cid)
        rec.update({
            "striker_final_tilt_deg": tilt_deg(qa),
            "striker_final_pos": [round(v, 6) for v in pa],
            "striker_final_yaw_deg": yaw_of(qa),
            "striker_final_speed_m_s": math.sqrt(sum(v * v for v in va)),
            "striker_final_spin_rad_s": math.sqrt(sum(v * v for v in wa)),
            "striker_verdict": classify(tilt_deg(qa)),
            "striker_all_contacts": len(pb.getContactPoints(bodyA=body_a,
                                                            physicsClientId=h.cid)),
        })
        if body_b is not None:
            p_b, q_b = pb.getBasePositionAndOrientation(body_b, physicsClientId=h.cid)
            vb, wb = pb.getBaseVelocity(body_b, physicsClientId=h.cid)
            rec.update({
                "target_final_tilt_deg": tilt_deg(q_b),
                "target_final_pos": [round(v, 6) for v in p_b],
                "target_translation_x_m": p_b[0] - xb,
                "target_translation_m": math.sqrt((p_b[0] - xb) ** 2 + p_b[1] ** 2 + p_b[2] ** 2),
                "target_final_yaw_deg": yaw_of(q_b),
                "target_final_speed_m_s": math.sqrt(sum(v * v for v in vb)),
                "target_final_spin_rad_s": math.sqrt(sum(v * v for v in wb)),
                "target_verdict": classify(tilt_deg(q_b)),
                "target_all_contacts": len(pb.getContactPoints(bodyA=body_b,
                                                               physicsClientId=h.cid)),
                "final_contacts_between_a_and_b": len(
                    pb.getContactPoints(bodyA=body_a, bodyB=body_b, physicsClientId=h.cid)),
            })
    finally:
        h.close()
    return rec


# ---------------------------------------------------------------------------------------------
# experiment matrix
# ---------------------------------------------------------------------------------------------

results = {
    "note": ("Physical re-verification of the three named box candidates as dominoes. The earlier "
             "shape metric (strike-face flatness coverage >= 0.85) is treated only as a screening "
             "hint; the verdict here comes from simulated contact."),
    "pybullet": pybullet_report,
    "harness_note": (
        "pybullet places a GEOM_MESH body's centre of mass at the OBJ's own origin. The upright "
        "proxies have their base at z=0, so `baseInertialFramePosition=[0, 0, H/2]` MUST be set or "
        "the COM sits on the floor and gravity restores the box upright however far it is tipped. "
        "An earlier draft of this test omitted it and produced a false 'nothing topples' result; "
        "see b_control2.py and b_rootcause.py for the control runs that established this."),
    "assumptions": {
        "density_primary_kg_m3": DENSITY_PRIMARY,
        "density_sweep_kg_m3": list(DENSITY_SWEEP),
        "density_rationale": (
            "URDF masses in this library are scan artefacts: each recorded mass is numerically "
            "equal to the asset's VISUAL hull volume in m^3, i.e. a unit-density artefact rather "
            "than a mass. Mass is therefore assigned as a uniform solid at a stated density over "
            "the measured convex-hull volume. 200 kg/m^3 represents a light, mostly-air hollow "
            "retail game box: well below solid paperboard (about 700) and well above the artefact. "
            "Gravitational torque and inertia both scale linearly with density, so the outcome is "
            "expected to be density-invariant; the density sweep TESTS that rather than assuming it."),
        "friction_box": FRICTION_BOX, "friction_floor": FRICTION_FLOOR,
        "restitution": RESTITUTION, "fixed_time_step_s": DT, "solver_iterations": SOLVER_ITERS,
        "settle_s": SETTLE_S, "standing_test_s": STANDING_S, "sim_after_trigger_s": SIM_S,
        "initial_clearance_m": CLEARANCE_M,
        "trigger": ("A is rotated about its own front bottom edge at omega0 rad/s, with the linear "
                    "velocity set consistently as omega x r so the push adds no slip. Nothing is "
                    "applied after t = 0."),
        "omega0_primary_rad_s": OMEGA0, "omega0_sweep_rad_s": list(OMEGA0_SWEEP),
        "topple_threshold_deg": TOPPLE_DEG, "tipped_threshold_deg": TIPPED_DEG,
        "gap_definition": ("clear face-to-face distance between A's front face and B's back face, "
                           "as a fraction of the SHORTER box's height"),
        "floor": "large GEOM_BOX (GEOM_MESH does not collide with GEOM_PLANE in this build)",
        "collider": ("the asset's own collision_geometry.obj, convex hull, re-expressed upright "
                     "with an explicit inertial frame"),
    },
    "spec": SPEC,
    "proxy_round_trip": proxy_check,
    "cases": [],
}

print("=" * 120)
print("V5.6 B: physical domino test (COM-corrected)")
print(f"  pybullet {pybullet_report['pybullet_api_version']}")
print(f"  margin argument accepted anywhere: {pybullet_report['any_margin_accepted']}")
for k, v in pybullet_report["attempts"].items():
    print(f"    {k:28s} accepted={v.get('accepted')} {v.get('error', '')}")

print("\n=== proxy round-trip (pybullet AABB vs measured dims; COM must be at mid-height) ===")
for aid, v in proxy_check.items():
    print(f"  {aid:44s} aabb={v['pybullet_aabb_dims_m']} measured={v['measured_dims_t_w_h_m']}")
    print(f"      COM reported {v['local_inertial_pos_reported']} (mid-height "
          f"{v['com_is_at_mid_height']})  resting_z={v['resting_z_m']:.6f} "
          f"floor_contacts={v['floor_contacts']}")

print("\n=== assigned masses and tipping energetics ===")
for aid, s in SPEC.items():
    tm = s["tipping_math"]
    print(f"  {aid:44s} t x w x h = {s['thickness_m']:.6f} x {s['width_m']:.6f} x "
          f"{s['height_m']:.6f} m  hull_vol={s['hull_volume_m3']:.9f} m^3")
    for d in (DENSITY_PRIMARY, *DENSITY_SWEEP):
        print(f"      density {d:6.1f} kg/m^3 -> mass {d * s['hull_volume_m3']:.6f} kg")
    print(f"      balance angle {tm['tip_angle_deg']:.3f} deg, COM rise "
          f"{tm['com_rise_to_tip_m']*1000:.4f} mm, w_crit {tm['w_crit_rad_s']:.4f} rad/s, "
          f"trigger w0={OMEGA0} = {tm['primary_omega0_over_w_crit']:.2f}x w_crit")

# --- standing ---------------------------------------------------------------------------------
print("\n" + "=" * 120)
print(f"=== STANDING STABILITY (single box, {STANDING_S} s, no trigger) ===")
for aid in ASSETS:
    rec = run_case(aid, aid, 0.0, DENSITY_PRIMARY, standing_only=True)
    results["cases"].append(rec)
    print(f"  {aid:44s} max_tilt {rec['standing_max_tilt_deg']:7.4f}  "
          f"final_tilt {rec['standing_final_tilt_deg']:7.4f} deg  "
          f"drift {rec['standing_max_xy_drift_m']*1000:7.4f} mm  "
          f"speed {rec['standing_final_speed_m_s']:.3e} m/s  "
          f"spin {rec['standing_final_spin_rad_s']:.3e} rad/s  "
          f"contacts {rec['standing_floor_contacts']:3d}  STABLE={rec['standing_stable']}")

# --- two-box same asset -----------------------------------------------------------------------
print("\n" + "=" * 120)
print("=== TWO-BOX COLLISION, same asset as striker and target ===")
print(f"  {'asset':44s} {'gap':>5s} {'gap_mm':>7s} {'A_tip':>7s} {'A_topl':>6s} {'contact':>7s} "
      f"{'t_1st':>6s} {'B_tip':>7s} {'B_topl':>6s} {'B_dx_mm':>8s}")
for aid in ASSETS:
    for frac in GAP_FRACTIONS:
        rec = run_case(aid, aid, frac, DENSITY_PRIMARY)
        results["cases"].append(rec)
        print(f"  {aid:44s} {frac:5.2f} {rec['gap_m']*1000:7.2f} "
              f"{rec['striker_max_tilt_deg']:7.2f} {str(rec['striker_toppled']):>6s} "
              f"{str(rec['contact_between_a_and_b_made']):>7s} "
              f"{(rec['first_contact_time_s'] if rec['first_contact_time_s'] is not None else -1):6.3f} "
              f"{rec['target_max_tilt_deg']:7.2f} {str(rec['target_toppled']):>6s} "
              f"{rec['target_translation_x_m']*1000:8.2f}")

# --- cross pairs ------------------------------------------------------------------------------
print("\n=== TWO-BOX COLLISION, cross pairs at gap 0.25h ===")
for striker in ASSETS:
    for target in ASSETS:
        if striker == target:
            continue
        rec = run_case(striker, target, 0.25, DENSITY_PRIMARY)
        rec["case"] = "two_box_cross"
        results["cases"].append(rec)
        print(f"  {striker[:36]:36s} -> {target[:36]:36s} "
              f"A_tip {rec['striker_max_tilt_deg']:7.2f} A_topl={str(rec['striker_toppled']):>5s} "
              f"contact={str(rec['contact_between_a_and_b_made']):>5s} "
              f"B_tip {rec['target_max_tilt_deg']:7.2f} B_topl={str(rec['target_toppled']):>5s} "
              f"B_dx={rec['target_translation_x_m']*1000:8.2f} mm")

# --- density sweep ----------------------------------------------------------------------------
print("\n=== DENSITY SWEEP (same-asset pairs, gap 0.25h): is the outcome density-invariant? ===")
for aid in ASSETS:
    for d in DENSITY_SWEEP:
        rec = run_case(aid, aid, 0.25, d)
        rec["case"] = "two_box_density_sweep"
        results["cases"].append(rec)
        print(f"  {aid[:40]:40s} density {d:6.1f} -> mass {rec['striker_mass_kg']:.6f} kg  "
              f"A_topl={str(rec['striker_toppled']):>5s} "
              f"contact={str(rec['contact_between_a_and_b_made']):>5s} "
              f"B_topl={str(rec['target_toppled']):>5s} B_tip {rec['target_max_tilt_deg']:7.2f} deg")

# --- push sweep -------------------------------------------------------------------------------
print("\n=== PUSH-STRENGTH SWEEP (same-asset pairs, gap 0.25h) ===")
for aid in ASSETS:
    for w in OMEGA0_SWEEP:
        rec = run_case(aid, aid, 0.25, DENSITY_PRIMARY, omega0=w)
        rec["case"] = "two_box_push_sweep"
        results["cases"].append(rec)
        print(f"  {aid[:40]:40s} omega0 {w:4.2f}  A_topl={str(rec['striker_toppled']):>5s} "
              f"contact={str(rec['contact_between_a_and_b_made']):>5s} "
              f"B_topl={str(rec['target_toppled']):>5s} B_tip {rec['target_max_tilt_deg']:7.2f} deg")

# --- reach vs capability ----------------------------------------------------------------------
print("\n=== REACH vs CAPABILITY CONTROL (tiny gap 0.02h, 8 s) ===")
for aid in ASSETS:
    rec = run_case(aid, aid, 0.02, DENSITY_PRIMARY, sim_s=8.0)
    rec["case"] = "two_box_reach_control"
    results["cases"].append(rec)
    print(f"  {aid[:40]:40s} A_topl={str(rec['striker_toppled']):>5s} "
          f"contact={str(rec['contact_between_a_and_b_made']):>5s} "
          f"B_topl={str(rec['target_toppled']):>5s} B_tip {rec['target_max_tilt_deg']:7.2f} deg "
          f"B_dx {rec['target_translation_x_m']*1000:8.2f} mm")

# --- summary ----------------------------------------------------------------------------------
summary = {}
for aid in ASSETS:
    primary = sorted(
        [c for c in results["cases"]
         if c.get("case") == "two_box" and c.get("striker") == aid and c.get("target") == aid],
        key=lambda x: x["gap_fraction_of_shorter_height"])
    standing = [c for c in results["cases"]
                if c.get("case") == "standing" and c.get("striker") == aid]
    ok_gaps = [c["gap_fraction_of_shorter_height"] for c in primary if c.get("target_toppled")]
    summary[aid] = {
        "dims_m_t_w_h": [SPEC[aid]["thickness_m"], SPEC[aid]["width_m"], SPEC[aid]["height_m"]],
        "hull_volume_m3": SPEC[aid]["hull_volume_m3"],
        "assigned_mass_kg_at_200": DENSITY_PRIMARY * SPEC[aid]["hull_volume_m3"],
        "tipping_math": SPEC[aid]["tipping_math"],
        "standing_stable": standing[0]["standing_stable"] if standing else None,
        "standing_max_tilt_deg": standing[0]["standing_max_tilt_deg"] if standing else None,
        "standing_final_tilt_deg": (standing[0]["standing_final_tilt_deg"] if standing else None),
        "standing_max_xy_drift_m": (standing[0]["standing_max_xy_drift_m"] if standing else None),
        "striker_toppled_at_all_gaps": all(c.get("striker_toppled") for c in primary),
        "contact_made_at_all_gaps": all(c.get("contact_between_a_and_b_made") for c in primary),
        "gaps_where_target_toppled": ok_gaps,
        "max_gap_fraction_that_topples": (max(ok_gaps) if ok_gaps else None),
        "min_gap_fraction_that_topples": (min(ok_gaps) if ok_gaps else None),
        "per_gap": [{
            "gap_fraction": c["gap_fraction_of_shorter_height"], "gap_m": c["gap_m"],
            "striker_max_tilt_deg": c["striker_max_tilt_deg"],
            "striker_toppled": c["striker_toppled"],
            "contact_made": c["contact_between_a_and_b_made"],
            "first_contact_time_s": c["first_contact_time_s"],
            "target_toppled": c["target_toppled"],
            "target_max_tilt_deg": c["target_max_tilt_deg"],
            "target_final_tilt_deg": c["target_final_tilt_deg"],
            "target_translation_x_m": c["target_translation_x_m"],
            "target_verdict": c["target_verdict"],
        } for c in primary],
    }
    summary[aid]["can_topple_a_following_box"] = bool(ok_gaps)
results["summary"] = summary

print("\n" + "=" * 120)
print("=== SUMMARY: can this box topple a following box of the same kind? ===")
for aid, s in summary.items():
    print(f"\n  {aid}")
    print(f"    dims t x w x h     {s['dims_m_t_w_h'][0]:.4f} x {s['dims_m_t_w_h'][1]:.4f} x "
          f"{s['dims_m_t_w_h'][2]:.4f} m   mass@200 = {s['assigned_mass_kg_at_200']:.5f} kg")
    print(f"    stands stably      {s['standing_stable']} "
          f"(max tilt {s['standing_max_tilt_deg']:.4f} deg, drift "
          f"{s['standing_max_xy_drift_m']*1000:.4f} mm)")
    print(f"    striker toppled    {s['striker_toppled_at_all_gaps']} at all gaps")
    print(f"    contact with B     {s['contact_made_at_all_gaps']} at all gaps")
    print(f"    B toppled at gaps  {s['gaps_where_target_toppled']}")

(OUT / "box_physics_test.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"\nwritten: {OUT / 'box_physics_test.json'}")
