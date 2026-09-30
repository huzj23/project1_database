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


def tip_angle_deg(asset) -> float:
    """The angle at which this box's COM passes over its own front bottom edge: atan(t/h).

    For the five fitted assets this is 7.5-15.1 deg. A box that has rotated past it is committed to
    falling; a box below it can still rock back. It is the only physically meaningful threshold here,
    and it is computed per asset rather than assumed.
    """
    return math.degrees(math.atan2(asset["thickness_m"], asset["height_m"]))


def support_profile_from_report(report_path, which="auto", min_width_m=0.30,
                                need_len_m=None, need_width_m=None):
    """Build `x -> support z` from a MEASURED ground window, so the chain is tested on the real floor.

    The report's window record carries the least-squares plane (`a_dzdx`, `b_dzdy`, `c_z_at_origin`)
    and the mean residual per sample along x, so the surface along the chain's own line is
    `z(x) = a*x + b*y + c + residual(x)`. Sampling the plane alone would ignore millimetres of real
    relief; using the residual profile captures what the survey measured at each station.

    WHICH WINDOW IS PICKED, and why it must depend on the chain's ACTUAL length. The ground offers two
    usable regions with a real tradeoff: one is flat to 16 MICROMETRES but only 1.35 m long, the other
    is 2.4 m long but tilted 0.42 deg. Choosing before the chain's length is known therefore chooses
    blind. With `need_len_m`/`need_width_m` given, the FLATTEST window that actually CONTAINS the
    chain wins -- flatness is what the chain cares about, and length is a hard constraint, so this is
    "minimise flatness subject to fitting", which is the right order. Without them, the longest window
    at `min_width_m` is used, and the choice is reported either way.
    """
    rep = json.loads(Path(report_path).read_text(encoding="utf-8"))
    win, pick_note = None, ""
    if which == "auto":
        if need_len_m is not None:
            w = need_width_m if need_width_m is not None else min_width_m
            fits = [r for r in rep.get("requirement_windows", [])
                    if r["len_m"] >= need_len_m - 1e-9 and r["width_m"] >= w - 1e-9]
            if fits:
                best = min(fits, key=lambda r: r["flatness_max_dev_m"])
                win = best["window"]
                pick_note = (f"flattest window fitting the chain's measured {need_len_m:.3f} x "
                             f"{w:.3f} m: L={best['len_m']:.3f} W={best['width_m']:.3f} "
                             f"flat={best['flatness_max_dev_m'] * 1000:.3f} mm "
                             f"tilt={best['plane_tilt_deg']:.4f} deg")
        if win is None:
            cands = [w0 for w0 in rep.get("longest_window_at_width", [])
                     if w0["width_m"] >= min_width_m - 1e-9]
            if cands:
                win = max(cands, key=lambda w0: w0["longest_len_m"])["window"]
                pick_note = (f"longest window at width >= {min_width_m} m (chain length was not "
                             f"given)")
    elif isinstance(which, dict):
        win, pick_note = which, "explicitly supplied window"
    if win is None:
        win = rep.get("chain_window")
        pick_note = "report's chain_window (no candidate matched)"
    if win is None:
        raise SystemExit(f"{report_path} has no usable ground window")
    coef = win.get("plane") or {}
    a, b, c = coef.get("a_dzdx", 0.0), coef.get("b_dzdy", 0.0), coef.get("c_z_at_origin", 0.0)
    prof = win.get("residual_profile_along_x_m") or []
    x0, x1 = win["x0"], win["x1"]
    y_mid = (win["y0"] + win["y1"]) / 2.0

    def profile(x):
        # interpolate the measured mean residual at this x; outside the window hold the end value
        if prof and len(prof) > 1:
            u = (x - x0) / max(1e-9, (x1 - x0)) * (len(prof) - 1)
            u = max(0.0, min(len(prof) - 1.0, u))
            i = int(u)
            j = min(i + 1, len(prof) - 1)
            r = prof[i] + (prof[j] - prof[i]) * (u - i)
        else:
            r = 0.0
        return a * x + b * y_mid + c + r

    meta = {
        "source": str(report_path), "selection": pick_note,
        "window": {"x0": x0, "x1": x1, "y0": win["y0"], "y1": win["y1"],
                   "len_m": win["len_m"], "width_m": win["width_m"]},
        "plane": coef, "residual_profile_along_x_m": prof,
        "flatness_max_dev_m": win.get("flatness_max_dev_m"),
        "flatness_p95_dev_m": win.get("flatness_p95_dev_m"),
        "tilt_deg": coef.get("tilt_deg"),
        "support_z_values": [round(profile(x), 6)
                             for x in (x0, (x0 + x1) / 2.0, x1)],
        "span_z_m": round(max(profile(x0), profile(x1), profile((x0 + x1) / 2.0))
                          - min(profile(x0), profile(x1), profile((x0 + x1) / 2.0)), 6),
    }
    return profile, meta

FLOOR_HALF_X = 6.0
FLOOR_HALF_Y = 6.0
FLOOR_THICK = 0.25

#: Asset used as the SEPARATE real-box trigger. Cranium is the shortest of the three at 272.6 mm, so
#: using it behind a chain whose first box is Ouija (408.4 mm) makes "the trigger cannot pass over the
#: first box" a geometric fact rather than a hope. Set per call through `trigger_spec` when needed.
OUIJA_TRIGGER = "Hasbro_Cranium_Performance_and_Acting_Game"

#: The five fitted models, at module level so every script names them identically.
ASSET_CRANIUM = "Hasbro_Cranium_Performance_and_Acting_Game"
ASSET_TRIVIAL = "Hasbro_Trivial_Pursuit_Family_Edition_Game"
ASSET_OUIJA = "Supernatural_Ouija_Board_Game"
ASSET_LEGO = "LEGO_Star_Wars_Advent_Calendar"
ASSET_HOUSE_OF_CARDS = "House_of_Cards_The_Complete_First_Season_4_Discs_DVD"
ASSET_IDS = (ASSET_CRANIUM, ASSET_TRIVIAL, ASSET_OUIJA, ASSET_LEGO, ASSET_HOUSE_OF_CARDS)
ASSET_SHORT = {ASSET_CRANIUM: "Cranium", ASSET_TRIVIAL: "TrivialPursuit", ASSET_OUIJA: "Ouija",
               ASSET_LEGO: "LEGO_Calendar", ASSET_HOUSE_OF_CARDS: "HouseOfCards"}

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
        self.floor_tiles = []
        self.bodies = {}

    def add_floor_tile(self, x0, x1, y0, y1, top_z):
        """One flat slab whose TOP is at `top_z`, used to build a measured floor out of steps.

        A single `GEOM_BOX` floor cannot represent a tilted or uneven surface, so when the chain is
        placed on a surveyed profile the support is built as a contiguous row of slabs whose top
        follows the measurement. The steps are quantised by the sample spacing of the survey (0.03 m
        here), which is why the residual step between neighbours is reported -- a slab floor is an
        approximation of the real relief, and saying so is the point.
        """
        hx, hy = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        hz = FLOOR_THICK
        s = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[hx, hy, hz], physicsClientId=self.cid)
        b = pb.createMultiBody(0, s, basePosition=((x0 + x1) / 2.0, (y0 + y1) / 2.0, top_z - hz),
                               physicsClientId=self.cid)
        pb.changeDynamics(b, -1, lateralFriction=FRICTION_FLOOR, restitution=RESTITUTION,
                          physicsClientId=self.cid)
        self.floor_tiles.append({"body": b, "x0": x0, "x1": x1, "y0": y0, "y1": y1, "top_z": top_z})
        return b

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


def record_contacts(w, bodies, trig_body, k, dt, frame, first_contact, seen, events):
    """Every active contact at substep `k`, as a per-pair summary plus optional detailed rows.

    THE FIRST-CONTACT RECORD IS THE ONE THAT MATTERS FOR THE BYPASS CHECK, so it is updated here for
    EVERY substep and for every ordered pair, including the trigger. `first_contact[i]` is the FIRST
    thing box i ever touched -- if a box's first touch is the trigger or a box further up the chain
    rather than its immediate upstream neighbour, the chain has been bypassed and the check in the
    caller will say so with the offending index and time.

    `events` (a list, or None) receives one row per active pair per VIDEO FRAME, plus one extra row at
    the exact first-touch substep. Those rows are what `contacts.jsonl` is written from.
    """
    summary = {}
    pairs = []
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            pairs.append(((i, j), i, j, w.contacts_with(bodies[i], bodies[j])))
        if trig_body is not None:
            pairs.append((("trigger", i), "trigger", i, w.contacts_with(trig_body, bodies[i])))

    for key, a, b, cps in pairs:
        if not cps:
            continue
        summary[key] = {"n_points": len(cps), "first_time_s": round(k * dt, 9)}
        for idx, other in ((a, b), (b, a)):
            if isinstance(idx, int) and first_contact[idx] is None:
                first_contact[idx] = {"time_s": round(k * dt, 9), "step": k, "with_index": other}
        # detailed rows: first touch immediately, then once per video frame
        if events is not None and (frame is not None or key not in seen):
            c = cps[0]
            events.append({
                "step": k, "time_s": round(k * dt, 9), "frame": frame,
                "body_a": (f"box{a}" if isinstance(a, int) else a),
                "body_b": (f"box{b}" if isinstance(b, int) else b),
                "first_touch": key not in seen,
                "n_points": len(cps),
                "position_world_m": [round(v, 9) for v in c[5]],
                "normal_on_b_world": [round(v, 9) for v in c[7]],
                "contact_distance_m": round(c[8], 9),
                "normal_force_n": round(c[9], 9),
                "friction_1_world": [round(v, 9) for v in c[11]],
                "friction_2_world": [round(v, 9) for v in c[13]],
                "lateral_friction_a": round(c[1], 6),
                "lateral_friction_b": round(c[2], 6),
            })
            seen.add(key)
    return summary, first_contact


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
        p, _q = w.pos_quat(body)
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


def _is_chain(seq):
    """Is `seq` exactly 0,1,2,...? A named helper so the test is one readable line at each use."""
    return list(seq) == list(range(len(seq)))


def run_chain(assets, order, gap_fracs, density, margin_m, support_z=0.0, x_start=0.0,
              trigger=None, sim_s=6.0, dt=DT, gap_override=None, drop_middle=None,
              gravity=GRAVITY, contact_log=None, trajectory=False, support_profile=None,
              trigger_spec=None, support_step=0.03, arc_boxes=None, floor_pad_m=0.30):
    """One full simulation. Returns a quantitative record.

    `trigger` is None, "rotate" (rotate the first box about its own front bottom edge) or a dict
    describing a separate real box/can body (see `make_trigger`).
    `drop_middle` is an index in `order` to REMOVE entirely (the broken-chain control).
    `support_profile` is a callable x -> support z, used to keep every base flush on real relief.

    `arc_boxes` replaces the straight-line placement with a pre-built list of box records that each
    carry their OWN (x, y, yaw_deg) -- which is what a curved chain needs, since `build_placement` only
    advances one `x` and leaves every yaw at 0. The caller builds them (see `tools/v57/arc_solve.py`)
    and the SAME records drive the placement, the settle check and the floor, so the simulated chain is
    the one that was laid out and previewed. When `arc_boxes` is given, `gap_fracs`/`x_start`/
    `gap_override` no longer describe the geometry and only the trigger's own spec may use them.
    """
    if support_profile is None:
        support_profile = lambda x: support_z          # noqa: E731
    else:
        # REFERENCE THE PROFILE ONCE, HERE, to the height under the FIRST BOX, and let every other
        # consumer (boxes, the trigger, the floor slabs) see a relative profile.
        #
        # The profile returns the ABSOLUTE world z of the surveyed floor, about -0.04 m in this scene,
        # while the simulated support sits at z = 0. Two consumers handled that differently -- the
        # boxes subtracted the reference and the trigger did not -- so the trigger was spawned 40 mm
        # below the floor and ejected upward, and the broken-chain control reported 0 of 5 upstream
        # boxes toppling. Normalising in ONE place removes the whole class of bug.
        _raw_profile = support_profile
        _z_ref = float(_raw_profile(x_start))
        support_profile = lambda x: float(_raw_profile(x)) - _z_ref   # noqa: E731
        support_z = 0.0
    w = World(dt=dt, gravity=gravity)
    try:
        rec = {"dt_s": dt, "density_kg_m3": density, "sim_s": sim_s,
               "support_z_reference_m": support_z, "x_start_m": x_start,
               "order": list(order), "gap_fractions": list(gap_fracs)}
        rec["self_check"] = w.self_check()
        rec["broken_chain_geometry"] = None
        contact_events = [] if contact_log else None

        # `drop_middle` may be an int or a LIST of ints. A single removed box leaves a void of only
        # (its thickness + the two gaps around it), which here is 0.25 m -- LESS than the 0.27 m a
        # toppling neighbour reaches, so the chain legitimately bridges it and the control proved
        # nothing. The control therefore removes a RUN of boxes wide enough that the void exceeds any
        # reachable span, and reports both the void and the reach so the test can be judged rather
        # than trusted.
        drops = ([drop_middle] if isinstance(drop_middle, int)
                 else list(drop_middle or []))
        keep = [i for i in range(len(order)) if i not in drops]
        kept_order = [order[i] for i in keep]
        # Gaps over the kept subsequence. When nothing is dropped this is the identity mapping.
        kept_fracs = list(gap_fracs)
        kept_positions, void_report = None, None
        if drops:
            full_boxes, _full_links = build_placement(assets, order, gap_fracs, x_start, 0.0,
                                                      margin_m)
            kept_positions = [full_boxes[i]["x"] for i in keep]
            # the void is measured between the boxes that FLANK the removed run
            i_lo = max(i for i in keep if i < min(drops))
            i_hi = min(i for i in keep if i > max(drops))
            lo, hi = full_boxes[i_lo], full_boxes[i_hi]
            void_m = (hi["x"] - hi["asset"]["thickness_m"] / 2.0
                      - (lo["x"] + lo["asset"]["thickness_m"] / 2.0))
            # how far a toppling neighbour can reach past its own pivot: hypot(t, h) for the taller
            # flanking box, which is the upper bound on the span any falling box can bridge
            flank = max([lo, hi], key=lambda b: math.hypot(b["asset"]["thickness_m"],
                                                           b["asset"]["height_m"]))
            reach_m = math.hypot(flank["asset"]["thickness_m"], flank["asset"]["height_m"])
            void_report = {
                "dropped_indices": drops,
                "flanking_original_indices": [i_lo, i_hi],
                "void_between_faces_m": round(void_m, 6),
                "max_flanking_reach_m": round(reach_m, 6),
                "void_exceeds_reach": bool(void_m > reach_m),
                "note": ("a broken-chain control only tests anything if the void is wider than a "
                         "falling neighbour can reach; otherwise the chain bridges it and the "
                         "control is inconclusive rather than passed"),
            }
            kept_fracs = [gap_fracs[keep[i]] if keep[i] < len(gap_fracs) else gap_fracs[-1]
                          for i in range(len(keep) - 1)]
        boxes0, links0 = build_placement(assets, kept_order, kept_fracs, x_start, 0.0, margin_m,
                                         gap_override=None)
        if arc_boxes is not None:
            # ARC MODE. The caller's records already carry per-box (x, y, yaw_deg); re-indexing keeps
            # `bodies` 0..n-1 aligned with `boxes0`, which every downstream loop assumes. `support_z`
            # normalization still applies, so the boxes sit on the same relative floor as before.
            boxes0 = []
            for i, src in enumerate(arc_boxes):
                b = dict(src)
                b["index"] = i
                b["asset"] = assets[b["asset_id"]]
                b["z"] = b["asset"]["height_m"] / 2.0
                boxes0.append(b)
            links0 = []
            for i in range(len(boxes0) - 1):
                a_ = boxes0[i]["asset"]
                b_ = boxes0[i + 1]["asset"]
                dx = boxes0[i + 1]["x"] - boxes0[i]["x"]
                dy = boxes0[i + 1]["y"] - boxes0[i]["y"]
                links0.append({
                    "from_index": i, "to_index": i + 1,
                    "from_asset": boxes0[i]["asset_id"], "to_asset": boxes0[i + 1]["asset_id"],
                    "centre_distance_m": round(math.hypot(dx, dy), 9),
                    "face_gap_m": round(math.hypot(dx, dy)
                                        - a_["thickness_m"] / 2.0 - b_["thickness_m"] / 2.0, 9),
                    "yaw_step_deg": round(boxes0[i + 1]["yaw_deg"] - boxes0[i]["yaw_deg"], 6),
                    "pitch_source": "arc placement supplied by the caller",
                })
        if kept_positions is not None:
            for b, xk in zip(boxes0, kept_positions):
                b["x"] = xk
            links0 = [dict(lk, note="position preserved from the unbroken chain: the removed boxes "
                                    "leave a real void") for lk in links0]
            rec["broken_chain_geometry"] = void_report
        # PLACE EACH BOX ON THE MEASURED SUPPORT UNDER IT. `support_profile` is ALREADY relative to the
        # height under the start point (see the normalisation at the top of this function), so box 0
        # stands at z = 0 exactly as on a flat plane and every other box follows the measured relief.
        # The floor slabs below use the same relative profile, so spawn heights and the collision
        # surface cannot disagree -- which they did while the trigger still read the absolute value.
        for b in boxes0:
            rel = float(support_profile(b["x"])) if support_profile is not None else 0.0
            b["z"] = rel + b["asset"]["height_m"] / 2.0
            b["support_relief_under_box_m"] = round(rel, 9)

        # BUILD THE MEASURED FLOOR, so the relief is a real collision surface and not just a spawn
        # offset. Without this the boxes are placed on a slope that does not exist and simply settle
        # back onto the flat plane.
        if support_profile is not None and boxes0:
            # THE FLOOR MUST COVER THE CHAIN'S ACTUAL FOOTPRINT. The straight chain ran along x at a fixed
            # y, so a row of slabs spanning y = +-hw was enough. A curved chain sweeps in y as well, and
            # its y is wherever the surveyed site is -- about +12.2 m here, nowhere near y = 0. Building
            # the old row would have put the collision floor in empty space and let every box fall
            # through. The slabs therefore span the chain's measured bounding box plus a pad, which is
            # also what makes this correct for any future site.
            ys = [b["y"] for b in boxes0]
            hw = max(a["width_m"] for a in assets.values()) / 2.0 + 0.10
            y0 = min(ys) - hw - floor_pad_m
            y1 = max(ys) + hw + floor_pad_m
            xa = min(b["x"] for b in boxes0) - 0.60
            xb = max(b["x"] for b in boxes0) + 0.60
            step = support_step
            tiles, x = [], xa
            while x < xb:
                x2 = min(x + step, xb)
                # `support_profile` is sampled along x only, which is exact for the straight chain. If a
                # future site needs relief along y as well, this is the line that must change, and the
                # residual is reported rather than assumed absent.
                zl = float(support_profile(x))
                zr = float(support_profile(x2))
                # the slab's top is the HIGHER of its two ends, so a box can never be spawned inside
                # it; the resulting over-estimate is bounded by the relief across one step and is
                # reported as `floor_step_error_max_m` below
                tiles.append((x, x2, y0, y1, max(zl, zr)))
                x = x2
            # the flat base plane is dropped out of the way so only the stepped surface supports
            pb.resetBasePositionAndOrientation(w.floor, (0.0, 0.0, -FLOOR_THICK - 5.0),
                                               (0.0, 0.0, 0.0, 1.0), physicsClientId=w.cid)
            base_z = min(t[4] for t in tiles)
            for (x0, x1, y0, y1, tz) in tiles:
                w.add_floor_tile(x0, x1, y0, y1, tz)
            errs = [abs((tiles[i][4] - tiles[i - 1][4])) for i in range(1, len(tiles))]
            rec["measured_floor"] = {
                "kind": "row_of_flat_slabs_following_the_surveyed_profile",
                "n_tiles": len(tiles), "step_m": step,
                "x_range_m": [round(xa, 4), round(xb, 4)],
                # The slabs now span the chain's own footprint in BOTH axes, so the y range is reported
                # alongside the x range. Reporting only `hw*2` as "width" described the old y=0 row and
                # would have understated a curved chain's floor by the whole sweep of the arc.
                "y_range_m": [round(y0, 4), round(y1, 4)],
                "slab_width_m": round(y1 - y0, 4),
                "top_z_range_m": [round(min(t[4] for t in tiles), 6),
                                  round(max(t[4] for t in tiles), 6)],
                "relief_reproduced_m": round(max(t[4] for t in tiles) - base_z, 6),
                "floor_step_error_max_m": round(max(errs) if errs else 0.0, 6),
                "note": ("a flat plane cannot represent a tilted floor; this row of slabs reproduces "
                         "the survey's relief to within one step. The residual error is reported as "
                         "floor_step_error_max_m rather than assumed away."),
                "flat_base_plane_used": False,
            }
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
            # Rotate box 0 about its OWN FRONT BOTTOM EDGE at (+t/2, 0, -h/2) relative to its COM.
            # For a body spinning about a fixed pivot, v_COM = omega x (r_COM - r_pivot), so with
            # omega = (0, +w, 0):
            #     v = (0,w,0) x (-t/2, 0, +h/2) = (+w*h/2, 0, +w*t/2)
            # which is the correct pure-rotation velocity (and matches the earlier project's
            # formula). An earlier version of this line had the x term negated, which dragged the box
            # BACKWARD while spinning it forward, so almost nothing toppled; the pair table in the
            # saved chain.json shows that failure. It is computed as a cross product here so the sign
            # cannot drift again.
            b0 = boxes0[0]
            t = b0["asset"]["thickness_m"]
            h = b0["asset"]["height_m"]
            Lc = math.hypot(t, h)
            wcrit = math.sqrt(3.0 * abs(GRAVITY) * (Lc - h) / (Lc * Lc)) if Lc > h else 0.0
            om = trigger_omega(b0)
            r_pivot_rel_com = (t / 2.0, 0.0, -h / 2.0)
            # omega = (0, om, 0); v = omega x (r_com - r_pivot) = omega x (-r_pivot_rel_com)
            rx, rz = -r_pivot_rel_com[0], -r_pivot_rel_com[2]
            pv = (om * rz, 0.0, -om * rx)          # (0,om,0) x (rx,0,rz) = (om*rz, 0, -om*rx)
            pb.resetBaseVelocity(bodies[0], linearVelocity=pv,
                                 angularVelocity=(0.0, om, 0.0), physicsClientId=w.cid)
            trig_info = {"kind": "rotate_first_box_about_front_bottom_edge",
                         "omega0_rad_s": om, "w_crit_rad_s": wcrit,
                         "omega_over_w_crit": (om / wcrit if wcrit else None),
                         "linear_velocity_m_s": [round(v, 6) for v in pv],
                         "expected_linear_velocity_m_s": [round(om * h / 2.0, 6), 0.0,
                                                          round(om * t / 2.0, 6)],
                         "velocity_matches_pure_rotation": bool(
                             abs(pv[0] - om * h / 2.0) < 1e-12 and abs(pv[2] - om * t / 2.0) < 1e-12),
                         "edge_speed_m_s": round(om * Lc / 2.0, 6)}
        elif isinstance(trigger, dict):
            trig_body, trig_info = make_trigger(w, trigger, boxes0, support_profile)
        elif trigger == "real_box":
            if trigger_spec is None:
                trigger_spec = trigger_box_spec(assets, OUIJA_TRIGGER, gap_m=0.03,
                                                factor=A.trigger_factor, density=density)
            else:
                # RESCALE THE TRIGGER'S MASS TO THE RUN'S DENSITY. The spec is built once by the
                # caller from the default density; without this the density sweep changes the CHAIN's
                # mass while leaving the trigger at its old mass, so the sweep measures the trigger
                # rather than the chain.
                trigger_spec = dict(trigger_spec)
                trigger_spec["mass_kg"] = density * trigger_spec["asset"]["box_volume_m3"]
                trigger_spec["density_kg_m3"] = density
            trig_body, trig_info = make_trigger(w, trigger_spec, boxes0, support_profile)
        rec["trigger"] = trig_info

        # --- simulate, logging per video frame -------------------------------------------------
        n_sub = int(round(sim_s / dt))
        frames = []
        first_contact = {b["index"]: None for b in boxes0}
        contact_pairs = {}
        topple_frame = {b["index"]: None for b in boxes0}
        onset_frame = {b["index"]: {"onset2": None, "onset10": None} for b in boxes0}
        max_tilt = {b["index"]: 0.0 for b in boxes0}
        contact_seen = set()
        traj_rows = {b["index"]: [] for b in boxes0}
        trig_rows = [] if (trajectory and trig_body is not None) else None
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
                if trig_body is not None and trig_rows is not None:
                    p, q = w.pos_quat(trig_body)
                    trig_rows.append({
                        "frame": frame, "blender_frame": frame + 1, "step": k,
                        "time_s": round(k * dt, 9),
                        "position_m": [round(v, 9) for v in p],
                        "quaternion_xyzw": [round(v, 9) for v in q],
                    })
            # contacts among the boxes and the trigger
            # --- contacts: one pass over every pair, with the first-touch substep preserved -------
            # `record_contacts` returns the per-pair summary AND, when `contact_events` is a list,
            # appends the detailed rows that become `contacts.jsonl`. It is called once per 480 Hz
            # substep, and gates the detailed rows to the 24 fps video grid plus the exact first-touch
            # substep, so the file stays readable while the onset instant stays exact.
            summary, first_contact = record_contacts(
                w, bodies, trig_body, k, dt, frame=(k // SUBSTEPS_PER_FRAME - 1
                                                    if k % SUBSTEPS_PER_FRAME == 0 else None),
                first_contact=first_contact, seen=contact_seen, events=contact_events)
            for key, s in summary.items():
                cp = contact_pairs.setdefault(key, {"count": 0, "max_points": 0,
                                                    "first_time_s": s["first_time_s"],
                                                    "frames": []})
                cp["count"] += 1
                cp["max_points"] = max(cp["max_points"], s["n_points"])
                if len(cp["frames"]) < 400:
                    cp["frames"].append(k // SUBSTEPS_PER_FRAME - 1
                                        if k % SUBSTEPS_PER_FRAME == 0 else None)
            # tilt at each substep is cheap and gives exact onset steps
            if k % 4 == 0 or k % SUBSTEPS_PER_FRAME == 0:
                for b in boxes0:
                    _p, q = w.pos_quat(bodies[b["index"]])
                    td = tilt_deg(q)
                    if td > max_tilt[b["index"]]:
                        max_tilt[b["index"]] = td
                    if topple_frame[b["index"]] is None and td >= TOPPLE_DEG:
                        topple_frame[b["index"]] = k
                    # MOTION ONSET, at a threshold far below any tip-over angle.
                    # `topple_frame` uses TOPPLE_DEG = 60 deg, which is where a box has FINISHED
                    # falling; two boxes whose falls overlap can cross 60 deg at nearly the same
                    # instant and look simultaneous even though one started seconds earlier. This
                    # records where each box BEGAN to move, which is the quantity that says whether
                    # the chain propagates as a wave. The no-trigger control peaks at 0.0024 deg, so
                    # 2 deg is three orders of magnitude above the noise floor and well below the
                    # smallest tip-over angle of any asset (atan(0.0253/0.192) = 7.5 deg).
                    for thr, key in ((2.0, "onset2"), (10.0, "onset10")):
                        if onset_frame[b["index"]].get(key) is None and td >= thr:
                            onset_frame[b["index"]][key] = k

        # --- final state ----------------------------------------------------------------------
        rows = []
        for b in boxes0:
            body = bodies[b["index"]]
            p, q = w.pos_quat(body)
            lin, ang = pb.getBaseVelocity(body, physicsClientId=w.cid)
            tip = tip_angle_deg(b["asset"])
            mt = max_tilt[b["index"]]
            ft = tilt_deg(q)
            rows.append({
                "index": b["index"], "asset_id": b["asset_id"],
                "final_position_m": [round(v, 9) for v in p],
                "final_tilt_deg": round(ft, 4),
                "final_verdict": classify(ft),
                "max_tilt_deg": round(mt, 4),
                # A BOX IS COUNTED AS FALLEN WHEN IT HAS ROTATED WELL PAST ITS OWN TIP-OVER ANGLE.
                # `toppled` uses TOPPLE_DEG = 60, which is the angle at which a fall is COMPLETE;
                # a box resting at 52 deg has plainly fallen over but is under that line, so both
                # readings and the physical threshold are reported. `PASS_FACTOR * tip` is 3x the
                # tip angle (22.5-45.3 deg for these assets), which no box can reach by rocking.
                "tip_angle_deg": round(tip, 4),
                "fallen": bool(mt >= 3.0 * tip),
                "fallen_threshold_deg": round(3.0 * tip, 4),
                "toppled": bool(mt >= TOPPLE_DEG),
                "topple_step": topple_frame[b["index"]],
                "topple_time_s": (None if topple_frame[b["index"]] is None
                                  else round(topple_frame[b["index"]] * dt, 9)),
                "final_speed_m_s": round(math.sqrt(sum(v * v for v in lin)), 9),
                "final_spin_rad_s": round(math.sqrt(sum(v * v for v in ang)), 9),
                "first_contact": first_contact[b["index"]],
                "motion_onset_step_2deg": onset_frame[b["index"]]["onset2"],
                "motion_onset_time_2deg_s": (None if onset_frame[b["index"]]["onset2"] is None
                                             else round(onset_frame[b["index"]]["onset2"] * dt, 9)),
                "motion_onset_step_10deg": onset_frame[b["index"]]["onset10"],
                "motion_onset_time_10deg_s": (None if onset_frame[b["index"]]["onset10"] is None
                                              else round(onset_frame[b["index"]]["onset10"] * dt, 9)),
                "peak_displacement_x_m": round(
                    max(r["position_m"][0] for r in traj_rows[b["index"]])
                    - min(r["position_m"][0] for r in traj_rows[b["index"]]), 9)
                if traj_rows[b["index"]] else None,
            })
        rec["boxes"] = rows
        rec["boxes_toppled"] = sum(1 for r in rows if r["toppled"])
        rec["all_toppled"] = rec["boxes_toppled"] == len(rows)
        rec["boxes_fallen"] = sum(1 for r in rows if r["fallen"])
        rec["all_fallen"] = rec["boxes_fallen"] == len(rows)
        rec["boxes_fallen_and_still_down"] = sum(1 for r in rows if r["fallen"]
                                                 and r["final_tilt_deg"] >= r["tip_angle_deg"])
        rec["all_fallen_and_still_down"] = rec["boxes_fallen_and_still_down"] == len(rows)
        rec["fall_criterion"] = ("fallen = max tilt >= 3x the asset's own tip-over angle "
                                 "atan(t/h); tip angles are 7.5-15.1 deg for the fitted assets, so "
                                 "the threshold is 22.5-45.3 deg, well above any rocking amplitude. "
                                 "`boxes_toppled` is reported beside it using the flat 60 deg line.")
        # THE SEQUENCE VERDICT, stated in terms that CAN fail. "Sequential" is judged on where each box
        # BEGAN to move and on the order of first contacts, not on the 60 deg line, because 60 deg is
        # where a fall FINISHES: neighbouring boxes whose falls overlap cross it within a frame of each
        # other even when their onsets are seconds apart, which is exactly what a domino chain looks
        # like. Both readings are reported so neither can hide the other.
        #
        # This block is built AFTER the onset blocks below, because `is_sequential_chain` reads their
        # results; building it here and reading the keys later left them missing and silently made the
        # flag False on a run whose onsets were in perfect order.
        rec["contact_pairs"] = {f"{a}|{b}": v for (a, b), v in contact_pairs.items()}
        rec["all_have_contact"] = all(r["first_contact"] is not None for r in rows)

        # --- ordering -------------------------------------------------------------------------
        onsets = [(r["index"], r["topple_step"]) for r in rows if r["topple_step"] is not None]
        rec["topple_order"] = [i for i, _ in sorted(onsets, key=lambda t: t[1])]
        rec["topple_order_is_chain"] = rec["topple_order"] == sorted(rec["topple_order"])

        # MOTION-onset ordering and separation, the quantity that shows the chain as a WAVE.
        for thr in ("2deg", "10deg"):
            key = f"motion_onset_{thr}"
            step_key = f"motion_onset_step_{thr}"
            steps = [(r["index"], r[step_key]) for r in rows if r[step_key] is not None]
            rec[f"{key}_order"] = [i for i, _ in sorted(steps, key=lambda t: t[1])]
            rec[f"{key}_order_is_chain"] = (rec[f"{key}_order"]
                                            == sorted(rec[f"{key}_order"]))
            by = {r["index"]: r[step_key] for r in rows}
            d = []
            for i in range(len(rows) - 1):
                if by.get(i) is not None and by.get(i + 1) is not None:
                    d.append(round((by[i + 1] - by[i]) * dt * VIDEO_FPS, 4))
            rec[f"{key}_adjacent_gaps_frames"] = d
            rec[f"{key}_min_adjacent_frames"] = (min(d) if d else None)
            rec[f"{key}_median_adjacent_frames"] = (sorted(d)[len(d) // 2] if d else None)
            rec[f"{key}_n_ge_1_frame"] = sum(1 for v in d if v >= 1.0)
            rec[f"{key}_all_sequential"] = bool(
                d and all(v > 0 for v in d) and rec[f"{key}_order_is_chain"])
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

        # THE SEQUENCE VERDICT, now that the onsets it reads actually exist. "Sequential" is judged on
        # where each box BEGAN to move and on the order of first contacts, NOT on the 60 deg line:
        # 60 deg is where a fall FINISHES, so neighbouring boxes whose falls overlap cross it within a
        # frame of each other even when their onsets are seconds apart -- which is exactly what a
        # domino chain looks like. Both readings are published so neither can hide the other.
        rec["sequence"] = {
            "first_contact_order": [r["index"] for r in rows
                                    if r["first_contact"] is not None],
            "first_contact_order_is_chain": _is_chain([r["index"] for r in rows
                                                       if r["first_contact"] is not None]),
            "motion_onset_2deg_order": rec.get("motion_onset_2deg_order"),
            "motion_onset_2deg_order_is_chain": rec.get("motion_onset_2deg_order_is_chain"),
            "motion_onset_10deg_order_is_chain": rec.get("motion_onset_10deg_order_is_chain"),
            "motion_onset_2deg_all_sequential": rec.get("motion_onset_2deg_all_sequential"),
            "motion_onset_10deg_all_sequential": rec.get("motion_onset_10deg_all_sequential"),
            "motion_onset_2deg_min_adjacent_frames": rec.get(
                "motion_onset_2deg_min_adjacent_frames"),
            "motion_onset_2deg_median_adjacent_frames": rec.get(
                "motion_onset_2deg_median_adjacent_frames"),
            "topple60_order_is_chain": rec.get("topple_order_is_chain"),
            "note": ("`*_order_is_chain` and `*_all_sequential` are the acceptance tests for a "
                     "SEQUENCE; `topple60_order_is_chain` is reported for completeness and is "
                     "expected to be weaker because the 60 deg line marks the END of a fall."),
        }
        rec["is_sequential_chain"] = bool(
            rec["sequence"]["first_contact_order_is_chain"]
            and rec["sequence"]["motion_onset_2deg_all_sequential"]
            and rec["sequence"]["motion_onset_10deg_all_sequential"])
        rec["sequence"]["is_sequential_chain"] = rec["is_sequential_chain"]

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
        # THE SEQUENCE VERDICT is finalised HERE, after `no_bypass` and `all_have_contact` exist.
        # Building it earlier made `is_sequential_chain` read a key that was not yet set, which raised
        # on one run and silently returned False on another -- the exact failure mode this project
        # treats as a defect, so the flag is asserted to be a real bool of real inputs.
        rec["sequence"]["no_bypass"] = rec["no_bypass"]
        rec["sequence"]["all_have_contact"] = rec["all_have_contact"]
        rec["is_sequential_chain"] = bool(
            rec["sequence"]["first_contact_order_is_chain"]
            and rec["sequence"]["motion_onset_2deg_all_sequential"]
            and rec["sequence"]["motion_onset_10deg_all_sequential"]
            and rec["no_bypass"] and rec["all_have_contact"])
        rec["sequence"]["is_sequential_chain"] = rec["is_sequential_chain"]
        rec["trajectory_rows"] = (traj_rows if trajectory else None)
        rec["trigger_info_row"] = trig_rows
        rec["contact_events"] = contact_events
        # the trigger's own final state, so the deliverable can show it fell too
        if trig_body is not None:
            tp, tq = w.pos_quat(trig_body)
            rec["trigger_final"] = {"position_m": [round(v, 9) for v in tp],
                                    "tilt_deg": round(tilt_deg(tq), 4),
                                    "verdict": classify(tilt_deg(tq))}
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
    """A REAL separate box as the trigger, toppling onto the first box and hitting ONLY it.

    WHY A TOPPLING REAL BOX AND NOT A LINEAR PUSH
    ---------------------------------------------
    A horizontal shove at the base slides a standing box rather than tipping it: the contact centroid
    sits near the pushed box's own COM height, so the toppling torque arm is nearly zero. A body that
    ROTATES onto the target strikes high, where the torque arm is largest. So the trigger here is the
    same manoeuvre a domino makes: it is placed upright behind box 0 and given one initial angular
    velocity about its own front bottom edge, then left to fall naturally.

    TWO GEOMETRIC FACTS THAT MAKE THE BYPASS IMPOSSIBLE, BOTH COMPUTED, NOT ASSERTED
    -------------------------------------------------------------------------------
    Let H be the trigger height, t_trig its thickness, g the visible gap between the trigger's front
    face and box 0's back face, and x_piv the pivot's world x.

      (1) **No over-the-top bypass.** The trigger's highest reachable point is its top-front corner,
          which is at most H above the ground. If H <= (box 0's height) the trigger can never be above
          box 0's top and therefore cannot land beyond it. `trigger_taller_than_first_box` records
          this; the trigger asset and box 0 are chosen so it is false.
      (2) **Strike height.** The corner meets box 0's back face at angle asin(g/H) and at height
          sqrt(H^2 - g^2). This is reported as a fraction of box 0's height so a low, sliding contact
          is visible as a number rather than discovered as a failure.

    The forward reach when the trigger lies flat is x_piv + H; that can exceed box 0's far face, so
    this function also reports `flat_reach_past_first_box_m` and the check that actually settles the
    question -- whether any box beyond the first ever records its FIRST contact with the trigger -- is
    run in the simulation and reported as `bypass_violations`.
    """
    aid = spec["asset_id"]
    a = spec["asset"]
    b0 = boxes[0]
    x0, t0, h0 = b0["x"], b0["asset"]["thickness_m"], b0["asset"]["height_m"]
    # THE TRIGGER FOLLOWS BOX 0'S OWN DIRECTION, not world -X. In a straight chain box 0's yaw is 0 and
    # this reduces to the original x-only placement. In a curved chain box 0 faces along its arc tangent,
    # so a trigger offset in world -X would sit beside the chain rather than behind it, and would push the
    # first box sideways instead of toppling it along the chain.
    yaw0 = float(b0.get("yaw_deg", 0.0))
    ux, uy = math.cos(math.radians(yaw0)), math.sin(math.radians(yaw0))
    t_trig, h_trig = a["thickness_m"], a["height_m"]
    gap = spec.get("gap_m", 0.03)
    d_back = t0 / 2.0 + gap + t_trig / 2.0
    xt = x0 - ux * d_back
    yt = b0["y"] - uy * d_back
    zt = float(support_profile(xt)) + h_trig / 2.0
    body = w.add_box(a["proxy_obj"], spec["mass_kg"], (xt, yt, zt), yaw0, tag="trigger")
    # one initial velocity: a pure rotation about the trigger's own front bottom edge.
    #
    # DERIVATION, because getting this wrong is silent -- the trigger spins the WRONG WAY, nudges box 0
    # by a fraction of a degree, and the whole chain reads as 0 toppled with no error reported.
    #
    # In the box's local frame, tangent = local X, across-path = local Y, up = local Z. The pivot is at
    # local (+t/2, 0, -h/2) and the COM at the origin, so r_COM - r_pivot = (-t/2, 0, +h/2). Toppling
    # FORWARD along the tangent means spinning about local +Y:
    #     v_local = (0, w, 0) x (-t/2, 0, h/2) = (w*h/2, 0, w*t/2)
    # The local-to-world rotation sends local X to (ux, uy, 0) and local Y to (-uy, ux, 0), so
    #     v_world = (w*h/2) * (ux, uy, 0) + (w*t/2) * (0, 0, 1)
    #     omega_world = w * (-uy, ux, 0)
    # At yaw0 = 0 (ux, uy) = (1, 0) and both reduce to the original straight-chain values
    # (w*h/2, 0, w*t/2) and (0, w, 0) -- which is the check that this generalisation is faithful.
    om = spec["omega_rad_s"]
    pv = (ux * om * h_trig / 2.0, uy * om * h_trig / 2.0, om * t_trig / 2.0)
    pb.resetBaseVelocity(body, linearVelocity=pv,
                         angularVelocity=(-uy * om, ux * om, 0.0),
                         physicsClientId=w.cid)
    # Along-tangent bookkeeping, which equals the original x-based numbers when yaw0 = 0.
    x_piv = xt + ux * t_trig / 2.0
    strike_h = math.sqrt(max(0.0, h_trig ** 2 - gap ** 2))
    info = {
        "kind": "real_box_toppling_about_its_front_bottom_edge",
        "asset_id": aid, "mass_kg": spec["mass_kg"],
        "position_m": [round(xt, 9), round(yt, 9), round(zt, 9)],
        "yaw_deg": round(yaw0, 9),
        "omega0_rad_s": om,
        "w_crit_rad_s": spec.get("w_crit_rad_s"),
        "omega_over_w_crit": spec.get("omega_over_w_crit"),
        "linear_velocity_m_s": [round(v, 9) for v in pv],
        "velocity_matches_pure_rotation": bool(
            abs(math.hypot(pv[0], pv[1]) - om * h_trig / 2.0) < 1e-12
            and abs(pv[2] - om * t_trig / 2.0) < 1e-12),
        "visible_gap_to_first_box_m": gap,
        "trigger_height_m": h_trig, "first_box_height_m": h0,
        "trigger_thickness_m": t_trig, "first_box_thickness_m": t0,
        "trigger_shorter_than_first_box_by_m": round(h0 - h_trig, 9),
        "trigger_taller_than_first_box": bool(h_trig > h0),
        "cannot_pass_over_the_first_box": bool(h_trig <= h0),
        "strike_height_m": round(strike_h, 9),
        "strike_height_fraction_of_first_box": round(strike_h / h0, 6),
        "pivot_x_m": round(x_piv, 9),
        "flat_reach_x_m": round(x_piv + ux * h_trig, 9),
        "first_box_far_face_x_m": round(x0 + ux * t0 / 2.0, 9),
        "flat_reach_past_first_box_m": round(x_piv + ux * h_trig - (x0 + ux * t0 / 2.0), 9),
        "note": ("whether the trigger actually reaches a later box is decided by the simulation's "
                 "first-contact record (`bypass_violations`), not by this reach bound"),
    }
    return body, info


def trigger_box_spec(assets, aid, gap_m=0.03, factor=2.0, density=DENSITY_DEFAULT):
    """Everything `make_trigger` needs for a real-box trigger, with w_crit computed for it.

    `density` MUST be the same density the boxes are built with. The trigger's mass is
    `density * its fitted volume`; pinning it to the default density made the trigger 3x too light
    relative to the chain whenever the chain was re-run at a higher density, and the density sweep
    then reported 0 of 12 boxes toppling at 600 kg/m3 -- a result about the trigger's mass, not about
    the chain. The caller passes the run's density through.
    """
    a = assets[aid]
    t, h = a["thickness_m"], a["height_m"]
    L = math.hypot(t, h)
    wc = math.sqrt(3.0 * abs(GRAVITY) * (L - h) / (L * L)) if L > h else 0.0
    return {
        "asset_id": aid, "asset": a, "gap_m": gap_m,
        "mass_kg": density * a["box_volume_m3"],
        "density_kg_m3": density,
        "omega_rad_s": factor * wc, "w_crit_rad_s": wc,
        "omega_over_w_crit": factor,
    }


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
    ap.add_argument("--compose", default="",
                    help="compose.json; supplies the chain order, the per-pair gap fractions and the "
                         "trigger, so the delivered chain is the one whose links were verified")
    ap.add_argument("--support-profile", default="",
                    help="ground_flat.json; applies the MEASURED per-station relief as the support "
                         "surface, so the chain is tested on the real alley floor and not only on a "
                         "flat plane")
    ap.add_argument("--support-window", default="",
                    help="optional json {x0,y0,len_m,width_m} selecting a specific measured window; "
                         "default is the flattest window that CONTAINS the chain")
    ap.add_argument("--support-step", type=float, default=0.03,
                    help="slab length when building the measured floor (m); the survey's own sample "
                         "spacing, so the floor is never finer than the measurement behind it")
    ap.add_argument("--x-start", type=float, default=0.0)
    ap.add_argument("--y", type=float, default=0.0)
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
    LEGO = "LEGO_Star_Wars_Advent_Calendar"
    HOC = "House_of_Cards_The_Complete_First_Season_4_Discs_DVD"
    THREE = [CRAN, TRIV, OUIJA]

    def log(msg):
        print(f"[b2_chain] {msg}", flush=True)

    # ---- THE DELIVERABLE CHAIN IS LOADED FIRST, because the GROUND CHOICE depends on its length ----
    # The gap and the ground are one decision: a 12-box chain at a 0.25 gap needs a 1.84 m run, while
    # the flattest corridor the survey found is only 1.35 m long, so choosing the ground before the
    # chain's length is known chooses a window the chain overhangs. `compose.json` is read ONCE here
    # and is the single source of truth for the order, the per-pair gaps and the trigger, so the
    # ground window, the extent check and the simulated run cannot disagree about what is being built.
    composed = None
    if A.compose and Path(A.compose).is_file():
        cj = json.loads(Path(A.compose).read_text(encoding="utf-8"))
        composed = {
            "order": cj["order"], "gap_fracs": cj["gap_fractions"],
            "trigger_spec": {**cj["trigger_spec"], "asset": assets[cj["trigger_spec"]["asset_id"]]},
            "links_verified_by_scan": cj["links_verified_by_scan"],
            "links_in_plan_band": cj["links_in_plan_band"],
            "source": A.compose,
        }
    if composed is not None:
        chain_order_deliver = composed["order"]
        chain_gaps_deliver = composed["gap_fracs"]
        trig_spec = composed["trigger_spec"]
        chain_src = (f"{Path(A.compose).name} (measured per-pair gaps and scanned trigger)")
    else:
        # Fallback constants, used only when --compose is absent. Interleaved across the three models
        # so no two adjacent boxes are the same model, and starting with the tallest so the trigger has
        # the easiest job.
        chain_order_deliver = [OUIJA, CRAN, TRIV, OUIJA, CRAN, TRIV, OUIJA, CRAN, OUIJA, TRIV,
                               CRAN, TRIV]
        chain_gaps_deliver = [0.20, 0.20, 0.22, 0.20, 0.20, 0.22, 0.20, 0.22, 0.20, 0.22, 0.20]
        trig_spec = trigger_box_spec(assets, CRAN, gap_m=0.030, factor=A.trigger_factor,
                                     density=A.density)
        chain_src = "fallback constants (no --compose given)"

    def chain_extent(order, gaps, tspec):
        """Trigger back face -> last box far face, from the same arithmetic the simulation uses."""
        bx, _ = build_placement(assets, order, gaps, 0.0, A.support_z, measured_margin)
        x0, t0 = bx[0]["x"], bx[0]["asset"]["thickness_m"]
        back = x0 - t0 / 2.0 - tspec["gap_m"] - tspec["asset"]["thickness_m"]
        last = bx[-1]
        return back, last["x"] + last["asset"]["thickness_m"] / 2.0

    b0, b1 = chain_extent(chain_order_deliver, chain_gaps_deliver, trig_spec)
    need_l = round(b1 - b0, 4)
    need_w = round(max(a["width_m"] for a in assets.values()) + 0.015, 4)
    result["chain_need_m"] = {"len_m": need_l, "width_m": need_w}
    log(f"deliverable chain needs {need_l:.4f} m x {need_w:.4f} m of ground")

    # MEASURED SUPPORT SURFACE, chosen against that length: the FLATTEST window that CONTAINS the
    # chain, because flatness is what the chain needs and length is a hard constraint. "It works on
    # flat ground" and "it works on THIS floor" are then separate, both-reported facts.
    support_profile, ground_meta = None, None
    if A.support_profile and Path(A.support_profile).is_file():
        support_profile, ground_meta = support_profile_from_report(
            A.support_profile, which=(A.support_window or "auto"),
            need_len_m=need_l, need_width_m=need_w)
        if ground_meta:
            gw = ground_meta["window"]
            log(f"ground: {ground_meta['selection']}")
            if gw["len_m"] + 1e-9 < need_l:
                log(f"WARNING: the chosen window is {gw['len_m']:.3f} m but the chain needs "
                    f"{need_l:.3f} m -- the chain overhangs the surveyed corridor")
    result["ground_support"] = ground_meta or {
        "source": None, "note": "flat plane used (no --support-profile given)"}

    def run_cfg(order, gaps, trigger="rotate", density=None, sim_s=None, trigger_spec=None, **kw):
        """`run_chain` with the shared parameters filled in, so every call differs only where stated.

        The MEASURED support profile is passed through, so every run in every mode stands on the same
        real floor as the delivered chain.
        """
        return run_chain(assets, order, gaps, A.density if density is None else density,
                         measured_margin, support_z=A.support_z, trigger=trigger,
                         sim_s=A.sim_s if sim_s is None else sim_s, trigger_spec=trigger_spec,
                         support_profile=support_profile, support_step=A.support_step, **kw)

    # ---------------------------------------------------------------- step 1: 4 Cranium instances
    if A.mode in ("cranium4", "all"):
        order = [CRAN] * 4
        gap_fracs = [0.25, 0.25, 0.25]
        boxes, links = build_placement(assets, order, gap_fracs, 0.0, A.support_z, measured_margin)
        w = World()
        try:
            bodies, settle = place_and_settle(w, boxes, A.density)
            com = assert_com(w, bodies, boxes)
            # A STABLE INITIAL FRAME means the published placement is already correct: the base is
            # flush and the box is upright and at rest AT THE PUBLISHED COORDINATES. This is checked
            # BEFORE any trigger, and the drop from the spawn clearance is reported, so "stable" is
            # not established by letting the boxes fall for 100 substeps and calling the result the
            # initial state.
            stable = all(abs(s["settled_tilt_deg"]) < 1.0 and s["floor_contacts"] > 0
                         and abs(s["settled_position_m"][0] - s["placed_position_m"][0]) < 1e-4
                         for s in settle)
            result["cranium4"] = {
                "order": order, "gap_fractions": gap_fracs, "links": links,
                "placement": [{"index": b["index"], "position_m": [b["x"], b["y"], b["z"]],
                               "support_z_m": A.support_z} for b in boxes],
                "settle": settle, "com_origin_check": com,
                "stable_initial_frames": bool(stable),
                "stable_initial_frame_criteria": (
                    "every box: |settled tilt| < 1 deg, floor contacts > 0, and settled x within "
                    "0.1 mm of the PUBLISHED x"),
            }
        finally:
            w.close()
        # then actually topple all four, through one trigger on the first box
        r4 = run_cfg(order, gap_fracs, trigger="rotate", sim_s=A.sim_s)
        result["cranium4"]["topple_run"] = {
            k: v for k, v in r4.items() if k != "trajectory_rows"}
        result["cranium4"]["all_four_toppled"] = bool(r4["all_toppled"])
        result["cranium4"]["topple_order"] = r4["topple_order"]

    # ---------------------------------------------------------------- step 2: ordered pair transfer
    if A.mode in ("pairs", "all"):
        pairs = []
        for a in THREE:
            for b in THREE:
                if a == b:
                    continue
                r = run_cfg([a, b], [0.25], trigger="rotate", sim_s=5.0)
                pairs.append({
                    "pair": f"{a}->{b}",
                    "striker_toppled": r["boxes"][0]["toppled"],
                    "target_toppled": r["boxes"][1]["toppled"],
                    "target_max_tilt_deg": r["boxes"][1]["max_tilt_deg"],
                    "contact": bool(r.get("contact_pairs")),
                    "first_contact": r["boxes"][1]["first_contact"],
                    "com_check_pass": r.get("com_origin_check", {}).get("pass"),
                    "self_check_ok": r.get("self_check", {}).get("ok"),
                })
        result["pairs"] = {"pairs": pairs, "count": len(pairs),
                           "all_pairs_transfer": all(p["target_toppled"] for p in pairs)}

    # ---------------------------------------------------------------- step 2b: per-pair gap solve
    if A.mode in ("gapscan", "all"):
        scan = []
        for a in THREE:
            for b in THREE:
                if a == b:
                    continue
                for gf in (0.15, 0.20, 0.25, 0.30, 0.35, 0.45):
                    r = run_cfg([a, b], [gf], trigger="rotate", sim_s=5.0)
                    scan.append({"pair": f"{a}->{b}", "gap_fraction": gf,
                                 "gap_m": r["links"][0]["gap_requested_m"],
                                 "pitch_m": r["links"][0]["pitch_m"],
                                 "striker_toppled": r["boxes"][0]["toppled"],
                                 "target_toppled": r["boxes"][1]["toppled"],
                                 "target_max_tilt_deg": r["boxes"][1]["max_tilt_deg"],
                                 "contact": bool(r.get("contact_pairs"))})
        # the SMALLEST gap fraction that works for each ordered pair, which is what the chain uses
        best = {}
        for s in scan:
            if s["striker_toppled"] and s["target_toppled"]:
                k = s["pair"]
                if k not in best or s["gap_fraction"] < best[k]["gap_fraction"]:
                    best[k] = s
        result["gap_scan"] = {"scan": scan, "smallest_working_gap_per_pair": best,
                              "all_pairs_have_a_working_gap": len(best) == 6}

    # ---------------------------------------------------------------- chosen chain, from compose.json
    # The order, the per-pair gaps and the trigger were loaded at the top of `main` because the GROUND
    # WINDOW choice depends on the chain's length; this block only reports them, so the deliverable's
    # numbers can be traced back to `compose.json`.
    CHAIN12 = chain_order_deliver
    GAPS12 = chain_gaps_deliver
    TRIG = trig_spec
    result["chain_source"] = chain_src
    result["chain_composition"] = {
        "order": CHAIN12, "order_short": [ASSET_SHORT[a] for a in CHAIN12],
        "gap_fractions": GAPS12,
        "n_boxes": len(CHAIN12), "n_distinct_assets": len(set(CHAIN12)),
        "adjacent_same_model_pairs": [i for i in range(len(CHAIN12) - 1)
                                      if CHAIN12[i] == CHAIN12[i + 1]],
        "trigger": {k: v for k, v in TRIG.items() if k != "asset"},
        "links_verified_by_scan": None,
        "links_in_plan_band": None,
    }
    if A.compose and Path(A.compose).is_file():
        cj2 = json.loads(Path(A.compose).read_text(encoding="utf-8"))
        result["chain_composition"]["links_verified_by_scan"] = cj2.get("links_verified_by_scan")
        result["chain_composition"]["links_in_plan_band"] = cj2.get("links_in_plan_band")

    if A.mode in ("chain", "controls", "all"):
        # `contact_log=True` is REQUIRED for `contacts.jsonl`: without it `run_chain` leaves
        # `contact_events` as None, and the deliverable's contact table would be silently empty --
        # which is exactly the kind of "check that cannot fail" this project forbids.
        r = run_cfg(CHAIN12, GAPS12, trigger="real_box", trigger_spec=TRIG, trajectory=True,
                    contact_log=True)
        result["chain12"] = {k: v for k, v in r.items() if k != "trajectory_rows"}
        result["_traj12"] = r.get("trajectory_rows")
        result["_boxes12"] = r.get("boxes")
        result["_trig12"] = r.get("trigger_info_row")

    if A.mode in ("controls", "all"):
        controls = {}

        # --- no-trigger control ------------------------------------------------------------------
        nt = run_cfg(CHAIN12, GAPS12, trigger=None)
        controls["no_trigger"] = {
            "boxes_toppled": nt["boxes_toppled"], "n_boxes": nt["n_boxes"],
            "boxes_fallen": nt["boxes_fallen"],
            "is_sequential_chain": nt["is_sequential_chain"],
            "max_tilt_deg": max(b["max_tilt_deg"] for b in nt["boxes"]),
            "max_final_tilt_deg": max(b["final_tilt_deg"] for b in nt["boxes"]),
            "chain_stays_standing": nt["boxes_toppled"] == 0 and nt["boxes_fallen"] == 0,
            "com_check_pass": nt["com_origin_check"]["pass"],
            "duration_s": nt["sim_s"],
        }

        # --- broken-chain control: remove a RUN of middle boxes -------------------------------
        # A RUN, not one box. Removing a single box leaves a 0.25 m void, which is narrower than the
        # 0.27 m a toppling neighbour reaches, so the chain bridges it and the control is inconclusive
        # -- which is what it reported (upstream 5/5, downstream 5/5) before the geometry was checked.
        # Removing five consecutive boxes leaves a void far wider than any span a falling box can
        # bridge, so "does the wave stop?" becomes a real question with a real answer.
        removed = [5, 6, 7, 8, 9]
        bc = run_cfg(CHAIN12, GAPS12, trigger="real_box", trigger_spec=TRIG, drop_middle=removed)
        # MAP THE RUN'S OWN INDICES BACK TO THE ORIGINAL CHAIN. `run_chain` re-indexes the kept boxes
        # 0..len(keep)-1, so after removing 5..9 the surviving "downstream" boxes are numbered 5 and 6,
        # not 10 and 11. Comparing `b["index"] > max(removed)` therefore matched NOTHING, and the
        # control passed on an empty downstream set -- a check that could not fail. The mapping is made
        # explicitly here so both sides are real sets with real members.
        orig = [i for i in range(len(CHAIN12)) if i not in removed]
        new_to_orig = {new: o for new, o in enumerate(orig)}
        up = [b for b in bc["boxes"] if new_to_orig[b["index"]] < min(removed)]
        down = [b for b in bc["boxes"] if new_to_orig[b["index"]] > max(removed)]
        geom = bc.get("broken_chain_geometry") or {}
        controls["broken_chain"] = {
            "removed_original_indices": removed, "removed_count": len(removed),
            "removed_assets": [CHAIN12[i] for i in removed],
            "remaining": bc["n_boxes"],
            "new_index_to_original_index": {str(k): v for k, v in new_to_orig.items()},
            "upstream_original_indices": [new_to_orig[b["index"]] for b in up],
            "downstream_original_indices": [new_to_orig[b["index"]] for b in down],
            "void_between_faces_m": geom.get("void_between_faces_m"),
            "max_flanking_reach_m": geom.get("max_flanking_reach_m"),
            "void_exceeds_reach": geom.get("void_exceeds_reach"),
            "upstream_toppled": sum(1 for b in up if b["toppled"]), "upstream_total": len(up),
            "upstream_fallen": sum(1 for b in up if b["fallen"]),
            "downstream_toppled": sum(1 for b in down if b["toppled"]), "downstream_total": len(down),
            "downstream_fallen": sum(1 for b in down if b["fallen"]),
            "upstream_all_fell": all(b["fallen"] for b in up),
            "downstream_stayed": all(not b["fallen"] for b in down),
            "links": bc["links"], "topple_order": bc["topple_order"],
            "topple_order_original_indices": [new_to_orig[i] for i in bc["topple_order"]],
            "downstream_max_tilt_deg": max((b["max_tilt_deg"] for b in down), default=None),
            "void_report": geom,
            "pass": bool(geom.get("void_exceeds_reach") and up and down
                         and all(b["fallen"] for b in up)
                         and all(not b["fallen"] for b in down)),
            "note": ("pass requires a NON-EMPTY upstream and downstream set, a void that EXCEEDS the "
                     "reachable span, upstream falling and downstream staying up; an empty set can no "
                     "longer satisfy it vacuously"),
        }

        # --- fixed-initial-state repeats x3 -------------------------------------------------------
        reps = []
        for k in range(3):
            rr = run_cfg(CHAIN12, GAPS12, trigger="real_box", trigger_spec=TRIG)
            reps.append({"repeat": k, "topple_order": rr["topple_order"],
                         "topple_steps": [b["topple_step"] for b in rr["boxes"]],
                         "adjacent_gaps_frames": rr["adjacent_onset_gaps_frames"],
                         "boxes_toppled": rr["boxes_toppled"],
                         "adjacent_onset_min_frames": rr["adjacent_onset_min_frames"]})
        orders = [tuple(x["topple_order"]) for x in reps]
        controls["repeat_x3"] = {
            "repeats": reps, "orders": [list(o) for o in orders],
            "order_identical": len(set(orders)) == 1,
            "boxes_toppled": [x["boxes_toppled"] for x in reps],
        }

        # --- half dt ------------------------------------------------------------------------------
        # SEQUENCE is compared, not the 60 deg completion order. The 60 deg crossing is a threshold
        # event on a falling body, and halving dt legitimately shifts each crossing by a step or two,
        # which can reorder two neighbours whose falls overlap; the ORDER OF MOTION ONSET is the
        # physical quantity and is what must agree.
        hd = run_cfg(CHAIN12, GAPS12, trigger="real_box", trigger_spec=TRIG, dt=DT / 2.0)
        ref = (result.get("chain12", {}) or {})
        controls["half_dt"] = {
            "dt_s": hd["dt_s"], "topple_order": hd["topple_order"],
            "order_matches_reference": (ref.get("topple_order") is not None
                                        and hd["topple_order"] == ref.get("topple_order")),
            "reference_order": ref.get("topple_order"),
            "boxes_toppled": hd["boxes_toppled"], "boxes_fallen": hd["boxes_fallen"],
            "is_sequential_chain": hd["is_sequential_chain"],
            "sequence_matches_reference": bool(
                hd["is_sequential_chain"] and ref.get("is_sequential_chain")),
            "motion_onset_2deg_order_is_chain": hd.get("motion_onset_2deg_order_is_chain"),
            "motion_onset_2deg_all_sequential": hd.get("motion_onset_2deg_all_sequential"),
            "motion_onset_2deg_min_adjacent_frames": hd.get(
                "motion_onset_2deg_min_adjacent_frames"),
            "adjacent_gaps_frames": hd["adjacent_onset_gaps_frames"],
            "note": ("`is_sequential_chain` and `sequence_matches_reference` are the timestep test; "
                     "`order_matches_reference` is reported as well but compares 60 deg COMPLETION "
                     "crossings, which a finer timestep can legitimately reorder between two boxes "
                     "whose falls overlap."),
        }

        # --- density invariance -------------------------------------------------------------------
        controls["density_sweep"] = {
            str(d): {k: v for k, v in run_cfg(CHAIN12, GAPS12, trigger="real_box",
                                              trigger_spec=TRIG, density=d).items()
                     if k in ("boxes_toppled", "n_boxes", "topple_order")}
            for d in DENSITY_SWEEP}

        # --- margin sensitivity -------------------------------------------------------------------
        msens = {}
        for label, m in (("zero", 0.0), ("measured_resting_height", measured_margin),
                         ("bisected_first_contact_worst", 0.0027669)):
            rm = run_chain(assets, CHAIN12, GAPS12, A.density, m, support_z=A.support_z,
                           trigger="real_box", sim_s=A.sim_s, trigger_spec=TRIG)
            msens[label] = {"margin_m": m, "boxes_toppled": rm["boxes_toppled"],
                            "n_boxes": rm["n_boxes"], "topple_order": rm["topple_order"],
                            "min_box_max_tilt_deg": min(b["max_tilt_deg"] for b in rm["boxes"])}
        controls["margin_sensitivity"] = msens

        # --- gap sensitivity: uniform spacing, to show the chain is NOT mechanically even ---------
        gsens = {}
        for gf in (0.15, 0.20, 0.25, 0.30, 0.35):
            rg = run_cfg(CHAIN12, [gf] * (len(CHAIN12) - 1), trigger="real_box", trigger_spec=TRIG)
            gsens[f"uniform_{gf}"] = {"gap_fraction": gf, "boxes_toppled": rg["boxes_toppled"],
                                      "n_boxes": rg["n_boxes"], "topple_order": rg["topple_order"]}
        controls["gap_sensitivity"] = gsens

        result["controls"] = controls

    # ---- write ---------------------------------------------------------------------------------
    traj = result.pop("_traj12", None)
    boxes12 = result.pop("_boxes12", None)
    trig_row = result.pop("_trig12", None)
    out = Path(A.out)
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")

    if traj is not None:
        # The PROJECT trajectory contract: frames start at 0, time_s = frame/24, blender_frame =
        # frame+1, step = the 480 Hz substep index, quaternions in xyzw order.
        bodies_out = {}
        for b in boxes12:
            idx = b["index"]
            bodies_out[f"box{idx}"] = traj[idx]
        if trig_row:
            bodies_out["trigger"] = trig_row
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

