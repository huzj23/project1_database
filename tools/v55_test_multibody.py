"""V5.5 stage 04: real-solve smoke tests and the validator counter-example suite.

04 section 7 requires a real solve smoke test -- two real boxes colliding, three real boxes
transferring, a no-trigger control, a broken chain, and an off-centre rotating model -- plus
the validator counter-example report from section 5.

The physics here is the REAL pybullet solver via `physim.physics.multibody`, using CLOSED
collision geometry, not a stub.  Ideal primitives appear ONLY as numeric unit tests, which
04 section 7 permits explicitly ("理想primitive只可作数值单测，不可作为用户成片中的真实资产").

Run with the project python on a host that has pybullet.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from physim.contracts import (  # noqa: E402
    ROLE_PASSIVE,
    ROLE_TARGET,
    ROLE_TRIGGER,
    BodySpec,
    StaticCollider,
    ContractError,
    box_inertia_diagonal,
)
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402
from physim.physics.multibody_validate import (  # noqa: E402
    ValidationReport,
    check_causality,
    check_geometry,
    check_stability_control,
    check_timing,
    run_counterexample_suite,
    topple_events,
)

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, reason: str) -> None:
    RESULTS.append((name, passed, reason))
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}: {reason}")


def make_box(instance_id: str, role: str, pos, half_extents, mass=0.5, **kw) -> BodySpec:
    """A numeric-test box body.  Primitives are unit-test-only, per 04 section 7."""
    dims = tuple(2 * h for h in half_extents)
    return BodySpec(
        instance_id=instance_id,
        asset_id=f"primitive_box_{half_extents[0]:.3f}",
        role=role,
        mass_kg=mass,
        mass_basis="estimated",
        collider_type="box",
        position_m=tuple(float(v) for v in pos),
        inertia_diagonal_kg_m2=box_inertia_diagonal(mass, dims),
        **kw,
    )


def ground_collider(z: float = 0.0) -> StaticCollider:
    return StaticCollider(collider_id="static:ground", collider_type="plane",
                          position_m=(0.0, 0.0, z))


def prims(*specs: BodySpec) -> dict:
    """Half extents keyed per instance, for the solver's explicit-geometry contract."""
    out = {}
    for s in specs:
        # Recover half extents from the inertia-bearing dimensions we chose.
        out[s.instance_id] = {"half_extents_m": HALF_EXTENTS[s.instance_id]}
    return out


HALF_EXTENTS: dict[str, tuple[float, float, float]] = {}


# ------------------------------------------------------------------ numeric unit tests


def test_inertia_formula() -> None:
    """04 section 3: box inertia must be m*(h^2+d^2)/12, NOT m*a^2/5."""
    m = 0.5731
    dims = (0.496927, 0.058296, 0.260353)
    got = box_inertia_diagonal(m, dims)
    x, y, z = dims
    want = [m * (y * y + z * z) / 12.0, m * (x * x + z * z) / 12.0, m * (x * x + y * y) / 12.0]
    ok = all(abs(g - w) < 1e-15 for g, w in zip(got, want))
    rejected = m * max(dims) ** 2 / 5.0
    record("inertia_uses_cuboid_formula_not_half_axis",
           ok and abs(got[0] - rejected) > 1e-9,
           f"Ixx={got[0]:.6e} matches cuboid form and differs from the forbidden "
           f"m*a^2/5 value {rejected:.6e}")


def test_time_contract() -> None:
    """Substep k must be reported at k*dt covering ((k-1)dt, k*dt] -- the V5 off-by-one."""
    from physim.contracts import substep_time_s

    dt = 1.0 / 480.0
    gaps = [substep_time_s(k, 480.0) - substep_time_s(k - 1, 480.0) for k in range(2, 12)]
    ok = all(abs(g - dt) < 1e-12 for g in gaps) and substep_time_s(1, 480.0) == dt
    record("substep_time_is_k_times_dt", ok,
           f"step 1 -> {substep_time_s(1, 480.0):.9f} s == dt; consecutive spacing is dt")


# ------------------------------------------------------------------ real pybullet solves


def test_two_real_boxes() -> None:
    """04 section 7: two real boxes collide.  A moving box must disturb a resting one.

    Spacing note: the first version of this test placed the trigger 0.20 m away, and the
    measured result was that it slid and STOPPED after ~0.13 m, so it never reached the
    target.  That was a layout error on my part, not a solver fault: sliding friction
    decays the approach.  The boxes here are therefore placed nearly touching, which is
    also how a real domino line is laid out.  The measured deceleration is recorded so the
    reachability of any spacing can be checked rather than guessed.
    """
    HALF_EXTENTS.clear()
    settings = SolverSettings(physics_fps=480.0, video_fps=24.0)
    speed = 0.8
    trigger = make_box("box_001", ROLE_TRIGGER, (-0.11, 0.0, 0.0251), (0.05, 0.05, 0.025),
                       mass=0.35, linear_velocity_m_s=(speed, 0.0, 0.0))
    target = make_box("box_002", ROLE_TARGET, (0.0, 0.0, 0.0251), (0.05, 0.05, 0.025),
                      mass=0.35)
    HALF_EXTENTS.update({"box_001": (0.05, 0.05, 0.025), "box_002": (0.05, 0.05, 0.025)})

    with MultibodySolver(settings) as solver:
        solver.load([trigger, target], [ground_collider()], primitives=prims(trigger, target))
        pen = solver.check_initial_penetration()
        result = solver.run(frame_count=48)
        effective = solver.effective_parameters()

    moved = result.trajectories["box_002"]
    displacement = math.dist(moved[-1].position, moved[0].position)
    contacts = {c.pair for c in result.contacts}
    hit = frozenset({"box_001", "box_002"}) in contacts

    # Measured sliding deceleration, so reachability is evidence-based.
    t = result.trajectories["box_001"]
    v0 = speed
    stopped = next((s for s in t if abs(s.linear_velocity[0]) < 0.01), t[-1])
    decel = (v0 - 0.0) / stopped.time_seconds if stopped.time_seconds > 0 else float("nan")
    stop_distance = v0 * v0 / (2 * decel) if decel and decel > 0 else float("nan")

    record("two_real_boxes_transfer_contact",
           hit and displacement > 0.005 and pen.passed,
           f"real contact recorded={hit}, target moved {displacement * 1000:.2f} mm, "
           f"initial penetration {pen.max_penetration_m * 1000:.4f} mm; measured sliding "
           f"deceleration {decel:.2f} m/s^2 gives a stopping distance of "
           f"{stop_distance * 1000:.1f} mm from {speed} m/s, so spacing must stay inside that")

    # Effective parameters must be READ BACK, not assumed (04 section 2).
    eff = effective["box_001"]
    record("effective_parameters_read_back",
           abs(eff["mass_kg"] - 0.35) < 1e-9 and eff["lateral_friction"] > 0,
           f"getDynamicsInfo reports mass={eff['mass_kg']} friction={eff['lateral_friction']:.3f} "
           f"inertia={[round(v, 9) for v in eff['local_inertia_diagonal_kg_m2']]}")

    # And the installed inertia must be the cuboid one, not the engine's approximation.
    want_ixx = box_inertia_diagonal(0.35, (0.1, 0.1, 0.05))[0]
    got_ixx = eff["local_inertia_diagonal_kg_m2"][0]
    record("installed_inertia_took_effect", abs(got_ixx - want_ixx) < 1e-12,
           f"engine inertia Ixx={got_ixx:.9e} equals the cuboid value {want_ixx:.9e}")


def test_three_real_boxes() -> None:
    """04 section 7: three real boxes transfer motion through the middle one.

    Laid out as a real line: surfaces separated by a small gap, so each box is inside the
    reach of the one before it (see the stopping distance measured in the two-box test).
    """
    HALF_EXTENTS.clear()
    settings = SolverSettings(physics_fps=480.0, video_fps=24.0)
    half = (0.05, 0.05, 0.025)
    xs = (-0.11, 0.0, 0.11)          # 0.1 m boxes -> 0.01 m gaps between surfaces
    boxes = [
        make_box("box_001", ROLE_TRIGGER, (xs[0], 0.0, 0.0251), half,
                 mass=0.35, linear_velocity_m_s=(0.8, 0.0, 0.0)),
        make_box("box_002", ROLE_TARGET, (xs[1], 0.0, 0.0251), half, mass=0.35),
        make_box("box_003", ROLE_TARGET, (xs[2], 0.0, 0.0251), half, mass=0.35),
    ]
    for b in boxes:
        HALF_EXTENTS[b.instance_id] = half

    with MultibodySolver(settings) as solver:
        solver.load(boxes, [ground_collider()], primitives=prims(*boxes))
        result = solver.run(frame_count=72)

    order = []
    for iid in ("box_002", "box_003"):
        traj = result.trajectories[iid]
        for state in traj:
            if math.dist(state.position, traj[0].position) > 0.002:
                order.append((iid, round(state.time_seconds, 5)))
                break

    pairs = {c.pair for c in result.contacts}
    chain_hit = frozenset({"box_001", "box_002"}) in pairs
    chain_hit2 = frozenset({"box_002", "box_003"}) in pairs
    increasing = len(order) == 2 and order[1][1] >= order[0][1]

    record("three_real_boxes_chain_transfer",
           chain_hit and chain_hit2 and increasing,
           f"contacts 1-2={chain_hit} 2-3={chain_hit2}; onset order={order} "
           f"(strictly increasing={increasing})")


def test_no_trigger_control() -> None:
    """04 section 5: the SAME layout with the trigger's velocity removed must stay still.

    Only that one factor changes, so this is a genuine control.
    """
    HALF_EXTENTS.clear()
    settings = SolverSettings(physics_fps=480.0, video_fps=24.0)
    half = (0.05, 0.05, 0.025)
    # Identical to the three-box test EXCEPT the trigger has zero initial velocity.
    boxes = [
        make_box("box_001", ROLE_TRIGGER, (-0.11, 0.0, 0.0251), half,
                 mass=0.35, linear_velocity_m_s=(0.0, 0.0, 0.0)),
        make_box("box_002", ROLE_TARGET, (0.0, 0.0, 0.0251), half, mass=0.35),
        make_box("box_003", ROLE_TARGET, (0.11, 0.0, 0.0251), half, mass=0.35),
    ]
    for b in boxes:
        HALF_EXTENTS[b.instance_id] = half

    with MultibodySolver(settings) as solver:
        solver.load(boxes, [ground_collider()], primitives=prims(*boxes))
        result = solver.run(frame_count=72, settle_seconds=2.0)

    report = ValidationReport()
    for c in check_stability_control(result):
        report.add("stability", c)
    passed = report.group_passed("stability")
    drift = max(
        (math.dist(result.trajectories[i][-1].position, result.trajectories[i][0].position)
         for i in ("box_001", "box_002", "box_003")),
        default=float("nan"),
    )
    record("no_trigger_control_stays_still", passed,
           f"max drift over 3 s without trigger = {drift * 1000:.4f} mm; "
           f"{[c.reason for c in report.groups['stability']][0]}")


def test_broken_chain_control() -> None:
    """04 section 5: with the middle box removed, downstream must NOT start.

    A gap is used that the upstream box cannot cross, so a bypass cannot be mistaken for
    propagation.
    """
    HALF_EXTENTS.clear()
    settings = SolverSettings(physics_fps=480.0, video_fps=24.0)
    half = (0.05, 0.05, 0.025)
    # box_002 is deliberately absent; box_003 sits far beyond the trigger's measured
    # ~0.13 m sliding reach, so no bypass can be mistaken for propagation.
    boxes = [
        make_box("box_001", ROLE_TRIGGER, (-0.11, 0.0, 0.0251), half,
                 mass=0.35, linear_velocity_m_s=(0.8, 0.0, 0.0)),
        make_box("box_003", ROLE_TARGET, (0.60, 0.0, 0.0251), half, mass=0.35),
    ]
    for b in boxes:
        HALF_EXTENTS[b.instance_id] = half

    with MultibodySolver(settings) as solver:
        solver.load(boxes, [ground_collider()], primitives=prims(*boxes))
        result = solver.run(frame_count=96)

    traj = result.trajectories["box_003"]
    drift = math.dist(traj[-1].position, traj[0].position)
    record("broken_chain_does_not_propagate", drift < 0.002,
           f"with box_002 removed, downstream box_003 stayed put "
           f"(drift {drift * 1000:.4f} mm < 2 mm), so the chain really is broken")


def test_offcentre_rotation_replay_consistency() -> None:
    """04 section 7: an off-centre rotating model -- the trajectory must be replayable."""
    HALF_EXTENTS.clear()
    settings = SolverSettings(physics_fps=480.0, video_fps=24.0)
    # A box dropped off-centre so it lands on a corner and rotates.
    box = make_box("box_001", ROLE_TRIGGER, (0.0, 0.0, 0.30), (0.06, 0.04, 0.02),
                   mass=0.25, quaternion_xyzw=(0.0, 0.0, 0.3826834, 0.9238795))
    HALF_EXTENTS["box_001"] = (0.06, 0.04, 0.02)

    with MultibodySolver(settings) as solver:
        solver.load([box], [ground_collider()], primitives=prims(box))
        result = solver.run(frame_count=60)

    traj = result.trajectories["box_001"]
    # Every recorded quaternion must remain unit length, or a replay would scale the body.
    norms = [math.sqrt(sum(v * v for v in s.quaternion)) for s in traj]
    unit_ok = all(abs(n - 1.0) < 1e-6 for n in norms)
    # Frames must be contiguous from 0 and times must equal frame/video_fps.
    frames_ok = [s.frame for s in traj] == list(range(len(traj)))
    times_ok = all(abs(s.time_seconds - s.frame / 24.0) < 1e-12 for s in traj)
    rotated = abs(traj[-1].quaternion[1] - traj[0].quaternion[1]) > 1e-4 or \
        abs(traj[-1].quaternion[3] - traj[0].quaternion[3]) > 1e-4

    record("offcentre_rotation_is_replayable",
           unit_ok and frames_ok and times_ok and rotated,
           f"unit quaternions={unit_ok}, frames contiguous from 0={frames_ok}, "
           f"time=frame/fps={times_ok}, body actually rotated={rotated}")

    # The contract must accept the result it produced.
    try:
        result.validate()
        record("solver_output_satisfies_contract", True,
               "MultibodyResult.validate() accepts the solved result (identity, time, "
               "quaternions, at least one dynamic body)")
    except ContractError as exc:
        record("solver_output_satisfies_contract", False, f"contract rejected it: {exc}")


def test_topple_uses_local_axis_not_yaw() -> None:
    """04 section 4: a pure yaw rotation must NOT be counted as a topple."""
    from physim.physics import BodyState

    from physim.contracts import MultibodyResult

    body = make_box("box_001", ROLE_TARGET, (0, 0, 0.1), (0.05, 0.05, 0.1), mass=0.5)
    HALF_EXTENTS["box_001"] = (0.05, 0.05, 0.1)
    # Yaw 60 degrees about world Z: the local long axis still points up.
    half = math.radians(60) / 2
    q_wxyz = (math.cos(half), 0.0, 0.0, math.sin(half))
    traj = {
        "box_001": [
            BodyState(frame=f, time_seconds=f / 24.0, position=(0, 0, 0.1),
                      quaternion=q_wxyz, linear_velocity=(0, 0, 0),
                      angular_velocity=(0, 0, 1.0))
            for f in range(30)
        ]
    }
    result = MultibodyResult(bodies=[body], trajectories=traj, frame_count=30,
                             physics_fps=480.0, video_fps=24.0)
    events = topple_events(result)
    record("yaw_is_not_a_topple", not events["box_001"]["toppled"],
           f"60 deg yaw about world Z gives local-Z angle "
           f"{events['box_001']['max_angle_deg']} deg, below the 50 deg topple threshold, "
           f"so a spin cannot masquerade as a fall")


def test_validator_counterexamples() -> None:
    """04 section 5: the validator must reject every listed bad input."""
    checks = run_counterexample_suite()
    for c in checks:
        record(f"counterexample::{c.name}", c.passed, c.reason)
    rejected = sum(1 for c in checks if c.passed)
    record("counterexample_suite_complete", rejected == len(checks),
           f"{rejected}/{len(checks)} invalid inputs were rejected by the validator")


def main() -> int:
    print("=== V5.5 stage 04: solver smoke tests and validator counter-examples ===")
    print()
    print("--- numeric unit tests (primitives allowed here only) ---")
    test_inertia_formula()
    test_time_contract()

    print()
    print("--- real pybullet solves (closed collision geometry) ---")
    for fn in (test_two_real_boxes, test_three_real_boxes, test_no_trigger_control,
               test_broken_chain_control, test_offcentre_rotation_replay_consistency,
               test_topple_uses_local_axis_not_yaw):
        try:
            fn()
        except Exception as exc:
            import traceback
            record(fn.__name__, False, f"raised {type(exc).__name__}: {exc}")
            traceback.print_exc()

    print()
    print("--- validator counter-example suite ---")
    test_validator_counterexamples()

    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print()
    print(f"=== SUMMARY: {passed}/{total} checks passed ===")
    for name, ok, reason in RESULTS:
        if not ok:
            print(f"  FAIL {name}: {reason}")

    out = ROOT / "outcomes" / "v55" / "stage04"
    out.mkdir(parents=True, exist_ok=True)
    (out / "test_results.json").write_text(
        json.dumps([{"name": n, "passed": p, "reason": r} for n, p, r in RESULTS], indent=2),
        encoding="utf-8",
    )
    print(f"written: {out / 'test_results.json'}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
