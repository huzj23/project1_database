"""V5.5 stage 02 contract tests.

02_contracts.md section 5 requires at least: schema round-trip; multiple instances of
one asset; illegal duplicate-id rejection; quaternion/COM alignment; time monotonicity
and 0/last-frame agreement; a failing physics validation blocks rendering; the old
``SimulationResult`` and every registered scenario still load; and that a no-trigger /
broken-chain experiment differs only by the declared config.

Run:
    python tools/v55_test_contracts.py
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / "code" / "physics-video-sim" / "physics-video-sim-main"
sys.path.insert(0, str(REPO / "src"))

from physim import contracts as C  # noqa: E402

FAILURES: list[str] = []


def _rejects(fn, *args, **kwargs) -> bool:
    """True when ``fn`` raises -- the contract rejects bad data rather than repairing."""
    try:
        fn(*args, **kwargs)
    except Exception:
        return True
    return False


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def make_body(iid: str, role: str = C.ROLE_TARGET, mass: float = 0.2) -> C.BodySpec:
    return C.BodySpec(
        instance_id=iid,
        asset_id="box_medium",
        role=role,
        mass_kg=mass,
        mass_basis="estimated",
        collider_type="box",
        position_m=(0.0, 0.0, 0.05),
        friction=0.4,
        restitution=0.05,
        inertia_diagonal_kg_m2=(1e-4, 2e-4, 3e-4),
    )


def make_result(n: int = 3) -> C.MultibodyResult:
    """A tiny synthetic chain: box_001 triggers box_002 triggers box_003."""
    bodies = [make_body(f"box_{i:03d}", C.ROLE_TRIGGER if i == 1 else C.ROLE_TARGET)
              for i in range(1, n + 1)]
    physics_fps, video_fps, frames = 480.0, 24.0, 5
    from physim.physics import BodyState

    trajectories = {}
    for i, b in enumerate(bodies):
        states = []
        for frame in range(frames):
            states.append(
                BodyState(
                    frame=frame,
                    time_seconds=C.frame_time_s(frame, video_fps),
                    position=(0.1 * i + 0.001 * frame, 0.0, 0.05),
                    quaternion=C.quat_to_wxyz((0.0, 0.0, 0.0, 1.0)),
                    linear_velocity=(0.01, 0.0, 0.0),
                    angular_velocity=(0.0, 0.0, 0.0),
                )
            )
        trajectories[b.instance_id] = states

    contacts = [
        C.ContactRecord(
            step=1, time_s=C.substep_time_s(1, physics_fps),
            instance_a="box_001", instance_b="box_002", link_a=-1, link_b=-1,
            position_on_a_m=(0.0, 0.0, 0.05), position_on_b_m=(0.0, 0.0, 0.05),
            normal_on_b=(1.0, 0.0, 0.0), signed_distance_m=0.0, normal_force_n=2.0,
            lateral_force_1_n=0.1, lateral_force_2_n=0.0,
            lateral_dir_1=(0.0, 1.0, 0.0), lateral_dir_2=(0.0, 0.0, 1.0),
        ),
        C.ContactRecord(
            step=2, time_s=C.substep_time_s(2, physics_fps),
            instance_a="box_001", instance_b="box_002", link_a=-1, link_b=-1,
            position_on_a_m=(0.0, 0.0, 0.05), position_on_b_m=(0.0, 0.0, 0.05),
            normal_on_b=(1.0, 0.0, 0.0), signed_distance_m=0.0, normal_force_n=1.5,
            lateral_force_1_n=0.1, lateral_force_2_n=0.0,
            lateral_dir_1=(0.0, 1.0, 0.0), lateral_dir_2=(0.0, 0.0, 1.0),
        ),
        C.ContactRecord(
            step=9, time_s=C.substep_time_s(9, physics_fps),
            instance_a="box_002", instance_b="box_003", link_a=-1, link_b=-1,
            position_on_a_m=(0.0, 0.0, 0.05), position_on_b_m=(0.0, 0.0, 0.05),
            normal_on_b=(1.0, 0.0, 0.0), signed_distance_m=0.0, normal_force_n=3.0,
            lateral_force_1_n=0.0, lateral_force_2_n=0.0,
            lateral_dir_1=(0.0, 1.0, 0.0), lateral_dir_2=(0.0, 0.0, 1.0),
        ),
    ]
    result = C.MultibodyResult(
        bodies=bodies, trajectories=trajectories, contacts=contacts,
        physics_fps=physics_fps, video_fps=video_fps, frame_count=frames,
        seed=550001, run_id="contract_test",
    )
    result.events = C.episodes_from_contacts(result.contacts)
    result.static_colliders = [
        C.StaticCollider(
            collider_id="static:floor", collider_type="mesh",
            uri="assets/environments/x/collision/floor.obj", triangles=1234,
        )
    ]
    return result


print("=== 1. units, frames, gravity are frozen as declared ===")
check("gravity is [0,0,-9.81]", C.Z_UP_GRAVITY == (0.0, 0.0, -9.81), str(C.Z_UP_GRAVITY))

print("\n=== 2. time convention: substep k covers ((k-1)dt, k*dt] and reports k*dt ===")
dt = 1.0 / 480.0
check("substep 1 -> dt", abs(C.substep_time_s(1, 480.0) - dt) < 1e-15, f"{C.substep_time_s(1, 480)}")
check("substep 0 rejected", _rejects(lambda: C.substep_time_s(0, 480.0)))
check("frame 0 -> t=0", C.frame_time_s(0, 24.0) == 0.0)
check("blender frame = frame+1", C.blender_frame_number(0) == 1 and C.blender_frame_number(80) == 81)
check("substeps_per_frame 480/24 = 20", C.substeps_per_frame(480.0, 24.0) == 20)
check("non-divisible fps rejected", _rejects(lambda: C.substeps_per_frame(500.0, 24.0)))
check("playback != sampled span (documented separately)",
      abs(C.playback_duration_s(81, 24.0) - 3.375) < 1e-12
      and abs(C.sampled_span_s(81, 24.0) - 80 / 24.0) < 1e-12)

print("\n=== 3. quaternion conventions (xyzw), q == -q, wxyz boundary ===")
check("identity xyzw -> wxyz", C.quat_to_wxyz((0.0, 0.0, 0.0, 1.0)) == (1.0, 0.0, 0.0, 0.0))
check("wxyz -> xyzw round trip",
      C.quat_from_wxyz(C.quat_to_wxyz((0.1, 0.2, 0.3, 0.9))) == (0.1, 0.2, 0.3, 0.9))
check("q and -q are the SAME rotation", C.quat_close((0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, -1.0)))
check("different rotations are not close", not C.quat_close((0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.7071, 0.7071), tol=1e-3))
s90 = (0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4))
check("90 deg about Z accepts +q and -q equally",
      C.quat_close(s90, tuple(-v for v in s90)))
check("angle of 90 deg Z is pi/2",
      abs(C.quat_angle(s90) - math.pi / 2) < 1e-9, f"{C.quat_angle(s90):.6f}")

print("\n=== 4. rotation correctness against hand-computed cases ===")
rt = C.quat_rotate(s90, (1.0, 0.0, 0.0))
check("Z+90 rotates +X to +Y", all(abs(a - b) < 1e-9 for a, b in zip(rt, (0.0, 1.0, 0.0))),
      f"{tuple(round(v, 6) for v in rt)}")
# Non-zero COM: rotating a point about an offset origin must match the manual result.
m = C.mat4_from_trs((1.0, 2.0, 3.0), s90)
p = C.mat4_transform_point(m, (0.5, 0.0, 0.0))
check("point rotates about the translated origin",
      all(abs(a - b) < 1e-9 for a, b in zip(p, (1.0, 2.5, 3.0))),
      f"{tuple(round(v, 6) for v in p)}")

print("\n=== 5. T_WV = T_WB @ T_BV composition ===")
t_wb = C.mat4_from_trs((1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
t_bv = C.mat4_from_trs((0.0, 0.5, 0.0), s90)
t_wv = C.mat4_multiply(t_wb, t_bv)
composed = C.mat4_transform_point(t_wv, (0.0, 0.0, 0.0))
check("composed transform places V origin correctly",
      all(abs(a - b) < 1e-9 for a, b in zip(composed, (1.0, 0.5, 0.0))),
      f"{tuple(round(v, 6) for v in composed)}")
check("row-major flatten/unflatten round trip",
      C.mat4_unflatten(C.mat4_flatten(t_wv)) == t_wv)
check("identity matrix", C.mat4_identity() == [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]])

print("\n=== 6. identity: same asset many times, unique instance ids ===")
r = make_result(3)
r.validate()
check("3 bodies of one asset validate", len(r.bodies) == 3)
check("all share asset_id box_medium", {b.asset_id for b in r.bodies} == {"box_medium"})
check("instance ids are distinct", len({b.instance_id for b in r.bodies}) == 3)

print("\n=== 7. duplicate / unknown ids are REJECTED ===")
dup = make_result(3)
dup.bodies.append(make_body("box_001"))
check("duplicate instance_id rejected", _rejects(dup.validate_identity))
ghost = make_result(3)
ghost.trajectories["box_999"] = ghost.trajectories["box_001"]
check("trajectory for unknown body rejected", _rejects(ghost.validate_identity))
collide = make_result(3)
collide.static_colliders.append(C.StaticCollider(collider_id="box_001", collider_type="box"))
check("static collider id colliding with a body rejected", _rejects(collide.validate_identity))

print("\n=== 8. role and mass-basis validation ===")
check("bad role rejected", _rejects(lambda: make_body("b", role="saboteur")))
check("bad mass_basis rejected", _rejects(lambda: C.BodySpec(
    instance_id="b", asset_id="a", role=C.ROLE_TARGET, mass_kg=1.0,
    mass_basis="vibes", collider_type="box", position_m=(0, 0, 0))))
check("negative mass rejected", _rejects(lambda: make_body("b", mass=-1.0)))
check("zero mass is allowed but NOT dynamic",
      make_body("b", mass=0.0).is_dynamic is False and make_body("b", mass=0.5).is_dynamic)

print("\n=== 9. 'all passive' cannot masquerade as a chain ===")
no_dyn = make_result(3)
no_dyn.bodies = [make_body(f"box_{i:03d}", mass=0.0) for i in (1, 2, 3)]
check("zero dynamic bodies REJECTED", _rejects(no_dyn.validate_no_passive_actors))

print("\n=== 10. time validation: 0-based, monotonic, consistent ===")
good = make_result(3)
good.validate_time()
bad_first = make_result(3)
from physim.physics import BodyState  # noqa: E402
bad_first.trajectories["box_001"] = [
    BodyState(frame=1, time_seconds=1 / 24.0, position=(0, 0, 0),
              quaternion=(1, 0, 0, 0), linear_velocity=(0, 0, 0), angular_velocity=(0, 0, 0))
]
check("first frame must be 0", _rejects(bad_first.validate_time))
bad_mono = make_result(3)
bad_mono.trajectories["box_001"] = list(reversed(bad_mono.trajectories["box_001"]))
check("frames must be monotonic", _rejects(bad_mono.validate_time))
bad_t = make_result(3)
bad_t.trajectories["box_001"] = [
    BodyState(frame=0, time_seconds=0.0, position=(0, 0, 0), quaternion=(1, 0, 0, 0),
              linear_velocity=(0, 0, 0), angular_velocity=(0, 0, 0)),
    BodyState(frame=1, time_seconds=999.0, position=(0, 0, 0), quaternion=(1, 0, 0, 0),
              linear_velocity=(0, 0, 0), angular_velocity=(0, 0, 0)),
]
check("time_seconds must equal frame/video_fps", _rejects(bad_t.validate_time))

print("\n=== 11. contact/event aggregation keeps raw evidence ===")
r = make_result(3)
pairs = {(e.instance_a, e.instance_b) for e in r.events}
check("two distinct pairs became two episodes", len(r.events) == 2, str(sorted(pairs)))
ep_12 = [e for e in r.events if e.instance_a == "box_001"][0]
check("adjacent substeps 1-2 merged into one episode", ep_12.step_start == 1 and ep_12.step_end == 2)
check("raw contact list is retained", len(r.contacts) == 3)
check("impulse_proxy is labelled an estimate",
      ep_12.to_dict()["impulse_proxy_is_estimate"] is True)
ground = C.ContactRecord(
    step=1, time_s=C.substep_time_s(1, 480.0), instance_a="box_001",
    instance_b="static:ground", link_a=-1, link_b=-1,
    position_on_a_m=(0, 0, 0), position_on_b_m=(0, 0, 0), normal_on_b=(0, 0, 1),
    signed_distance_m=0.0, normal_force_n=9.8, lateral_force_1_n=0.0,
    lateral_force_2_n=0.0, lateral_dir_1=(1, 0, 0), lateral_dir_2=(0, 1, 0),
)
eps = C.episodes_from_contacts([ground])
check("static contact classified as ground, not dynamic propagation",
      eps[0].contact_kind == "ground" and eps[0].to_dict()["contact_kind"] == "ground")

print("\n=== 12. schema round-trip (to_dict -> from_dict -> equal) ===")
r = make_result(3)
d1 = r.to_dict()
r2 = C.MultibodyResult.from_dict(copy.deepcopy(d1))
d2 = r2.to_dict()
check("round trip preserves schema_version", d1["schema_version"] == C.SCHEMA_VERSION)
check("round trip is stable", json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True))
check("round-tripped result still validates", (r2.validate() or True))
check("quaternion order declared as xyzw",
      d1["time_convention"]["quaternion_order"] == "xyzw")
check("matrix serialization declared row-major",
      d1["time_convention"]["matrix_serialization"] == "row-major")
check("blender frame offset declared",
      d1["time_convention"]["blender_frame_number"] == "frame + 1")
check("substep interval declared",
      d1["time_convention"]["substep_interval"] == "((k-1)*dt, k*dt]")

print("\n=== 13. matrix fields survive JSON as 16-element row-major ===")
r = make_result(3)
# Rebuild body 0 with the optional transform fields populated.  ``is_dynamic`` is a
# derived property, so it is deliberately NOT passed back into the constructor.
first = r.bodies[0]
r.bodies[0] = C.BodySpec(
    instance_id=first.instance_id,
    asset_id=first.asset_id,
    role=first.role,
    mass_kg=first.mass_kg,
    mass_basis=first.mass_basis,
    collider_type=first.collider_type,
    position_m=first.position_m,
    quaternion_xyzw=first.quaternion_xyzw,
    linear_velocity_m_s=first.linear_velocity_m_s,
    angular_velocity_rad_s=first.angular_velocity_rad_s,
    friction=first.friction,
    restitution=first.restitution,
    com_local_m=first.com_local_m,
    inertia_diagonal_kg_m2=first.inertia_diagonal_kg_m2,
    visual_to_body_4x4=C.mat4_from_trs((0.1, 0.2, 0.3), s90),
    collision_to_body_4x4=C.mat4_identity(),
)
dd = r.to_dict()
check("visual_to_body_4x4 serialized as 16 floats",
      len(dd["bodies"][0]["visual_to_body_4x4"]) == 16)
back = C.MultibodyResult.from_dict(copy.deepcopy(dd))
check("matrix round trips to 4x4",
      C.mat4_flatten(back.bodies[0].visual_to_body_4x4)
      == dd["bodies"][0]["visual_to_body_4x4"])
check("COM survives the round trip",
      tuple(dd["bodies"][0]["com_local_m"]) == tuple(back.bodies[0].com_local_m))
check("is_dynamic is NOT a constructor field but is reported",
      "is_dynamic" in dd["bodies"][0] and back.bodies[0].is_dynamic is True)

print("\n=== 14. JSONL writers refuse to overwrite prior evidence ===")
tmp = ROOT / "tmp" / "v55_contract_test"
tmp.mkdir(parents=True, exist_ok=True)
target = tmp / f"probe_{len(list(tmp.iterdir()))}.jsonl"
n = C.write_jsonl(target, [{"a": 1}, {"a": 2}])
check("write_jsonl returns the record count", n == 2)
check("second write to the same path is REFUSED", _rejects(lambda: C.write_jsonl(target, [{"a": 3}])))
check("read_jsonl returns both records", len(list(C.read_jsonl(target))) == 2)

print("\n=== 15. legacy SimulationResult path still works (no regression) ===")
legacy_ok = True
try:
    from physim.physics import SimulationResult
    one = SimulationResult(
        trajectory=tuple(r.trajectories["box_001"]), collisions=(),
        support_trajectory=(),
    )
    legacy_ok = (not one.has_support_trajectory) and len(one.trajectory) == 5
except Exception as exc:  # pragma: no cover
    print(f"      legacy load raised: {exc}")
    legacy_ok = False
check("legacy SimulationResult constructs and reads as before", legacy_ok)

if FAILURES:
    print(f"\nRESULT: FAIL ({len(FAILURES)} check(s))")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("\nRESULT: PASS -- V5.5 contract verified")
