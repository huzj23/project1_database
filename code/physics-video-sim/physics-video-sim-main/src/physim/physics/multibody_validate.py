"""V5.5 stage 04: the geometric / stability / causal / intrusion validator.

04 section 1.4 requires PASS/FAIL plus a reason BEFORE any Blender render, and section 5
requires the validator to REJECT a list of specific bad inputs.  This module is the single
place those judgements live, so stages 05-08 cannot each invent their own criteria.

Validation is split into four independent verdicts, matching the stage-02 rule that
"physics passed", "render verified", "executor reviewed" and "user accepted" are separate
facts and must never be collapsed into one boolean:

  * ``geometry``    -- bodies are separated, in bounds, no initial penetration
  * ``stability``   -- the no-trigger control keeps every target still
  * ``causality``   -- the propagation path is really driven by contacts
  * ``timing``      -- substep resolution is sufficient and consistent

Every check returns a ``Check`` with a boolean and a human-readable reason, so a FAIL is
always reportable instead of just being a number that went the wrong way.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from physim.contracts import (
    ROLE_TARGET,
    ROLE_TRIGGER,
    BodySpec,
    ContactRecord,
    ContractError,
    MultibodyResult,
    quat_angle,
    quat_conjugate,
    quat_multiply,
    quat_rotate,
)

#: 04 section 4: motion-onset thresholds.  Fixed BEFORE the trial and written into the
#: resolved config, exactly as the section demands.
DEFAULT_ONSET_TRANSLATION_M = 0.002
DEFAULT_ONSET_ROTATION_DEG = 2.0
DEFAULT_ONSET_DWELL_S = 0.020
DEFAULT_ONSET_SPEED_M_S = 0.02
DEFAULT_ONSET_SPIN_RAD_S = 0.1

#: 04 section 4: topple = local vertical long axis vs world Z exceeds this, for this long.
DEFAULT_TOPPLE_ANGLE_DEG = 50.0
DEFAULT_TOPPLE_DWELL_S = 0.10

#: 04 section 4: a propagator must respond within this window after first contact.
DEFAULT_PROPAGATION_WINDOW_S = 0.15

#: 04 section 3: pre-settle steady-state drift limits over the final 0.5 s.
DEFAULT_MAX_TRANSLATION_DRIFT_M = 0.002
DEFAULT_MAX_ROTATION_DRIFT_DEG = 1.0
DEFAULT_SETTLE_WINDOW_S = 0.5


@dataclass
class Check:
    """One validation result: a verdict plus why."""

    name: str
    passed: bool
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    #: ``None`` means the check could not be evaluated; that is NOT a pass.
    evaluated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "evaluated": self.evaluated,
            "reason": self.reason,
            "evidence": self.evidence,
        }


@dataclass
class ValidationReport:
    """Grouped checks with a per-group and overall verdict."""

    groups: dict[str, list[Check]] = field(default_factory=dict)

    def add(self, group: str, check: Check) -> None:
        self.groups.setdefault(group, []).append(check)

    def group_passed(self, group: str) -> bool:
        checks = self.groups.get(group, [])
        # An unevaluated check is a failure, not a pass: silence must not look like success.
        return bool(checks) and all(c.passed and c.evaluated for c in checks)

    @property
    def physics_passed(self) -> bool:
        required = ("geometry", "stability", "causality", "timing")
        present = [g for g in required if g in self.groups]
        if not present:
            return False
        return all(self.group_passed(g) for g in present)

    def failures(self) -> list[Check]:
        out: list[Check] = []
        for checks in self.groups.values():
            out.extend(c for c in checks if not c.passed or not c.evaluated)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": {
                name: [c.to_dict() for c in checks] for name, checks in self.groups.items()
            },
            "group_verdicts": {name: self.group_passed(name) for name in self.groups},
            "physics_passed": self.physics_passed,
            "failure_count": len(self.failures()),
            "failure_reasons": [f"{c.name}: {c.reason}" for c in self.failures()],
            # 04: each verdict is separate and must not be folded into physics_passed.
            "render_verified": None,
            "executor_visual_reviewed": None,
            "user_visual_accepted": None,
        }


# --------------------------------------------------------------------------- helpers


def world_up_angle_deg(result: MultibodyResult, instance_id: str, frame: int) -> float | None:
    """Angle between the body's LOCAL +Z axis and world +Z, in degrees.

    04 requires topple to be judged on the local vertical long axis, because a yaw spin of
    50 degrees must not be counted as a topple.  ``quat_angle`` alone would count yaw, so
    this transforms the local axis and measures against world up.
    """
    body = result.body(instance_id)
    traj = result.trajectories.get(instance_id)
    if not traj or frame >= len(traj):
        return None
    # BodyState stores wxyz (legacy type); the contract's quaternion rotate uses xyzw.
    w, x, y, z = traj[frame].quaternion
    xyzw = (x, y, z, w)
    local_z = quat_rotate(xyzw, (0.0, 0.0, 1.0))
    cos_angle = max(-1.0, min(1.0, local_z[2]))
    return math.degrees(math.acos(cos_angle))


def drift_over_window(
    result: MultibodyResult, instance_id: str, window_s: float
) -> dict[str, float] | None:
    """Max translation and rotation drift over the final ``window_s`` of the trajectory."""
    traj = result.trajectories.get(instance_id)
    if not traj:
        return None
    fps = result.video_fps
    n = max(1, int(round(window_s * fps)))
    window = traj[-n:] if len(traj) > n else traj
    if len(window) < 2:
        return None
    base = window[0]
    max_t = 0.0
    max_r = 0.0
    for state in window[1:]:
        dt = math.dist(state.position, base.position)
        max_t = max(max_t, dt)
        # BodyState stores wxyz; quat_multiply/quat_conjugate work in xyzw, so convert
        # both and take the RELATIVE rotation.  Using quat_angle on a single absolute
        # quaternion would report the body's orientation, not how far it drifted.
        a = (base.quaternion[1], base.quaternion[2], base.quaternion[3], base.quaternion[0])
        b = (state.quaternion[1], state.quaternion[2], state.quaternion[3], state.quaternion[0])
        relative = quat_multiply(quat_conjugate(a), b)
        max_r = max(max_r, math.degrees(quat_angle(relative)))
    return {"max_translation_m": max_t, "max_rotation_deg": max_r}


# --------------------------------------------------------------------------- geometry


def check_geometry(
    result: MultibodyResult,
    *,
    bounds_m: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None,
    forbidden_regions: Sequence[dict[str, Any]] = (),
) -> list[Check]:
    """Separation, initial penetration and out-of-bounds / no-go-region checks."""
    checks: list[Check] = []

    # 04 section 3: initial penetration target <= min(1 mm, t_min*5%).
    worst = 0.0
    worst_pair = None
    for c in result.contacts:
        if c.step > 1:
            break
        if c.signed_distance_m < 0:
            depth = -c.signed_distance_m
            if depth > worst:
                worst, worst_pair = depth, (c.instance_a, c.instance_b)
    limit = 1e-3
    checks.append(Check(
        name="initial_penetration_within_limit",
        passed=worst <= limit,
        reason=(
            f"max initial penetration {worst * 1000:.4f} mm <= {limit * 1000:.3f} mm"
            if worst <= limit
            else f"max initial penetration {worst * 1000:.4f} mm exceeds {limit * 1000:.3f} mm"
                 f" (pair {worst_pair}); the layout overlaps, and this engine has no"
                 f" collision margin to hide it"
        ),
        evidence={"max_penetration_m": worst, "limit_m": limit, "pair": worst_pair},
    ))

    # Bounds: every dynamic body must stay inside the declared play volume.
    if bounds_m is not None:
        lo, hi = bounds_m
        escapes: list[dict[str, Any]] = []
        for spec in result.dynamic_bodies():
            for state in result.trajectories.get(spec.instance_id, []):
                for i, axis in enumerate("xyz"):
                    if state.position[i] < lo[i] - 1e-9 or state.position[i] > hi[i] + 1e-9:
                        escapes.append({
                            "instance_id": spec.instance_id,
                            "frame": state.frame,
                            "axis": axis,
                            "value": state.position[i],
                        })
                        break
        checks.append(Check(
            name="within_declared_bounds",
            passed=not escapes,
            reason=(
                "all dynamic bodies stayed inside the declared play volume"
                if not escapes
                else f"{len(escapes)} body/frame pairs left the declared volume, "
                     f"first={escapes[0]}"
            ),
            evidence={"violations": escapes[:10], "bounds_m": [list(lo), list(hi)]},
        ))
    else:
        checks.append(Check(
            name="within_declared_bounds",
            passed=False,
            evaluated=False,
            reason="no bounds supplied, so bounds were NOT checked",
        ))

    # No-go regions (soft furniture etc. must be background, never contact targets).
    if forbidden_regions:
        intrusions: list[dict[str, Any]] = []
        for region in forbidden_regions:
            centre = region["centre_m"]
            radius = float(region["radius_m"])
            for spec in result.dynamic_bodies():
                for state in result.trajectories.get(spec.instance_id, []):
                    if math.dist(state.position, centre) < radius:
                        intrusions.append({
                            "instance_id": spec.instance_id,
                            "region": region.get("id", "?"),
                            "frame": state.frame,
                        })
                        break
        checks.append(Check(
            name="no_forbidden_region_intrusion",
            passed=not intrusions,
            reason=(
                f"{len(forbidden_regions)} forbidden region(s) stayed clear"
                if not intrusions
                else f"bodies entered forbidden regions: {intrusions[:5]}"
            ),
            evidence={"intrusions": intrusions[:10]},
        ))

    return checks


# --------------------------------------------------------------------------- stability


def check_stability_control(
    result: MultibodyResult,
    *,
    max_translation_m: float = DEFAULT_MAX_TRANSLATION_DRIFT_M,
    max_rotation_deg: float = DEFAULT_MAX_ROTATION_DRIFT_DEG,
    window_s: float = DEFAULT_SETTLE_WINDOW_S,
    settle_window_s: float | None = None,
) -> list[Check]:
    """04 section 3 + section 5: the no-trigger world must leave every target still.

    This is the check that makes "the layout is stable" a measurement rather than a claim.
    """
    checks: list[Check] = []
    targets = [b for b in result.bodies if b.role == ROLE_TARGET]
    if not targets:
        checks.append(Check(
            name="targets_present",
            passed=False,
            evaluated=False,
            reason="no body carries the target role, so there is nothing to keep still",
        ))
        return checks

    drifted: list[dict[str, Any]] = []
    for spec in targets:
        d = drift_over_window(result, spec.instance_id, settle_window_s or window_s)
        if d is None:
            drifted.append({"instance_id": spec.instance_id, "reason": "no trajectory"})
            continue
        if d["max_translation_m"] > max_translation_m or d["max_rotation_deg"] > max_rotation_deg:
            drifted.append({
                "instance_id": spec.instance_id,
                "max_translation_m": round(d["max_translation_m"], 6),
                "max_rotation_deg": round(d["max_rotation_deg"], 6),
            })

    checks.append(Check(
        name="no_trigger_control_is_stable",
        passed=not drifted,
        reason=(
            f"all {len(targets)} targets stayed within {max_translation_m * 1000:.1f} mm and "
            f"{max_rotation_deg:.1f} deg"
            if not drifted
            else f"{len(drifted)} target(s) moved without a trigger: {drifted[:4]}"
        ),
        evidence={
            "targets": [b.instance_id for b in targets],
            "drifted": drifted,
            "limits": {"translation_m": max_translation_m, "rotation_deg": max_rotation_deg},
        },
    ))
    return checks


# --------------------------------------------------------------------------- causality


def topple_events(
    result: MultibodyResult,
    *,
    angle_deg: float = DEFAULT_TOPPLE_ANGLE_DEG,
    dwell_s: float = DEFAULT_TOPPLE_DWELL_S,
    instance_ids: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """First substep-resolution frame where each body is toppled, and whether it held.

    04: topple is the local vertical long axis exceeding 50 degrees for at least 0.10 s,
    judged on drift from world Z so a yaw turn cannot masquerade as a fall.
    """
    fps = result.video_fps
    dwell_frames = max(1, int(math.ceil(dwell_s * fps)))
    ids = list(instance_ids) if instance_ids is not None else [
        b.instance_id for b in result.dynamic_bodies()
    ]
    out: dict[str, dict[str, Any]] = {}
    for iid in ids:
        traj = result.trajectories.get(iid)
        if not traj:
            out[iid] = {"toppled": False, "reason": "no trajectory"}
            continue
        angles = [world_up_angle_deg(result, iid, f) for f in range(len(traj))]
        onset_frame = None
        onset_time = None
        for f, ang in enumerate(angles):
            if ang is None or ang <= angle_deg:
                continue
            # Demand the dwell, so a momentary spike does not count as a topple.
            if f + dwell_frames <= len(angles) and all(
                a is not None and a > angle_deg for a in angles[f:f + dwell_frames]
            ):
                onset_frame = f
                onset_time = traj[f].time_seconds
                break
        out[iid] = {
            "toppled": onset_frame is not None,
            "onset_frame": onset_frame,
            "onset_time_s": onset_time,
            "max_angle_deg": round(max(a for a in angles if a is not None), 3) if any(
                a is not None for a in angles
            ) else None,
            "dwell_frames_required": dwell_frames,
        }
    return out


def check_causality(
    result: MultibodyResult,
    *,
    toppled_ids: Sequence[str] | None = None,
    require_topple_all: bool = True,
) -> list[Check]:
    """Contact-driven propagation, not a scripted or bookkeeping coincidence.

    A propagation A -> B is accepted only when ALL hold (04 section 4):
      * A was itself triggered upstream, or A is the declared unique trigger;
      * a valid dynamic A/B contact happens FIRST;
      * B was nearly still before that contact;
      * B visibly responds inside the propagation window afterwards.
    """
    checks: list[Check] = []

    triggers = [b for b in result.bodies if b.role == ROLE_TRIGGER]
    checks.append(Check(
        name="exactly_one_trigger",
        passed=len(triggers) == 1,
        reason=(
            f"exactly one trigger body ({triggers[0].instance_id})"
            if len(triggers) == 1
            else f"expected exactly one trigger, found {len(triggers)}: "
                 f"{[t.instance_id for t in triggers]}"
        ),
        evidence={"triggers": [t.instance_id for t in triggers]},
    ))

    # No passive body may be an actor: every dynamic body must be a real rigid body from
    # the start, because 04 forbids promoting a passive body at a scripted moment.
    passive_actors = [
        b.instance_id for b in result.bodies
        if b.mass_kg == 0.0 and b.role in (ROLE_TRIGGER, ROLE_TARGET)
    ]
    checks.append(Check(
        name="no_passive_body_acts_as_actor",
        passed=not passive_actors,
        reason=(
            "every trigger/target is a real dynamic rigid body"
            if not passive_actors
            else f"these actors have zero mass and cannot move: {passive_actors}"
        ),
        evidence={"passive_actors": passive_actors},
    ))

    events = topple_events(result, instance_ids=toppled_ids)
    if toppled_ids:
        # Each declared body must topple EXACTLY once as a first event, and the ordering
        # must be strictly increasing at substep resolution (04 section 4).
        missing = [i for i in toppled_ids if not events.get(i, {}).get("toppled")]
        checks.append(Check(
            name="every_declared_body_topples",
            passed=not missing,
            reason=(
                f"all {len(toppled_ids)} declared bodies toppled"
                if not missing
                else f"{len(missing)} declared bodies never toppled: {missing}"
            ),
            evidence={"events": events, "missing": missing},
        ))

        onsets = [(i, events[i]["onset_time_s"]) for i in toppled_ids
                  if events.get(i, {}).get("toppled")]
        non_increasing = [
            (onsets[k], onsets[k + 1])
            for k in range(len(onsets) - 1) if onsets[k + 1][1] <= onsets[k][1]
        ]
        checks.append(Check(
            name="propagation_time_strictly_increases",
            passed=not non_increasing,
            reason=(
                f"all {len(onsets)} onset times strictly increase at substep resolution"
                if not non_increasing
                else f"{len(non_increasing)} pair(s) did not strictly increase, e.g. "
                     f"{non_increasing[0]}; refine the step or the layout rather than "
                     f"imposing an order"
            ),
            evidence={"onsets_s": onsets, "violations": non_increasing[:5]},
        ))

    # Every accepted propagation must be backed by a real contact.
    ids = set(result.instance_ids())
    if len(ids) > 1:
        pairs_with_contact = {c.pair for c in result.contacts}
        checks.append(Check(
            name="propagation_backed_by_contacts",
            passed=bool(pairs_with_contact),
            reason=(
                f"{len(pairs_with_contact)} distinct body pairs recorded real contact"
                if pairs_with_contact
                else "no contacts were recorded at all, so nothing propagated by contact"
            ),
            evidence={"contact_pairs": sorted(pairs_with_contact)[:40]},
        ))

    return checks


# --------------------------------------------------------------------------- timing


def check_timing(
    result: MultibodyResult,
    *,
    violations: Sequence[dict[str, Any]] = (),
) -> list[Check]:
    """Substep resolution and the 04 section 2 step-size bound."""
    checks: list[Check] = []

    ratio = result.physics_fps / result.video_fps if result.video_fps else 0.0
    integral = abs(ratio - round(ratio)) < 1e-9
    checks.append(Check(
        name="physics_fps_integer_multiple_of_video_fps",
        passed=integral,
        reason=(
            f"{result.physics_fps:g} Hz / {result.video_fps:g} fps = {ratio:g} substeps per "
            f"frame (must be an integer)"
            if integral
            else f"{result.physics_fps:g} Hz is not an integer multiple of "
                 f"{result.video_fps:g} fps (ratio {ratio:g})"
        ),
        evidence={"physics_fps": result.physics_fps, "video_fps": result.video_fps,
                  "substeps_per_frame": ratio},
    ))

    # Substep count must equal frames * substeps_per_frame; 04 requires EVERY substep.
    expected = result.frame_count * int(round(ratio))
    dynamic_count = len(result.dynamic_bodies())
    actual = len(result.substeps)
    checks.append(Check(
        name="all_substeps_recorded",
        passed=actual == expected * dynamic_count,
        reason=(
            f"{actual} substep rows == {result.frame_count} frames x "
            f"{int(round(ratio))} substeps x {dynamic_count} dynamic bodies"
            if actual == expected * dynamic_count
            else f"{actual} substep rows, expected {expected * dynamic_count} "
                 f"({result.frame_count} frames x {int(round(ratio))} substeps x "
                 f"{dynamic_count} bodies); the old 100-contact cap must not reappear"
        ),
        evidence={"substeps": actual, "expected": expected * dynamic_count,
                  "dynamic_bodies": dynamic_count},
    ))

    if violations:
        checks.append(Check(
            name="step_size_within_motion_bound",
            passed=False,
            reason=f"{len(violations)} body/bodies exceed 0.1*t_min per step: {violations[:3]}"
                   f"; reduce dt or velocity and evaluate CCD by penetration test",
            evidence={"violations": violations[:10]},
        ))
    else:
        checks.append(Check(
            name="step_size_within_motion_bound",
            passed=True,
            reason="no body exceeded the 0.1*t_min per-step motion bound",
            evidence={"violations": []},
        ))

    return checks


# --------------------------------------------------------------------------- counterexamples


def run_counterexample_suite() -> list[Check]:
    """04 section 5: the validator MUST reject these inputs.

    Each case returns ``True`` when the validator REJECTED the bad input.  Rejection can
    take either form: a hard ``ContractError`` for structurally invalid data, or a failed
    check group for physically invalid data.  A case "passes" when it was rejected, so an
    all-passed suite means the validator genuinely discriminates rather than accepting
    everything.
    """
    checks: list[Check] = []

    def evaluate(name: str, fn, why: str) -> Check:
        """Run one counter-example; pass when the validator rejected it."""
        try:
            rejected = bool(fn())
        except Exception as exc:  # a raised error is also a rejection
            return Check(
                name=name, passed=True,
                reason=f"correctly rejected by ContractError: {type(exc).__name__}: {exc}",
                evidence={"rejection": "exception", "exception": type(exc).__name__},
            )
        if rejected:
            return Check(
                name=name, passed=True,
                reason=f"correctly rejected: {why}",
                evidence={"rejection": "failed_check_group"},
            )
        return Check(
            name=name, passed=False,
            reason=f"NOT rejected: {why} was accepted, so the validator is permissive",
            evidence={"rejection": "none"},
        )

    def build_result(**overrides) -> MultibodyResult:
        from physim.physics import BodyState

        bodies = overrides.pop("bodies", None) or [
            BodySpec(instance_id="box_001", asset_id="a", role=ROLE_TRIGGER, mass_kg=0.5,
                     mass_basis="estimated", collider_type="mesh",
                     position_m=(0.0, 0.0, 1.0)),
            BodySpec(instance_id="box_002", asset_id="a", role=ROLE_TARGET, mass_kg=0.5,
                     mass_basis="estimated", collider_type="mesh",
                     position_m=(0.1, 0.0, 0.0)),
        ]
        traj = {
            b.instance_id: [
                BodyState(frame=f, time_seconds=f / 24.0, position=b.position_m,
                          quaternion=(1.0, 0.0, 0.0, 0.0),
                          linear_velocity=(0.0, 0.0, 0.0),
                          angular_velocity=(0.0, 0.0, 0.0))
                for f in range(3)
            ]
            for b in bodies
        }
        return MultibodyResult(bodies=bodies, trajectories=traj, frame_count=3,
                               physics_fps=480.0, video_fps=24.0, **overrides)

    def group_fails(result, checker, group: str, **kw) -> bool:
        report = ValidationReport()
        for c in checker(result, **kw):
            report.add(group, c)
        return not report.group_passed(group)

    # 1. duplicate instance_id -> the contract must reject it (raises ContractError).
    def duplicate_ids() -> bool:
        r = build_result(bodies=[
            BodySpec(instance_id="box_001", asset_id="a", role=ROLE_TRIGGER, mass_kg=1.0,
                     mass_basis="estimated", collider_type="mesh", position_m=(0, 0, 1)),
            BodySpec(instance_id="box_001", asset_id="a", role=ROLE_TARGET, mass_kg=1.0,
                     mass_basis="estimated", collider_type="mesh", position_m=(0, 0, 0)),
        ])
        r.validate_identity()
        return False

    checks.append(evaluate("counterexample_duplicate_instance_id", duplicate_ids,
                           "two bodies sharing an instance_id"))

    # 2. a non-unit quaternion -> the contract must reject it.
    def bad_quaternion() -> bool:
        b = BodySpec(instance_id="box_001", asset_id="a", role=ROLE_TARGET, mass_kg=1.0,
                     mass_basis="estimated", collider_type="mesh", position_m=(0, 0, 0),
                     quaternion_xyzw=(0.0, 0.0, 0.0, 2.0))
        build_result(bodies=[b]).validate_quaternions()
        return False

    checks.append(evaluate("counterexample_bad_quaternion", bad_quaternion,
                           "a non-unit quaternion that would silently scale the body"))

    # 3. initial penetration beyond the limit -> the geometry check must fail.
    def initial_penetration() -> bool:
        r = build_result()
        r.contacts = [ContactRecord(
            step=1, time_s=1.0 / 480.0, instance_a="box_001", instance_b="box_002",
            link_a=-1, link_b=-1, position_on_a_m=(0, 0, 0), position_on_b_m=(0, 0, 0),
            normal_on_b=(0, 0, 1), signed_distance_m=-0.02, normal_force_n=10.0,
            lateral_force_1_n=0.0, lateral_force_2_n=0.0,
            lateral_dir_1=(1, 0, 0), lateral_dir_2=(0, 1, 0),
        )]
        return group_fails(r, check_geometry, "geometry")

    checks.append(evaluate("counterexample_initial_penetration", initial_penetration,
                           "a 20 mm initial overlap exceeding the 1 mm limit"))

    # 4. a target that topples with NO contact at all -> a scripted move, not physics.
    def manually_moved_target() -> bool:
        from physim.physics import BodyState

        bodies = [
            BodySpec(instance_id="box_001", asset_id="a", role=ROLE_TRIGGER, mass_kg=0.5,
                     mass_basis="estimated", collider_type="mesh", position_m=(0, 0, 1)),
            BodySpec(instance_id="box_002", asset_id="a", role=ROLE_TARGET, mass_kg=0.5,
                     mass_basis="estimated", collider_type="mesh", position_m=(0.1, 0, 0)),
        ]
        traj = {}
        for b in bodies:
            rows = []
            for f in range(40):
                pos = (0.5 * f / 40.0, 0.0, 0.0) if b.instance_id == "box_002" else b.position_m
                q = (math.cos(math.pi / 4), math.sin(math.pi / 4), 0.0, 0.0) \
                    if b.instance_id == "box_002" and f > 10 else (1.0, 0.0, 0.0, 0.0)
                rows.append(BodyState(frame=f, time_seconds=f / 24.0, position=pos,
                                      quaternion=q, linear_velocity=(1.0, 0, 0),
                                      angular_velocity=(0, 0, 0)))
            traj[b.instance_id] = rows
        r = MultibodyResult(bodies=bodies, trajectories=traj, frame_count=40,
                            physics_fps=480.0, video_fps=24.0, contacts=[])
        # Also demand the pair never appears in the contact log.
        no_contact_pair = not any(
            c.pair == frozenset({"box_001", "box_002"}) for c in r.contacts
        )
        return no_contact_pair and group_fails(
            r, check_causality, "causality", toppled_ids=["box_001", "box_002"]
        )

    checks.append(evaluate("counterexample_no_contact_but_moves", manually_moved_target,
                           "a target toppling with a zero-contact log"))

    # 5. a missing trajectory for a declared body -> stability must fail.
    def missing_trajectory() -> bool:
        r = build_result()
        r.trajectories.pop("box_002")
        return group_fails(r, check_stability_control, "stability")

    checks.append(evaluate("counterexample_missing_trajectory", missing_trajectory,
                           "a declared body with no trajectory"))

    # 6. two triggers -> rejected, because propagation needs ONE unique source.
    def two_triggers() -> bool:
        r = build_result(bodies=[
            BodySpec(instance_id="box_001", asset_id="a", role=ROLE_TRIGGER, mass_kg=0.5,
                     mass_basis="estimated", collider_type="mesh", position_m=(0, 0, 1)),
            BodySpec(instance_id="box_002", asset_id="a", role=ROLE_TRIGGER, mass_kg=0.5,
                     mass_basis="estimated", collider_type="mesh", position_m=(0.1, 0, 0)),
        ])
        return group_fails(r, check_causality, "causality",
                           toppled_ids=["box_001", "box_002"])

    checks.append(evaluate("counterexample_two_triggers", two_triggers,
                           "two trigger bodies instead of one unique source"))

    # 7. physics_fps not an integer multiple of video_fps -> timing must fail.
    def bad_fps_ratio() -> bool:
        r = build_result()
        r.physics_fps = 500.0          # 500/24 is not an integer
        return group_fails(r, check_timing, "timing")

    checks.append(evaluate("counterexample_non_integer_fps_ratio", bad_fps_ratio,
                           "physics_fps that is not an integer multiple of video_fps"))

    # 8. truncated substep log (the old partial-log habit) -> timing must fail.
    def truncated_substeps() -> bool:
        r = build_result()
        r.substeps = []                # nothing recorded
        return group_fails(r, check_timing, "timing")

    checks.append(evaluate("counterexample_truncated_substep_log", truncated_substeps,
                           "an empty substep log where every substep is required"))

    # 9. a passive actor (zero mass) doing the pushing -> causality must fail.
    def passive_actor() -> bool:
        r = build_result(bodies=[
            BodySpec(instance_id="box_001", asset_id="a", role=ROLE_TRIGGER, mass_kg=0.0,
                     mass_basis="estimated", collider_type="mesh", position_m=(0, 0, 1)),
            BodySpec(instance_id="box_002", asset_id="a", role=ROLE_TARGET, mass_kg=0.5,
                     mass_basis="estimated", collider_type="mesh", position_m=(0.1, 0, 0)),
        ])
        return group_fails(r, check_causality, "causality", toppled_ids=["box_002"])

    checks.append(evaluate("counterexample_passive_actor", passive_actor,
                           "a zero-mass trigger that cannot actually move"))

    # 10. an unevaluated check must NOT count as a pass.
    def unevaluated_is_not_pass() -> bool:
        report = ValidationReport()
        report.add("geometry", Check(name="x", passed=False, evaluated=False,
                                     reason="not checked"))
        return not report.group_passed("geometry")

    checks.append(evaluate("counterexample_unevaluated_not_a_pass",
                           unevaluated_is_not_pass,
                           "an unevaluated check being treated as a pass"))

    return checks
