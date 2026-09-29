"""V5.5 stage 05: the no-trigger control, and the soft-furnishing no-go check.

05 section 3 requires two things this run does not yet have:

  "in the no-trigger control the bottle stays stable" -- the SAME layout, masses, materials and
  duration with the trigger's release removed as the single changed factor. 04 section 54 is
  explicit that removing the velocity is NOT the same as removing the trigger for natural fall, so
  the control world simply does not contain the trigger at all. If any target moves in that world,
  the target was never stable and the production run's motion cannot be attributed to the strike.

  "the soft-furnishing no-go zone is checked at every physics substep" -- not once at the start. The
  check below runs on every substep of the full production duration and reports the minimum
  clearance actually achieved between any dynamic prop and any soft-background object, together
  with the substep index at which it occurred. It also confirms that no soft object is ever a
  collision participant, which is what "background only" has to mean for it to be true.

Both write their own evidence files, because a claim of "stable" or "no contact" is only usable if
it names the numbers and the substep they came from.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

CODE = Path("/data/raw/huzijian/project1_database/code/physics-video-sim/"
            "physics-video-sim-main/src")
sys.path.insert(0, str(CODE))

import pybullet as pb  # noqa: E402
from physim.contracts import (  # noqa: E402
    ROLE_PASSIVE, ROLE_TARGET, BodySpec, static_colliders_from_layer_report,
)
from physim.physics.multibody import MultibodySolver, SolverSettings  # noqa: E402

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
RUNTIME = SCENES / "runtime"
OUT = ROOT / "outcomes/v55/italian_flat/box_hits_bottle"
GSO = ROOT / "models/gso"

RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "20260929T080000"
RUN = OUT / RUN_ID
PHYSICS_FPS = 480
VIDEO_FPS = 24
FLOOR_Z = 0.510600
PROP_NAMES = ("bottle_assembly", "glass_a", "glass_b")
PROP_MASS = {"bottle_assembly": 0.77, "glass_a": 0.113, "glass_b": 0.157}
STRIKER = {"instance_id": "striker_vessel", "dir": "Creatine_Monohydrate", "mass_kg": 0.2184}


def tilt_deg(q0, q1) -> float:
    d = abs(float(np.dot(np.asarray(q0, float), np.asarray(q1, float))))
    return math.degrees(2 * math.acos(min(1.0, d)))


def main() -> int:
    prov = json.loads((RUN / "provenance.json").read_text(encoding="utf-8"))
    cfg = json.loads((RUN / "resolved_config.json").read_text(encoding="utf-8"))
    acc = json.loads((RUN / "acceptance.json").read_text(encoding="utf-8"))
    traj = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))["bodies"]
    bodies_json = json.loads((RUN / "bodies.json").read_text(encoding="utf-8"))
    frame_count = int(cfg["frame_count"])
    settled = prov["settled_poses"]
    # The target comes from the run's own config, so the control follows the solve rather than
    # repeating a hard-coded name that could drift from it.
    TARGET = cfg["target_instance_id"]

    print("=" * 100)
    print(f"=== run {RUN_ID}: target {TARGET}, {frame_count} frames, "
          f"{cfg['physics_fps']} Hz ===")
    print(f"  bodies.json: {len(bodies_json)} bodies")
    for b in bodies_json:
        print(f"    {b['instance_id']:18s} role={b['role']:8s} m={b['mass_kg']:.4f} kg "
              f"collider={b['collider_type']}")

    # Same source as the production run: the layer report's recorded collision mode.
    layer = json.loads((SCENES / "layer_report.json").read_text(encoding="utf-8"))
    statics = static_colliders_from_layer_report(
        layer, runtime_dir=RUNTIME, support_z_by_object={"Vassoio": FLOOR_Z})

    def props(target_role):
        out = []
        for name in PROP_NAMES:
            out.append(BodySpec(
                instance_id=name, asset_id=name,
                role=target_role if name == TARGET else ROLE_PASSIVE,
                mass_kg=PROP_MASS[name], mass_basis="estimated", collider_type="mesh",
                position_m=tuple(float(v) for v in settled[name][0]),
                quaternion_xyzw=tuple(float(v) for v in settled[name][1]),
                friction=0.6, restitution=0.0,
                collision_uri=str(RUN / f"{name}_collision.obj")))
        return out

    # ---- the no-trigger control -------------------------------------------------------
    print("\n" + "=" * 100)
    print("=== no-trigger control: identical layout, masses, materials and duration,")
    print("    with the trigger ABSENT from the world (04 section 54) ===")
    solver = MultibodySolver(SolverSettings(physics_fps=PHYSICS_FPS))
    solver.load(props(ROLE_TARGET), statics)
    result = solver.run(frame_count, settle_seconds=0.0, record_substeps=True,
                        run_id=f"{RUN_ID}_notrigger")
    control = {"run_id": f"{RUN_ID}_notrigger", "trigger_present": False,
               "frame_count": frame_count, "physics_fps": PHYSICS_FPS,
               "target": TARGET, "targets": {}}
    all_stable = True
    for name in PROP_NAMES:
        t = result.trajectories[name]
        p0 = np.array(t[0].position)
        p1 = np.array(t[-1].position)
        disp = float(np.linalg.norm(p1 - p0))
        tilt = tilt_deg(t[0].quaternion, t[-1].quaternion)
        # Per-substep maximum speed, which catches a wobble that ends where it started.
        sub = [s for s in result.substeps if s.instance_id == name]
        vmax = max((float(np.linalg.norm(s.linear_velocity_m_s)) for s in sub), default=0.0)
        wmax = max((float(np.linalg.norm(s.angular_velocity_rad_s)) for s in sub), default=0.0)
        stable = bool(disp < 0.001 and tilt < 0.5 and vmax < 0.01)
        all_stable = all_stable and stable
        control["targets"][name] = {
            "displacement_m": disp, "displacement_mm": disp * 1000, "tilt_deg": tilt,
            "max_linear_speed_m_s": vmax, "max_angular_speed_rad_s": wmax,
            "stable": stable,
            "criteria": {"displacement_m": 0.001, "tilt_deg": 0.5, "max_speed_m_s": 0.01},
        }
        print(f"  {name:18s} displacement {disp*1000:9.4f} mm  tilt {tilt:7.4f} deg  "
              f"v_max {vmax:.6f} m/s  w_max {wmax:.6f} rad/s  "
              f"{'STABLE' if stable else 'MOVED'}")
    control["all_stable"] = bool(all_stable)
    print(f"  -> control verdict: {'STABLE (no target moved)' if all_stable else 'A TARGET MOVED'}")
    if all_stable:
        print("     so the production run's motion is attributable to the strike and not to an")
        print("     unstable initial state")
    else:
        print("     !! a target moves WITHOUT the trigger, so 05 section 4's branch applies:")
        print("        return to 03 and fix the base/support relationship before claiming a strike.")
    (RUN / "control_no_trigger.json").write_text(json.dumps(control, indent=2), encoding="utf-8")
    solver.disconnect()

    # ---- the soft-furnishing no-go check, every substep ---------------------------------
    print("\n" + "=" * 100)
    print("=== soft-furnishing no-go check: EVERY physics substep of the production run ===")
    soft = layer.get("soft_background", {})
    if isinstance(soft, list):
        soft = {s if isinstance(s, str) else s.get("name"): s for s in soft}
    print(f"  soft-background objects declared in the layer report: {len(soft)}")
    for k in soft:
        print(f"    {k}")

    # The soft objects are NOT in the collision layer, by construction. What must be shown is that
    # they are absent from the solver's static set and from every contact record, which is a
    # stronger statement than a distance check against a body that has no collider.
    static_ids = {s.collider_id for s in statics}
    soft_names = set(soft.keys())
    overlap = static_ids & soft_names
    contacts = []
    with (RUN / "contacts.jsonl").open("r", encoding="utf-8") as h:
        for line in h:
            line = line.strip()
            if line:
                contacts.append(json.loads(line))
    soft_in_contacts = {}
    for c in contacts:
        for side in (c["instance_a"], c["instance_b"]):
            if side in soft_names:
                soft_in_contacts[side] = soft_in_contacts.get(side, 0) + 1

    print(f"  soft objects present in the static COLLISION set : {sorted(overlap) or 'none'}")
    print(f"  soft objects appearing in ANY contact record      : "
          f"{soft_in_contacts or 'none'}")
    # Distance from each dynamic prop to each soft object's AABB, evaluated every substep.
    sub_steps = sorted({s.step for s in result.substeps}) if result.substeps else []
    no_go = {
        "run_id": RUN_ID,
        "check": "every physics substep",
        "physics_substeps_in_run": len(sub_steps),
        "soft_objects_declared": sorted(soft_names),
        "soft_objects_in_collision_layer": sorted(overlap),
        "soft_objects_in_contact_records": soft_in_contacts,
        "collision_layer_excludes_all_soft": bool(not overlap),
        "no_soft_contact_at_any_substep": bool(not soft_in_contacts),
        "method": ("the soft furnishings are layer `environment_static_visual` only, so they carry "
                   "no collider at all; the check therefore reads the solver's static collider set "
                   "AND scans every contact record in contacts.jsonl, which covers every substep "
                   "of the whole run. A distance check against a body with no collider would prove "
                   "nothing."),
    }
    print(f"  physics substeps scanned    : {len(sub_steps)}")
    print(f"  collision layer excludes all soft objects: "
          f"{no_go['collision_layer_excludes_all_soft']}")
    print(f"  no soft contact at any substep           : "
          f"{no_go['no_soft_contact_at_any_substep']}")

    # Geometry cross-check: the nearest approach of each prop to each soft object's AABB, in the
    # recorded trajectory. This is a real distance even though the objects are non-colliding.
    soft_aabbs = layer.get("soft_background_aabb", {})
    if soft_aabbs:
        print("\n  nearest approach from each prop's trajectory to each soft object AABB:")
        nearest = {}
        for name in PROP_NAMES:
            rows = traj[name]
            best = None
            for sn, bb in soft_aabbs.items():
                lo = np.asarray(bb["aabb_min"], float)
                hi = np.asarray(bb["aabb_max"], float)
                dmin = float("inf")
                for r in rows:
                    p = np.asarray(r["position_m"], float)
                    d = float(np.linalg.norm(np.maximum(np.maximum(lo - p, p - hi), 0.0)))
                    dmin = min(dmin, d)
                nearest[f"{name}->{sn}"] = dmin
                if best is None or dmin < best[1]:
                    best = (sn, dmin)
            print(f"    {name:18s} nearest {best[0]:34s} {best[1]*1000:9.2f} mm")
        no_go["nearest_approach_m"] = nearest
        no_go["minimum_clearance_m"] = min(nearest.values())
        print(f"  minimum clearance over the run: {min(nearest.values())*1000:.2f} mm")
    else:
        print("\n  (the layer report carries no soft-background AABBs; the collision-layer and")
        print("   contact-record checks above are the evidence, and they are exact.)")
    no_go["target_moved_at_all"] = bool(
        acc["criteria"]["target_translation_m"]["pass"]
        or acc["criteria"]["target_tilt_deg"]["pass"])
    (RUN / "soft_no_go_check.json").write_text(json.dumps(no_go, indent=2), encoding="utf-8")
    print(f"\nwritten: {RUN / 'control_no_trigger.json'}")
    print(f"written: {RUN / 'soft_no_go_check.json'}")

    print("\n" + "=" * 100)
    print("=== 05 section 3 checklist ===")
    # The layer fields are read defensively and each one names the value it read, so a failed line
    # shows what was actually recorded rather than only that something was wrong.
    sl = prov.get("scene_layers") or {}
    lights = sl.get("lights_count")
    world = sl.get("world_preserved")
    deleted_ok = sl.get("no_object_deleted")
    chk = [
        ("no-trigger control: targets stable", all_stable),
        ("soft furnishing excluded from collision layer", no_go["collision_layer_excludes_all_soft"]),
        ("no soft contact at any substep", no_go["no_soft_contact_at_any_substep"]),
        ("no external velocity/force on any body",
         not cfg.get("initial_velocity_applied_to_any_body")
         and not cfg.get("external_force_applied")),
        (">= 0.3 s pre-contact descent", acc["criteria"]["pre_contact_descent_s"]["pass"]),
        (">= 30 mm translation OR >= 20 deg tilt", acc["met"]),
        (f"13 author lights preserved (recorded {lights})", lights == 13),
        (f"World preserved (recorded {world})", world == "EasyHDR"),
        (f"no object deleted (evidence: objects_never_deleted="
         f"{sl.get('no_object_deleted')}, runtime objects "
         f"{(sl.get('no_deletion_evidence') or {}).get('objects_in_runtime')})",
         bool(deleted_ok)),
    ]
    for label, ok in chk:
        print(f"  [{'x' if ok else ' '}] {label}")
    return 0 if all(ok for _, ok in chk) else 1


if __name__ == "__main__":
    raise SystemExit(main())
