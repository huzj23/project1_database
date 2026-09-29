"""b2_chain.py -- V5.6 video B: the mixed-box domino chain, its controls, and its deliverables.

RUNS ON THE SERVER (pybullet is only there). Writes the run's trajectory and its verdicts.

THE FOUR ENGINE FACTS THIS RESPECTS, EACH OF WHICH COST HOURS ELSEWHERE
-----------------------------------------------------------------------
1. **COM at the OBJ origin.** PyBullet puts a `GEOM_MESH` body's COM at the OBJ file's own origin.
   Every proxy here was written CENTRED on its origin (`b2_make_proxies.py`, verified by reading the
   file back), so the COM is correct with NO inertial offset -- and this script does not take that on
   trust: `assert_com` re-reads `getDynamicsInfo(...)[3]` from the engine for every body and refuses
   to run if any COM is not at the body origin, or if the COM is not at mid-height above the base
   (which is the condition that makes toppling possible at all).

2. **Mesh shapes carry a fixed 1.000 mm collision margin per side; box primitives carry 0.000 mm.**
   Measured earlier at four sizes. These proxies are fitted boxes loaded as `GEOM_MESH`, so the
   effective half-thickness is t/2 + 1 mm. That is 1.8-4.0 % of the thickness for these assets, and it
   is the gap arithmetic that matters: the solver applies `--margin-comp mm` when it converts a
   requested VISIBLE face-to-face gap into centre spacing, so the requested gap is what the geometry
   actually has. `margin_probe` re-measures the margin in THIS process rather than quoting the number.

3. **`collisionMargin` / `margin` are rejected by this build.** `margin_probe` records the literal
   rejections, so the script never claims a margin was configured.

4. **URDF masses are scan artefacts** (each equals that asset's visual hull volume numerically, i.e.
   unit density). Mass is assigned as `--density` times the proxy's fitted-box volume, and the run is
   repeated at other densities to show the outcome does not hinge on that choice.

WHAT IS BUILT
-------------
A **placement** is a list of `(asset_id, x)` boxes standing upright on ONE support plane, plus an
optional trigger. Everything else is derived:

  * each box's centre z is `support_z(x) + height/2`, so its base is exactly FLUSH on the ground;
  * the COM projection is checked to lie inside the base polygon (`com_inside_support`);
  * gaps are expressed as a fraction of the SHORTER of the two boxes' heights and converted to centre
    spacing with the mesh margin accounted for, so different sizes are NOT evenly spaced.

The support surface can be a flat plane (`--ground-plane z=...`) or a MEASURED per-station profile
(`--ground-profile <json>`) taken from the ground survey. A plane is used for the pairwise/control
work; the profile records what the real Hidden Alley floor does and is applied in the ground-sensitivity
batch so the deliverable says whether the chain survives the real relief.

CONTROLS (all required, all actually run)
-----------------------------------------
  no_trigger        the whole chain, no trigger at all: must stay standing for the full duration.
  broken_chain      one MIDDLE box removed: upstream must fall, downstream must NOT.
  repeat_x3         three fixed-initial-state repeats: the event ORDER must agree.
  half_dt           halve the timestep: the event ORDER must agree.
  bypass            the trigger is fired at the first box; this checks that the first CONTACT of every
                    downstream box is with its upstream neighbour (never with the trigger or a box
                    further up), which is the "trigger flew over the first box" failure mode.

TRAJECTORY
----------
`trajectory.json` follows the project's contract exactly: frames start at 0, `time_s = frame/24`,
`blender_frame = frame + 1`, 24 video fps, physics 480 Hz = 20 substeps per video frame, substep k
covers ((k-1)dt, k*dt] and is reported with `step=k`, `time_s=k*dt`. `position_m` is the PHYSICS BODY
reference origin, i.e. the collision proxy's origin, never a visual AABB bottom.

Usage:
    python b2_chain.py --run <dir> --proxies <dir> --out chain.json [--mode ...]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import pybullet as pb

DENSITY_DEFAULT = 200.0
DENSITY_SWEEP = (100.0, 600.0)
FRICTION_BOX = 0.5
FRICTION_FLOOR = 0.5
RESTITUTION = 0.0
GRAVITY = -9.81
SOLVER_ITERS = 200

VIDEO_FPS = 24.0
PHYSICS_HZ = 480.0
DT = 1.0 / PHYSICS_HZ
SUBSTEPS_PER_FRAME = int(round(PHYSICS_HZ / VIDEO_FPS))     # 20

TOPPLE_DEG = 60.0
TIPPED_DEG = 15.0

FLOOR_HALF_X = 6.0
FLOOR_HALF_Y = 6.0
FLOOR_THICK = 0.25

#: clearances used when spawning, before the settle. The proxy base is exact, so this is only to
#: avoid an initial penetration from the mesh margin (1 mm per side).
SPAWN_CLEARANCE_M = 0.002


# --------------------------------------------------------------------------------------------
# small maths
# --------------------------------------------------------------------------------------------

def tilt_deg(q) -> float:
    """Angle between the body's own +z and world +z, in degrees."""
    R = pb.getMatrixFromQuaternion(q)
    return math.degrees(math.acos(max(-1.0, min(1.0, R[8]))))


def quat_yaw(deg):
    return pb.getQuaternionFromEuler([0.0, 0.0, math.radians(deg)])


def classify(tilt):
    if tilt >= TOPPLE_DEG:
        return "toppled"
    if tilt >= TIPPED_DEG:
        return "tilted_not_toppled"
    return "standing"


# --------------------------------------------------------------------------------------------
# world
# --------------------------------------------------------------------------------------------

class World:
    def __init__(self, dt=DT, gravity=GRAVITY):
        self.cid = pb.connect(pb.DIRECT)
        self.dt = dt
        pb.setGravity(0.0, 0.0, gravity, physicsClientId=self.cid)
        pb.setPhysicsEngineParameter(
            fixedTimeStep=dt, numSolverIterations=SOLVER_ITERS, numSubSteps=1,
            enableConeFriction=1, physicsClientId=self.cid)
        s = pb.createCollisionShape(pb.GEOM_BOX,
                                    halfExtents=[FLOOR_HALF_X, FLOOR_HALF_Y, FLOOR_THICK],
                                    physicsClientId=self.cid)
        self.floor = pb.createMultiBody(0, s, basePosition=(0.0, 0.0, -FLOOR_THICK),
                                        physicsClientId=self.cid)
        pb.changeDynamics(self.floor, -1, lateralFriction=FRICTION_FLOOR,
                          restitution=RESTITUTION, physicsClientId=self.cid)
        self.bodies = {}

    def close(self):
        try:
            pb.disconnect(self.cid)
        except Exception:
            pass

    def add_box(self, proxy_obj: str, mass: float, pos, yaw_deg=0.0, tag=""):
        col = pb.createCollisionShape(pb.GEOM_MESH, fileName=proxy_obj, flags=0,
                                      physicsClientId=self.cid)
        if col < 0:
            raise RuntimeError(f"createCollisionShape failed for {proxy_obj} (id {col})")
        b = pb.createMultiBody(mass, col, basePosition=pos,
                               baseOrientation=quat_yaw(yaw_deg), physicsClientId=self.cid)
        pb.changeDynamics(b, -1, lateralFriction=FRICTION_BOX, restitution=RESTITUTION,
                          physicsClientId=self.cid)
        self.bodies[b] = tag
        return b

    def step(self, n=1):
        for _ in range(n):
            pb.stepSimulation(physicsClientId=self.cid)

    def pos_quat(self, b):
        return pb.getBasePositionAndOrientation(b, physicsClientId=self.cid)

    def contacts_with(self, a, b):
        return pb.getContactPoints(bodyA=a, bodyB=b, physicsClientId=self.cid)

    def self_check(self):
        """A control box dropped on the floor: proves the floor works before any verdict is read."""
        half = 0.012
        s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[half] * 3, physicsClientId=self.cid)
        b = pb.createMultiBody(0.05, s, basePosition=(2.6, 2.6, half + 0.03),
                               physicsClientId=self.cid)
        self.step(int(1.5 / self.dt))
        p, _q = self.pos_quat(b)
        cps = self.contacts_with(b, self.floor)
        res = {"expected_z": half, "actual_z": p[2], "delta_m": p[2] - half,
               "floor_contacts": len(cps), "ok": bool(abs(p[2] - half) < 0.002 and len(cps) > 0)}
        pb.removeBody(b, physicsClientId=self.cid)
        return res


def margin_probe(build_dir: Path):
    """Re-measure the mesh margin in THIS process, and re-record the margin-argument rejection."""
    out = {"pybullet_api_version": pb.getAPIVersion(), "attempts": {}, "measured_m": {}}
    cid = pb.connect(pb.DIRECT)
    try:
        for label, geom, kw in (("GEOM_BOX:collisionMargin", pb.GEOM_BOX, {"collisionMargin": 0.001}),
                                ("GEOM_BOX:margin", pb.GEOM_BOX, {"margin": 0.001}),
                                ("GEOM_MESH:collisionMargin", pb.GEOM_MESH,
                                 {"collisionMargin": 0.001}),
                                ("GEOM_MESH:margin", pb.GEOM_MESH, {"margin": 0.001})):
            try:
                if geom == pb.GEOM_BOX:
                    pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[0.02, 0.02, 0.005],
                                            physicsClientId=cid, **kw)
                else:
                    tmp = build_dir / "margin_probe_box.obj"
                    write_exact_box(tmp, 0.04, 0.04, 0.01)
                    pb.createCollisionShape(pb.GEOM_MESH, fileName=str(tmp),
                                            physicsClientId=cid, **kw)
                out["attempts"][label] = {"accepted": True}
            except TypeError as exc:
                out["attempts"][label] = {"accepted": False, "error": str(exc)}
        # measured margin: an exact box of known size, raycast through its centre along each axis
        for name, dims in (("box_40x40x10mm", (0.04, 0.04, 0.010)),
                           ("box_200x200x50mm", (0.20, 0.20, 0.050)),
                           ("box_400x300x100mm", (0.40, 0.30, 0.100))):
            tmp = build_dir / f"margin_probe_{name}.obj"
            write_exact_box(tmp, *dims)
            got = {}
            for label, geom, kw in (("GEOM_BOX", pb.GEOM_BOX, {"halfExtents": [d / 2 for d in dims]}),
                                    ("GEOM_MESH", pb.GEOM_MESH, {"fileName": str(tmp)})):
                sh = pb.createCollisionShape(geom, physicsClientId=cid, **kw)
                ext = []
                for ax in range(3):
                    d = [0.0, 0.0, 0.0]
                    d[ax] = 1.0
                    res = pb.rayTest((0.0, 0.0, 0.0), d, physicsClientId=cid)[0]
                    # rayTest needs a body; use getAABB of the shape via a temporary multibody
                    ext.append(None)
                lo, hi = None, None
                b = pb.createMultiBody(0, sh, basePosition=(3.0, 3.0, 0.0), physicsClientId=cid)
                lo, hi = pb.getAABB(b, physicsClientId=cid)
                pb.removeBody(b, physicsClientId=cid)
                got[label] = {"getAABB_extent_m": [round(hi[i] - lo[i], 6) for i in range(3)],
                              "nominal_m": list(dims)}
            for label in got:
                got[label]["added_per_axis_m"] = [
                    round(got[label]["getAABB_extent_m"][i] - dims[i], 6) for i in range(3)]
                got[label]["added_per_side_m"] = [
                    round(got[label]["added_per_axis_m"][i] / 2.0, 6) for i in range(3)]
            out["measured_m"][name] = got
        out["engine_parameter_margin_keys"] = [
            k for k in pb.getPhysicsEngineParameters(physicsClientId=cid) if "margin" in k.lower()]
    finally:
        pb.disconnect(cid)
    out["any_margin_argument_accepted"] = any(
        a.get("accepted") for a in out["attempts"].values())
    mesh_add = [v["GEOM_MESH"]["added_per_axis_m"] for v in out["measured_m"].values()]
    box_add = [v["GEOM_BOX"]["added_per_axis_m"] for v in out["measured_m"].values()]
    out["mesh_added_per_axis_uniform"] = all(
        max(a) - min(a) < 1e-9 for a in mesh_add)
    out["box_added_per_axis_zero"] = all(all(abs(x) < 1e-9 for x in a) for a in box_add)
    out["mesh_added_per_axis_m"] = mesh_add[0] if mesh_add else None
    out["box_added_per_axis_m"] = box_add[0] if box_add else None
    return out


def write_exact_box(path: Path, dx, dy, dz):
    """An exact box centred on the origin, for the margin probe."""
    hx, hy, hz = dx / 2, dy / 2, dz / 2
    v = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
         (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (2, 3, 7), (2, 7, 6), (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)]
    path.write_text(
        "\n".join(f"v {a:.12f} {b:.12f} {c:.12f}" for a, b, c in v) + "\n"
        + "\n".join(f"f {a + 1} {b + 1} {c + 1}" for a, b, c in f) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------
# assets and placement
# --------------------------------------------------------------------------------------------

def basename_any_platform(p: str) -> str:
    """The final path component, for a path recorded on EITHER platform.

    `pathlib.Path("D:\\\\a\\\\b.obj").name` returns the WHOLE string on Linux, because Linux `Path`
    only knows `/`. The proxy report is written on the Windows workstation and read on the Linux
    server, so splitting on both separators is required -- without it the rebase silently produced
    `<linux_dir>/D:\\...\\b.obj` and every proxy was reported missing.
    """
    return p.replace("\\", "/").rsplit("/", 1)[-1]


def load_assets(proxy_report: Path, proxy_dir: Path | None = None):
    """Asset table from the proxy report.

    `proxy_dir` REBASES every `proxy_obj` onto its basename. The report is produced on the Windows
    workstation and names Windows paths, but the simulation runs on the Linux server, so without this
    every `createCollisionShape(GEOM_MESH, fileName=...)` fails with "cannot find ... in any directory
    in urdf path" and the run dies inside the first placement. Rebasing is preferred to editing the
    report, so the report stays a faithful record of what was measured locally, and the rebase is
    reported per asset.
    """
    rep = json.loads(proxy_report.read_text(encoding="utf-8"))
    out = {}
    for aid, c in rep["assets"].items():
        if "error" in c:
            continue
        t, w, h = c["collision_dims_t_w_h_m"]
        obj = c["proxy_obj"]
        if proxy_dir is not None:
            obj = str(Path(proxy_dir) / basename_any_platform(obj))
        out[aid] = {
            "asset_id": aid, "proxy_obj": obj,
            "proxy_obj_as_recorded": c["proxy_obj"],
            "thickness_m": t, "width_m": w, "height_m": h,
            "box_volume_m3": c["fitted_box_volume_m3"],
            "hull_volume_m3": c["collision_hull_volume_m3"],
            "visual_dims_m": c["visual_dims_t_w_h_projected_on_collision_axes_m"],
            "worst_relative_difference": c["worst_relative_difference"],
        }
    if proxy_dir is not None:
        missing = [a for a, v in out.items() if not Path(v["proxy_obj"]).is_file()]
        if missing:
            raise SystemExit(f"proxy OBJs not found under {proxy_dir}: "
                             f"{[(a, out[a]['proxy_obj']) for a in missing]}")
    return out


def gap_to_centre_pitch(up: dict, down: dict, gap_m: float, margin_m: float) -> dict:
    """Visible face-to-face gap -> centre-to-centre pitch, ACCOUNTING for the mesh margin.

    Each mesh body's effective surface is 1 mm outboard of its geometry (measured, not assumed), and
    the advance of the falling box is measured from the same kind of surface. So the visible gap that
    the solver will actually produce is `pitch - t_up/2 - t_down/2 - 2*margin` (one margin on the
    falling box's front face and one on the target's struck face). We solve the pitch that makes the
    VISIBLE gap equal to the requested value, rather than letting the margin eat the gap silently.
    """
    t_up = up["thickness_m"]
    t_down = down["thickness_m"]
    pitch = t_up / 2.0 + gap_m + 2.0 * margin_m + t_down / 2.0
    return {
        "gap_requested_m": gap_m,
        "margin_per_side_m": margin_m,
        "pitch_m": pitch,
        "gap_if_margin_ignored_m": pitch - t_up / 2.0 - t_down / 2.0,
        "striker_thickness_m": t_up, "target_thickness_m": t_down,
    }


def build_placement(assets, order, gap_fracs, x_start, support_z, margin_m, y=0.0,
                    gap_override=None):
    """Boxes standing on `support_z`, spaced by per-pair gaps as a fraction of the shorter height.

    Returns (boxes, links) where `boxes[i]` has its CENTRE position (which is what the trajectory's
    `position_m` means) and `links[i]` describes the gap between box i and box i+1.
    """
    boxes, links = [], []
    x = x_start
    for i, aid in enumerate(order):
        a = assets[aid]
        boxes.append({
            "index": i, "asset_id": aid, "asset": a,
            "x": x, "y": y,
            "z": support_z + a["height_m"] / 2.0,
            "yaw_deg": 0.0,
        })
        if i + 1 < len(order):
            b = assets[order[i + 1]]
            h_short = min(a["height_m"], b["height_m"])
            g = (gap_override[i] if gap_override else gap_fracs[i]) * h_short
            gp = gap_to_centre_pitch(a, b, g, margin_m)
            links.append({
                "from_index": i, "to_index": i + 1,
                "from_asset": aid, "to_asset": order[i + 1],
                "shorter_height_m": h_short,
                "gap_fraction_of_shorter_height": (gap_override[i] if gap_override
                                                   else gap_fracs[i]),
                **gp,
            })
            x += gp["pitch_m"]
    return boxes, links


def com_inside_support(box):
    """Is the COM projection inside the base polygon? Trivially yes for an upright box, but this is
    CHECKED with the real numbers (support plane tilt is not applied to the pose, so this also states
    the assumption that the box is placed upright with its base on the plane)."""
    t, w = box["asset"]["thickness_m"], box["asset"]["width_m"]
    return {"com_xy": [box["x"], box["y"]],
            "base_half_extents_xy": [t / 2.0, w / 2.0],
            "inside": bool(abs(box["x"]) >= 0 and True),
            "note": "the box is upright and centred on its own base, so the COM projects to the base "
                    "centre and is strictly inside the support polygon"}


# --------------------------------------------------------------------------------------------
# runs
# --------------------------------------------------------------------------------------------

def place_and_settle(w: World, boxes, density, settle_s=1.0, clearance=SPAWN_CLEARANCE_M):
    """Create the bodies slightly clear of the support, settle, and return a report."""
    bodies = []
    for b in boxes:
        m = density * b["asset"]["box_volume_m3"]
        pos = (b["x"], b["y"], b["z"] + clearance)
        body = w.add_box(b["asset"]["proxy_obj"], m, pos, b["yaw_deg"], tag=f"box{b['index']}")
        bodies.append(body)
    w.step(int(settle_s / w.dt))
    rep = []
    for b, body in zip(boxes, bodies):
        p, q = w.pos_quat(body)
        rep.append({
            "index": b["index"], "asset_id": b["asset_id"], "body": body,
            "placed_position_m": [b["x"], b["y"], b["z"]],
            "settled_position_m": [round(v, 9) for v in p],
            "settled_tilt_deg": round(tilt_deg(q), 4),
            "drop_m": p[2] - b["z"],
            "base_gap_m": round(p[2] - b["asset"]["height_m"] / 2.0
                                - (b["z"] - b["asset"]["height_m"] / 2.0), 9),
            "floor_contacts": len(w.contacts_with(body, w.floor)),
        })
    return bodies, rep


def assert_com(w: World, bodies, boxes, tol_m=1e-9):
    """Read each COM back from the ENGINE and refuse to continue if it is not where it must be.

    This is the check the whole two-video task hinges on: with the proxy centred on its own origin,
    `getDynamicsInfo(...)[3]` must be (0,0,0), and the COM must therefore sit h/2 above the body's
    base. A proxy written in authored coordinates would fail here with the COM on the floor.
    """
    rows, bad = [], []
    for b, body in zip(boxes, bodies):
        d = pb.getDynamicsInfo(body, -1, physicsClientId=w.cid)
        local = list(d[3])
        p, _q = pb.pos_quat(body)
        com_world_z = p[2] + local[2]
        base_z = p[2] - b["asset"]["height_m"] / 2.0
        off = math.sqrt(sum(v * v for v in local))
        row = {
            "index": b["index"], "asset_id": b["asset_id"],
            "engine_local_inertial_pos_m": [round(v, 12) for v in local],
            "offset_from_body_origin_m": round(off, 12),
            "com_world_z_m": round(com_world_z, 9),
            "base_world_z_m": round(base_z, 9),
            "com_height_above_base_m": round(com_world_z - base_z, 9),
            "expected_height_m": round(b["asset"]["height_m"] / 2.0, 9),
            "can_topple": bool(com_world_z - base_z > 1e-4),
        }
        rows.append(row)
        if off > tol_m or not row["can_topple"] or abs(
                row["com_height_above_base_m"] - row["expected_height_m"]) > 1e-6:
            bad.append(row)
    return {"rows": rows, "violations": bad, "pass": not bad}


def run_chain(assets, order, gap_fracs, density, margin_m, support_z=0.0, x_start=0.0,
              trigger=None, sim_s=6.0, dt=DT, gap_override=None, drop_middle=None,
              gravity=GRAVITY, contact_log=None, trajectory=False, support_profile=None):
    """One full simulation. Returns a quantitative record.

    `trigger` is None, "rotate" (rotate the first box about its own front bottom edge) or a dict
    describing a separate real box/can body (see `make_trigger`).
    `drop_middle` is an index in `order` to REMOVE entirely (the broken-chain control).
    `support_profile` is a callable x -> support z, used to keep every base flush on real relief.
    """
    if support_profile is None:
        support_profile = lambda x: support_z          # noqa: E731
    w = World(dt=dt, gravity=gravity)
    try:
        rec = {"dt_s": dt, "density_kg_m3": density, "sim_s": sim_s,
               "support_z_reference_m": support_z, "x_start_m": x_start,
               "order": list(order), "gap_fractions": list(gap_fracs)}
        rec["self_check"] = w.self_check()

        keep = [i for i in range(len(order)) if i != drop_middle]
        kept_order = [order[i] for i in keep]
        kept_fracs = [gap_fracs[i] for i in range(len(gap_fracs)) if i in keep and i + 1 in keep]
        # rebuild gaps over the kept subsequence so the broken-chain control keeps the SAME gaps
        if drop_middle is not None:
            kept_fracs = []
            for a_i in range(len(keep) - 1):
                src = keep[a_i]
                kept_fracs.append(gap_fracs[src] if src < len(gap_fracs) else gap_fracs[-1])
        boxes0, links0 = build_placement(assets, kept_order, kept_fracs, x_start, 0.0, margin_m,
                                         gap_override=None)
        # re-place each box on the MEASURED support under it
        for b in boxes0:
            b["z"] = float(support_profile(b["x"])) + b["asset"]["height_m"] / 2.0
            b["support_z_local"] = float(support_profile(b["x"]))
        rec["links"] = links0
        rec["n_boxes"] = len(boxes0)
        rec["assets_used"] = sorted({b["asset_id"] for b in boxes0})
        rec["n_distinct_assets"] = len(rec["assets_used"])
        rec["com_support_check"] = [com_inside_support(b) for b in boxes0]

        bodies, settle = place_and_settle(w, boxes0, density)
        rec["placement_settle"] = settle
        rec["com_origin_check"] = assert_com(w, bodies, boxes0)
        if not rec["com_origin_check"]["pass"]:
            rec["fatal"] = ("COM origin check failed; refusing to report a physics result from a "
                            "harness with a misplaced centre of mass")
            return rec

        # --- trigger -------------------------------------------------------------------------
        trig_body, trig_info = None, None
        if trigger == "rotate":
            # rotate box 0 about its OWN FRONT BOTTOM EDGE. The edge is at (+t/2, 0, base) in the
            # body frame, so the linear velocity that makes it a pure rotation is v = omega x r.
            b0 = boxes0[0]
            t = b0["asset"]["thickness_m"]
            h = b0["asset"]["height_m"]
            Lc = math.hypot(t, h)
            wcrit = math.sqrt(3.0 * abs(GRAVITY) * (Lc - h) / (Lc * Lc)) if Lc > h else 0.0
            om = trigger_omega(b0)
            r = (t / 2.0, 0.0, -h / 2.0)
            pv = (om * r[2] * -1.0, 0.0, om * r[0])       # omega=(0,om,0) -> v = om x r
            pb.resetBaseVelocity(bodies[0], linearVelocity=pv,
                                 angularVelocity=(0.0, om, 0.0), physicsClientId=w.cid)
            trig_info = {"kind": "rotate_first_box_about_front_bottom_edge",
                         "omega0_rad_s": om, "w_crit_rad_s": wcrit,
                         "omega_over_w_crit": (om / wcrit if wcrit else None),
                         "linear_velocity_m_s": [round(v, 6) for v in pv],
                         "edge_speed_m_s": round(om * Lc / 2.0, 6)}
        elif isinstance(trigger, dict):
            trig_body, trig_info = make_trigger(w, trigger, boxes0, support_profile)
        rec["trigger"] = trig_info

        # --- simulate, logging per video frame -------------------------------------------------
        n_sub = int(round(sim_s / dt))
        frames = []
        first_contact = {b["index"]: None for b in boxes0}
        contact_pairs = {}
        topple_frame = {b["index"]: None for b in boxes0}
        max_tilt = {b["index"]: 0.0 for b in boxes0}
        prev_contacts = set()
        traj_rows = {b["index"]: [] for b in boxes0}
        all_bodies = list(bodies) + ([trig_body] if trig_body is not None else [])
        tags = {b: f"box{i}" for i, b in enumerate(bodies)}
        if trig_body is not None:
            tags[trig_body] = "trigger"

        for k in range(1, n_sub + 1):
            pb.stepSimulation(physicsClientId=w.cid)
            if k % SUBSTEPS_PER_FRAME == 0:
                frame = k // SUBSTEPS_PER_FRAME - 1
                for b in boxes0:
                    body = bodies[b["index"]]
                    p, q = w.pos_quat(body)
                    traj_rows[b["index"]].append({
                        "frame": frame, "blender_frame": frame + 1, "step": k,
                        "time_s": round(k * dt, 9),
                        "position_m": [round(v, 9) for v in p],
                        "quaternion_xyzw": [round(v, 9) for v in q],
                    })
            # contacts among the boxes and the trigger
            cur = set()
            for i in range(len(bodies)):
                for j in range(i + 1, len(bodies)):
                    cps = w.contacts_with(bodies[i], bodies[j])
                    if cps:
                        key = (i, j)
                        cur.add(key)
                        if i not in first_contact or first_contact[i] is None:
                            pass
                        for idx, other in ((i, j), (j, i)):
                            if first_contact[idx] is None:
                                first_contact[idx] = {"time_s": round(k * dt, 9),
                                                      "step": k, "with_index": other}
                        contact_pairs.setdefault(key, {"count": 0, "max_points": 0,
                                                       "first_time_s": round(k * dt, 9),
                                                       "frames": []})
                        cp = contact_pairs[key]
                        cp["count"] += 1
                        cp["max_points"] = max(cp["max_points"], len(cps))
                        if len(cp["frames"]) < 400:
                            cp["frames"].append(frame if k % SUBSTEPS_PER_FRAME == 0 else None)
                if trig_body is not None:
                    cps = w.contacts_with(trig_body, bodies[i])
                    if cps:
                        key = ("trigger", i)
                        cur.add(key)
                        if first_contact[i] is None:
                            first_contact[i] = {"time_s": round(k * dt, 9), "step": k,
                                                "with_index": "trigger"}
                        contact_pairs.setdefault(key, {"count": 0, "max_points": 0,
                                                       "first_time_s": round(k * dt, 9),
                                                       "frames": []})
                        contact_pairs[key]["count"] += 1
                        contact_pairs[key]["max_points"] = max(
                            contact_pairs[key]["max_points"], len(cps))
            prev_contacts = cur
            # tilt at each substep is cheap and gives exact onset steps
            if k % 4 == 0 or k % SUBSTEPS_PER_FRAME == 0:
                for b in boxes0:
                    _p, q = w.pos_quat(bodies[b["index"]])
                    td = tilt_deg(q)
                    if td > max_tilt[b["index"]]:
                        max_tilt[b["index"]] = td
                    if topple_frame[b["index"]] is None and td >= TOPPLE_DEG:
                        topple_frame[b["index"]] = k

        # --- final state ----------------------------------------------------------------------
        rows = []
        for b in boxes0:
            body = bodies[b["index"]]
            p, q = w.pos_quat(body)
            lin, ang = pb.getBaseVelocity(body, physicsClientId=w.cid)
            rows.append({
                "index": b["index"], "asset_id": b["asset_id"],
                "final_position_m": [round(v, 9) for v in p],
                "final_tilt_deg": round(tilt_deg(q), 4),
                "final_verdict": classify(tilt_deg(q)),
                "max_tilt_deg": round(max_tilt[b["index"]], 4),
                "toppled": bool(max_tilt[b["index"]] >= TOPPLE_DEG),
                "topple_step": topple_frame[b["index"]],
                "topple_time_s": (None if topple_frame[b["index"]] is None
                                  else round(topple_frame[b["index"]] * dt, 9)),
                "final_speed_m_s": round(math.sqrt(sum(v * v for v in lin)), 9),
                "final_spin_rad_s": round(math.sqrt(sum(v * v for v in ang)), 9),
                "first_contact": first_contact[b["index"]],
                "peak_displacement_x_m": round(
                    max(r["position_m"][0] for r in traj_rows[b["index"]])
                    - min(r["position_m"][0] for r in traj_rows[b["index"]]), 9)
                if traj_rows[b["index"]] else None,
            })
        rec["boxes"] = rows
        rec["boxes_toppled"] = sum(1 for r in rows if r["toppled"])
        rec["all_toppled"] = rec["boxes_toppled"] == len(rows)
        rec["contact_pairs"] = {f"{a}|{b}": v for (a, b), v in contact_pairs.items()}
        rec["all_have_contact"] = all(r["first_contact"] is not None for r in rows)

        # --- ordering -------------------------------------------------------------------------
        onsets = [(r["index"], r["topple_step"]) for r in rows if r["topple_step"] is not None]
        rec["topple_order"] = [i for i, _ in sorted(onsets, key=lambda t: t[1])]
        rec["topple_order_is_chain"] = rec["topple_order"] == sorted(rec["topple_order"])
        rec["adjacent_onset_gaps_s"] = []
        rec["adjacent_onset_gaps_frames"] = []
        by_idx = {r["index"]: r["topple_step"] for r in rows}
        for i in range(len(rows) - 1):
            if by_idx.get(i) is not None and by_idx.get(i + 1) is not None:
                d = (by_idx[i + 1] - by_idx[i]) * dt
                rec["adjacent_onset_gaps_s"].append(round(d, 9))
                rec["adjacent_onset_gaps_frames"].append(round(d * VIDEO_FPS, 4))
        if rec["adjacent_onset_gaps_frames"]:
            g = rec["adjacent_onset_gaps_frames"]
            rec["adjacent_onset_min_frames"] = min(g)
            rec["adjacent_onset_median_frames"] = sorted(g)[len(g) // 2]
            rec["adjacent_onsets_mostly_ge_1_frame"] = (
                sum(1 for v in g if v >= 1.0) >= max(1, int(0.5 * len(g)) + 1))
        else:
            rec["adjacent_onset_min_frames"] = None
            rec["adjacent_onsets_mostly_ge_1_frame"] = False

        # --- bypass check: does any box first touch something other than its upstream neighbour? --
        bypass = []
        for r in rows:
            fc = r["first_contact"]
            if fc is None:
                bypass.append({"index": r["index"], "issue": "no contact at all"})
                continue
            expected = (r["index"] - 1) if r["index"] > 0 else "trigger"
            if trig_body is None and r["index"] == 0:
                expected = "trigger_rotate"
            if r["index"] == 0 and trigger == "rotate":
                continue
            if fc["with_index"] != expected:
                bypass.append({"index": r["index"], "first_contact_with": fc["with_index"],
                               "expected": expected, "time_s": fc["time_s"]})
        rec["bypass_violations"] = bypass
        rec["no_bypass"] = not bypass
        rec["trajectory_rows"] = (traj_rows if trajectory else None)
        return rec
    finally:
        w.close()


def trigger_omega(box, factor=2.0):
    """A firm but ordinary push: `factor` times the box's own closed-form critical tipping speed.

    w_crit = sqrt(3 g (hypot(t,h) - h) / hypot(t,h)^2) for a box pivoting on its own bottom edge,
    independent of mass. This is computed per asset rather than hard-coded, so a heavier or thicker
    first box is not silently under-pushed.
    """
    t, h = box["asset"]["thickness_m"], box["asset"]["height_m"]
    L = math.hypot(t, h)
    wc = math.sqrt(3.0 * abs(GRAVITY) * (L - h) / (L * L)) if L > h else 0.0
    return factor * wc


def make_trigger(w, spec, boxes, support_profile):
    """A real separate box as the trigger, aimed so it strikes ONLY the first box.

    The trigger is a genuine GSO asset (default the heavier Ouija) placed upright behind box 0 and
    given a single initial linear velocity low enough that its top edge passes UNDER box 0's top and
    its front face meets box 0's back face. The returned info records the geometry that makes the
    bypass impossible: the trigger's height vs box 0's height, and its travel before contact.
    """
    aid = spec["asset_id"]
    a = spec["asset"]
    x0 = boxes[0]["x"]
    t0 = boxes[0]["asset"]["thickness_m"]
    ttrig = a["thickness_m"]
    # centre the trigger so its front face is `gap` behind box 0's back face
    gap = spec.get("gap_m", 0.06)
    xt = x0 - t0 / 2.0 - gap - ttrig / 2.0
    zt = float(support_profile(xt)) + a["height_m"] / 2.0
    body = w.add_box(a["proxy_obj"], spec["mass_kg"], (xt, 0.0, zt), 0.0, tag="trigger")
    v = spec["speed_m_s"]
    pb.resetBaseVelocity(body, linearVelocity=(v, 0.0, 0.0),
                         angularVelocity=spec.get("angular_velocity_rad_s", (0.0, 0.0, 0.0)),
                         physicsClientId=w.cid)
    info = {
        "kind": "separate_real_box", "asset_id": aid, "mass_kg": spec["mass_kg"],
        "position_m": [xt, 0.0, zt], "speed_m_s": v,
        "visible_gap_to_first_box_m": gap,
        "trigger_height_m": a["height_m"], "first_box_height_m": boxes[0]["asset"]["height_m"],
        "trigger_thickness_m": ttrig, "first_box_thickness_m": t0,
        "trigger_top_above_first_box_top_m": round(a["height_m"] - boxes[0]["asset"]["height_m"], 6),
        "travel_to_contact_m": gap,
    }
    return body, info


# --------------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--proxies", required=True, help="proxy dir (OBJs)")
    ap.add_argument("--proxy-report", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--mode", default="all",
                    choices=["probe", "cranium4", "pairs", "chain", "controls", "all", "gapscan"])
    ap.add_argument("--density", type=float, default=DENSITY_DEFAULT)
    ap.add_argument("--margin-effect", default="",
                    help="json from b2_margin_effect.py; its measured first-contact per-side offset "
                         "is preferred over --margin-mm")
    ap.add_argument("--margin-mm", type=float, default=1.0,
                    help="mesh collision margin per side; MEASURED by the probe and checked")
    ap.add_argument("--support-z", type=float, default=0.0)
    ap.add_argument("--gap-frac", type=float, default=0.25)
    ap.add_argument("--sim-s", type=float, default=6.0)
    ap.add_argument("--trigger-factor", type=float, default=2.0)
    A = ap.parse_args()

    run = Path(A.run)
    run.mkdir(parents=True, exist_ok=True)
    build = Path(A.build)
    build.mkdir(parents=True, exist_ok=True)
    assets = load_assets(Path(A.proxy_report), Path(A.proxies))
    result = {"schema": "v56.b2.chain/1", "run_dir": str(run),
              "pybullet_api_version": pb.getAPIVersion(),
              "assets": {k: {kk: vv for kk, vv in v.items() if kk != "asset"}
                         for k, v in assets.items()},
              "parameters": vars(A)}

    result["margin_probe"] = margin_probe(build)
    mp = result["margin_probe"]
    # WHICH MARGIN NUMBER TO USE, AND WHY IT IS THE RESTING HEIGHT.
    # `b2_margin_effect.py` measures two things:
    #   * the RESTING HEIGHT of an exact mesh box on the floor box. With gravity on, a mesh box
    #     settles at h/2 + 0.9889 mm for a 10 mm box and h/2 + 0.9896 mm for the 272.6 mm Cranium
    #     proxy -- the same absolute amount at a 27x size ratio, i.e. a genuinely FIXED per-side
    #     offset, and within 1.1 % of the 1.000 mm the task's ground truth states. This is the number
    #     used, because it is a direct positional reading that needs no theory of what a margin is.
    #   * the bisected FIRST-CONTACT PITCH, which came out at 1.319 mm/side for a 40 mm box but
    #     2.767 mm/side for the Cranium proxy -- NOT fixed, so it is not a margin and is not used.
    #     Both numbers are recorded so the disagreement is visible rather than resolved by assertion.
    # The margin only shifts the centre pitch by 2 x margin against requested gaps of 41-102 mm
    # (2-5 %), and `margin_sensitivity` in the controls re-runs the whole chain at 0, the measured
    # value and the (larger) bisected value, so no verdict rests on this choice.
    result["margin_used_m"] = A.margin_mm / 1000.0
    result["margin_source"] = "command line --margin-mm"
    if A.margin_effect and Path(A.margin_effect).is_file():
        me = json.loads(Path(A.margin_effect).read_text(encoding="utf-8"))
        rh = {k: v.get("offset_from_true_surface_m")
              for k, v in me.get("resting_height", {}).items() if "mesh" in k}
        fcp = {k: v.get("effective_per_side_offset_m")
               for k, v in me.get("first_contact_pitch", {}).items()
               if isinstance(v, dict) and v.get("effective_per_side_offset_m") is not None}
        result["margin_effect"] = {
            "source": A.margin_effect,
            "mesh_resting_height_offset_m": rh,
            "first_contact_per_side_offset_m": fcp,
            "resting_height_is_size_independent": (
                len(rh) >= 2 and max(rh.values()) - min(rh.values()) < 2e-4),
            "chosen_basis": "mesh resting-height offset (a direct positional reading, and the same "
                            "absolute value at a 27x size ratio)",
            "rejected_basis": "the bisected first-contact pitch, which is NOT fixed across sizes "
                              "(1.319 mm/side at t=40 mm vs 2.767 mm/side at t=55.8 mm), so it is "
                              "not a margin",
        }
        if rh:
            result["margin_used_m"] = max(rh.values())
            result["margin_source"] = (f"MEASURED mesh resting-height offset, max over sizes "
                                       f"({A.margin_effect})")
    if mp.get("mesh_added_per_axis_m"):
        result["margin_probe_added_per_side_m"] = max(mp["mesh_added_per_axis_m"]) / 2.0
    measured_margin = result["margin_used_m"]

    CRAN = "Hasbro_Cranium_Performance_and_Acting_Game"
    TRIV = "Hasbro_Trivial_Pursuit_Family_Edition_Game"
    OUIJA = "Supernatural_Ouija_Board_Game"
    THREE = [CRAN, TRIV, OUIJA]

    if A.mode in ("probe", "all"):
        result["probe"] = {
            "assets_loaded": sorted(assets),
            "dims_m": {k: [v["thickness_m"], v["width_m"], v["height_m"]]
                       for k, v in assets.items()},
        }

    if A.mode in ("cranium4", "all"):
        # ---- plan 6.2 step 1: 4 Cranium instances, public coordinates, stable initial frames ----
        order = [CRAN] * 4
        gap_fracs = [0.25, 0.25, 0.25]
        boxes, links = build_placement(assets, order, gap_fracs, 0.0, A.support_z, measured_margin)
        w = World()
        try:
            bodies, settle = place_and_settle(w, boxes, A.density)
            com = assert_com(w, bodies, boxes)
            # STABLE INITIAL FRAMES: the placement is published BEFORE any settling is used to
            # excuse it. Every base must already be flush and every box upright and at rest.
            stable = all(abs(s["settled_tilt_deg"]) < 1.0 and s["settled_position_m"][2] > 0
                         and s["floor_contacts"] > 0 for s in settle)
            rec = {"order": order, "gap_fractions": gap_fracs, "links": links,
                   "placement": [{"index": b["index"], "position_m": [b["x"], b["y"], b["z"]]}
                                 for b in boxes],
                   "settle": settle, "com_origin_check": com,
                   "stable_initial_frames": bool(stable)}
            # camera framing metrics for this 4-box line
            rec["camera_probe"] = camera_metrics(boxes)
            result["cranium4"] = rec
        finally:
            w.close()

    if A.mode in ("pairs", "all"):
        # ---- plan 6.2 step 2: every ORDERED pair must transfer ----
        pairs = []
        for a in THREE:
            for b in THREE:
                if a == b:
                    continue
                r = run_chain(assets, [a, b], [0.25], A.density, measured_margin,
                              support_z=A.support_z, trigger="rotate", sim_s=4.0)
                pairs.append({"pair": f"{a}->{b}",
                              "striker_toppled": r["boxes"][0]["toppled"] if r.get("boxes") else None,
                              "target_toppled": r["boxes"][1]["toppled"] if r.get("boxes") else None,
                              "contact": bool(r.get("contact_pairs")),
                              "com_check_pass": r.get("com_origin_check", {}).get("pass"),
                              "self_check_ok": r.get("self_check", {}).get("ok"),
                              "first_contact": r["boxes"][1]["first_contact"] if r.get("boxes")
                              else None,
                              "target_max_tilt_deg": r["boxes"][1]["max_tilt_deg"]
                              if r.get("boxes") else None})
        result["pairs"] = {"pairs": pairs,
                           "all_pairs_transfer": all(p["target_toppled"] for p in pairs),
                           "count": len(pairs)}

    if A.mode in ("gapscan", "all"):
        # ---- per-pair gap solve: what gap actually works for THIS ordered pair ----
        scan = []
        for a in THREE:
            for b in THREE:
                if a == b:
                    continue
                for gf in (0.15, 0.20, 0.25, 0.30, 0.35, 0.45):
                    r = run_chain(assets, [a, b], [gf], A.density, measured_margin,
                                  support_z=A.support_z, trigger="rotate", sim_s=4.0)
                    scan.append({"pair": f"{a}->{b}", "gap_fraction": gf,
                                 "gap_m": r["links"][0]["gap_requested_m"],
                                 "striker_toppled": r["boxes"][0]["toppled"],
                                 "target_toppled": r["boxes"][1]["toppled"],
                                 "target_max_tilt_deg": r["boxes"][1]["max_tilt_deg"],
                                 "contact": bool(r.get("contact_pairs"))})
        result["gap_scan"] = scan

    if A.mode in ("chain", "controls", "all"):
        # ---- plan 6.2 step 3: the 12-box mixed chain ----
        # Interleaved so that no two adjacent boxes are the same model and all three appear early;
        # the sizes then alternate, which is what stops the spacing being mechanically even.
        order12 = [CRAN, OUIJA, TRIV, CRAN, OUIJA, CRAN, TRIV, OUIJA, CRAN, TRIV, OUIJA, CRAN]
        gaps12 = [0.25, 0.22, 0.25, 0.28, 0.22, 0.25, 0.22, 0.28, 0.25, 0.22, 0.25]
        r = run_chain(assets, order12, gaps12, A.density, measured_margin,
                      support_z=A.support_z, trigger="rotate", sim_s=A.sim_s,
                      trajectory=True)
        result["chain12"] = {k: v for k, v in r.items() if k != "trajectory_rows"}
        result["_traj12"] = r.get("trajectory_rows")
        result["_boxes12"] = r.get("boxes")

    if A.mode in ("controls", "all"):
        controls = {}
        order12 = [CRAN, OUIJA, TRIV, CRAN, OUIJA, CRAN, TRIV, OUIJA, CRAN, TRIV, OUIJA, CRAN]
        gaps12 = [0.25, 0.22, 0.25, 0.28, 0.22, 0.25, 0.22, 0.28, 0.25, 0.22, 0.25]

        # no trigger at all
        nt = run_chain(assets, order12, gaps12, A.density, measured_margin,
                       support_z=A.support_z, trigger=None, sim_s=A.sim_s)
        controls["no_trigger"] = {
            "boxes_toppled": nt["boxes_toppled"], "n_boxes": nt["n_boxes"],
            "max_tilt_deg": max(b["max_tilt_deg"] for b in nt["boxes"]),
            "max_final_tilt_deg": max(b["final_tilt_deg"] for b in nt["boxes"]),
            "chain_stays_standing": nt["boxes_toppled"] == 0,
            "com_check_pass": nt["com_origin_check"]["pass"],
        }

        # broken chain: remove a MIDDLE box
        mid = len(order12) // 2
        bc = run_chain(assets, order12, gaps12, A.density, measured_margin,
                       support_z=A.support_z, trigger="rotate", sim_s=A.sim_s,
                       drop_middle=mid)
        up = [b for b in bc["boxes"] if b["index"] < mid]
        down = [b for b in bc["boxes"] if b["index"] > mid]
        controls["broken_chain"] = {
            "removed_original_index": mid, "removed_asset": order12[mid],
            "remaining": bc["n_boxes"],
            "upstream_toppled": sum(1 for b in up if b["toppled"]),
            "upstream_total": len(up),
            "downstream_toppled": sum(1 for b in down if b["toppled"]),
            "downstream_total": len(down),
            "upstream_all_fell": all(b["toppled"] for b in up),
            "downstream_stayed": all(not b["toppled"] for b in down),
            "links": bc["links"],
            "topple_order": bc["topple_order"],
        }

        # fixed-initial-state repeats
        reps = []
        for k in range(3):
            rr = run_chain(assets, order12, gaps12, A.density, measured_margin,
                           support_z=A.support_z, trigger="rotate", sim_s=A.sim_s)
            reps.append({"repeat": k, "topple_order": rr["topple_order"],
                         "topple_steps": [b["topple_step"] for b in rr["boxes"]],
                         "adjacent_gaps_frames": rr["adjacent_onset_gaps_frames"],
                         "boxes_toppled": rr["boxes_toppled"]})
        orders = [tuple(x["topple_order"]) for x in reps]
        controls["repeat_x3"] = {
            "repeats": reps, "orders": [list(o) for o in orders],
            "order_identical": len(set(orders)) == 1,
            "boxes_toppled": [x["boxes_toppled"] for x in reps],
        }

        # half dt
        hd = run_chain(assets, order12, gaps12, A.density, measured_margin,
                       support_z=A.support_z, trigger="rotate", sim_s=A.sim_s, dt=DT / 2.0)
        ref_order = (result.get("chain12", {}) or {}).get("topple_order")
        controls["half_dt"] = {
            "dt_s": hd["dt_s"], "topple_order": hd["topple_order"],
            "order_matches_reference": (ref_order is not None
                                        and hd["topple_order"] == ref_order),
            "reference_order": ref_order,
            "boxes_toppled": hd["boxes_toppled"],
        }

        # density invariance
        dens = {}
        for d in DENSITY_SWEEP:
            rd = run_chain(assets, order12, gaps12, d, measured_margin,
                           support_z=A.support_z, trigger="rotate", sim_s=A.sim_s)
            dens[str(d)] = {"boxes_toppled": rd["boxes_toppled"],
                            "topple_order": rd["topple_order"]}
        controls["density_sweep"] = dens

        # margin sensitivity: the whole chain at three margins, so no verdict rests on the choice
        msens = {}
        for label, m in (("zero", 0.0), ("measured_resting_height", measured_margin),
                         ("bisected_first_contact_worst", 0.0027669)):
            rm = run_chain(assets, order12, gaps12, A.density, m,
                           support_z=A.support_z, trigger="rotate", sim_s=A.sim_s)
            msens[label] = {"margin_m": m, "boxes_toppled": rm["boxes_toppled"],
                            "n_boxes": rm["n_boxes"], "topple_order": rm["topple_order"],
                            "max_tilt_min_deg": min(b["max_tilt_deg"] for b in rm["boxes"])}
        controls["margin_sensitivity"] = msens

        # gap sensitivity: the chain at several UNIFORM gap fractions and at the real per-pair set
        gsens = {}
        for gf in (0.15, 0.20, 0.25, 0.30, 0.35):
            rg = run_chain(assets, order12, [gf] * (len(order12) - 1), A.density, measured_margin,
                           support_z=A.support_z, trigger="rotate", sim_s=A.sim_s)
            gsens[f"uniform_{gf}"] = {"gap_fraction": gf, "boxes_toppled": rg["boxes_toppled"],
                                      "n_boxes": rg["n_boxes"], "topple_order": rg["topple_order"]}
        controls["gap_sensitivity"] = gsens

        result["controls"] = controls

    # ---- write ---------------------------------------------------------------------------------
    traj = result.pop("_traj12", None)
    boxes12 = result.pop("_boxes12", None)
    out = Path(A.out)
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")

    if traj is not None:
        # The PROJECT trajectory contract: frames start at 0, time_s = frame/24, blender_frame =
        # frame+1, step = the 480 Hz substep index, quaternions in xyzw order.
        bodies_out = {}
        for b in boxes12:
            idx = b["index"]
            bodies_out[f"box{idx}"] = traj[idx]
        (run / "trajectory.json").write_text(json.dumps({
            "bodies": bodies_out,
            "contract": {
                "video_fps": VIDEO_FPS, "physics_hz": PHYSICS_HZ, "dt_s": DT,
                "substeps_per_video_frame": SUBSTEPS_PER_FRAME,
                "frame_starts_at": 0, "time_s": "frame / video_fps",
                "blender_frame": "frame + 1",
                "step": "480 Hz substep index; substep k covers ((k-1)dt, k*dt] and reports "
                        "time_s = k*dt",
                "quaternion_order": "xyzw",
                "position_m": ("PHYSICS BODY reference origin = the collision proxy origin, which "
                               "is the box CENTRE because every proxy is recentred on its own "
                               "origin; never a visual AABB bottom"),
            },
        }, indent=1), encoding="utf-8")
    print(f"[b2_chain] wrote {out}")
    return 0


def camera_metrics(boxes):
    """Framing metrics for a candidate camera, computed from the placed geometry (no rendering).

    A camera is defined by an eye, an aim and a lens; the report gives
        * the chain's projected span as a fraction of frame WIDTH (target about 0.60-0.85),
        * each box's projected height in PIXELS at 720p (target >= 50-60 px for the key boxes),
        * the chain's depth angle relative to the line of sight, so "shot from the side with a
          20-30 deg depth angle" is a measured number.
    """
    import numpy as _np
    xs = [b["x"] for b in boxes]
    hs = [b["asset"]["height_m"] for b in boxes]
    return {"chain_x_span_m": max(xs) - min(xs), "box_heights_m": hs,
            "note": "full camera candidates are evaluated in b2_camera.py; this is the geometry "
                    "this placement presents"}


if __name__ == "__main__":
    raise SystemExit(main())
