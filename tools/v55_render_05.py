"""V5.5 stage 05 render: replay the solved trajectory in Blender and produce the delivery video.

ARCHITECTURE, AND WHY IT IS SPLIT THIS WAY

The solve runs on the server, because that is where the permitted workspace and the PyBullet build
are. The render runs LOCALLY, and not by preference: the server's Blender 3.4.1 does not start at all
(`libxkbcommon.so.0` is missing from every tree available to the loader, and the loader reports it
before anything else can fail). The runtime copy `italian_flat_runtime.blend` is therefore written by
the local Blender 4.2.23 and opened by that same build, so the file version matches the reader.

NOTHING IS PRESCRIBED HERE. Every position in the video comes from `trajectory.json`, which PyBullet
produced. This script only transcribes those poses into keyframes and points a camera at them.

HOW A BODY'S TRAJECTORY IS APPLIED TO SCENE OBJECTS

The solver records a BODY frame per instance. A scene object has its own authored frame, so the
object is not simply moved to the body's position -- that would drop it by the offset between its own
origin and the proxy anchor and would spin it about the wrong point. Instead:

  * `anchor` is the object's own local point that corresponds to the body origin: the AABB centre in
    x and y and the AABB minimum in z, matching how the solver defined `body_origin` for the props
    (and the AABB centre on all three axes for the striker, whose body origin is a centre).
  * The object's frame-0 matrix is chosen so that this anchor lands exactly on the body's frame-0
    position, keeping the authored rotation.
  * Every later frame applies the body's rigid RELATIVE motion from frame 0. Because that transform
    starts at identity, the rendered object begins exactly at its settled pose rather than jumping
    to it, and the anchor tracks the body origin for the whole clip.

The alternative -- placing each object at `body.position` -- is wrong by construction and was the
reason an earlier attempt rendered the props floating at the tray's rim height.

CAMERA

09 fixes resolution, elevation band, focal range and framing occupancy, so the azimuth is not chosen
by eye: every 10 degrees is evaluated, the framing of the whole recorded motion is projected into
normalised device coordinates, and the azimuth that best satisfies 09's occupancy rule while keeping
every key event inside the 2-98 percent safe frame is the one used. The choice and the numbers behind
it are written to `camera_solve.json`.

USAGE (run with the local Blender)
    blender.exe --background --factory-startup --python tools/v55_render_05.py -- \
        --run <run dir> --out <render dir> --mode probe|keyframes|preview|final \
        [--res 1920x1080] [--spp 64] [--frames 0-61] [--azimuth 270]
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

# ---------------------------------------------------------------------------------------
# arguments
# ---------------------------------------------------------------------------------------


def parse_args() -> dict:
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out = {"mode": "probe", "res": "1920x1080", "spp": 64, "frames": None, "azimuth": None}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--"):
            key = argv[i][2:]
            val = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else "1"
            out[key] = val
            i += 2
        else:
            i += 1
    for req in ("run", "out"):
        if req not in out:
            raise SystemExit(f"missing --{req}")
    return out


ARGS = parse_args()
RUN = Path(ARGS["run"])
OUT = Path(ARGS["out"])
MODE = ARGS["mode"]
RES_X, RES_Y = (int(v) for v in ARGS["res"].lower().split("x"))
SPP = int(ARGS["spp"])
THREADS = int(ARGS["threads"]) if ARGS.get("threads") not in (None, "None") else 8
AZ_OVERRIDE = None if ARGS["azimuth"] in (None, "None") else float(ARGS["azimuth"])

# 09's render budget, recorded so the run can be checked against it rather than trusted.
BUDGET = {
    "keyframes": {"res": (960, 540), "spp": (8, 16)},
    "preview": {"res": (1280, 720), "spp": (16, 32)},
    "final": {"res": (1920, 1080), "spp": (64, 128)},
}

ROOT = Path(r"D:\workspace\project1_database")
RUNTIME = ROOT / "outcomes/v55/scenes/italian_flat/runtime"
RUNTIME_BLEND = RUNTIME / "italian_flat_runtime.blend"
GSO = ROOT / "models/gso/Creatine_Monohydrate"

print("=" * 104)
print(f"=== stage 05 render: mode={MODE} res={RES_X}x{RES_Y} spp={SPP} ===")
print(f"  run {RUN}")
print(f"  out {OUT}")

cfg = json.loads((RUN / "resolved_config.json").read_text(encoding="utf-8"))
traj_all = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))
TRAJ = traj_all["bodies"]
bodies = json.loads((RUN / "bodies.json").read_text(encoding="utf-8"))
cam_cfg = json.loads((RUN / "camera.json").read_text(encoding="utf-8"))
provenance = json.loads((RUN / "provenance.json").read_text(encoding="utf-8"))
BFPS = int(round(float(cfg["video_fps"])))
FRAME_COUNT = int(cfg["frame_count"])
TARGET = cfg["target_instance_id"]
TRIGGER = cfg["trigger_instance_id"]

# `--frames a-b` renders a sub-range, which is how a keyframe still is produced without rendering
# the whole clip.
if ARGS.get("framelist") not in (None, "None"):
    FRAME_LIST = [int(v) for v in str(ARGS["framelist"]).split(",") if v.strip() != ""]
    FRAME_LO, FRAME_HI = min(FRAME_LIST), max(FRAME_LIST)
elif ARGS["frames"] not in (None, "None"):
    lo, _, hi = str(ARGS["frames"]).partition("-")
    FRAME_LO = int(lo)
    FRAME_HI = int(hi) if hi else int(lo)
    FRAME_LIST = list(range(FRAME_LO, FRAME_HI + 1))
else:
    FRAME_LO, FRAME_HI = 0, FRAME_COUNT - 1
    FRAME_LIST = list(range(FRAME_LO, FRAME_HI + 1))
print(f"  frames {FRAME_LO}..{FRAME_HI} of 0..{FRAME_COUNT-1} at {BFPS} fps"
      + (f"  (explicit list: {FRAME_LIST})"
         if len(FRAME_LIST) < FRAME_HI - FRAME_LO + 1 else ""))


# ---------------------------------------------------------------------------------------
# small helpers, all in the xyzw contract convention at the boundary
# ---------------------------------------------------------------------------------------


def q_xyzw_to_blender(q) -> Quaternion:
    """Contract quaternions are xyzw; Blender's constructor is (w, x, y, z)."""
    x, y, z, w = (float(v) for v in q)
    return Quaternion((w, x, y, z))


def basis(eye: Vector, look: Vector):
    forward = (look - eye).normalized()
    world_up = Vector((0.0, 0.0, 1.0))
    if abs(forward.dot(world_up)) > 0.999:
        world_up = Vector((0.0, 1.0, 0.0))
    right = forward.cross(world_up).normalized()
    up = right.cross(forward).normalized()
    return forward, right, up


def project(p: Vector, eye: Vector, fwd: Vector, right: Vector, up: Vector,
            half_h: float, half_v: float):
    """World point -> normalised device coords, both in 0..1, or None if behind the camera."""
    d = p - eye
    z = d.dot(fwd)
    if z <= 1e-6:
        return None
    return (0.5 + 0.5 * (d.dot(right) / z) / half_h,
            0.5 - 0.5 * (d.dot(up) / z) / half_v)


def evaluated_world_verts(obj):
    """World-space vertices of an object's evaluated mesh (modifiers applied)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    mw = obj.matrix_world
    pts = [mw @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return pts


# ---------------------------------------------------------------------------------------
# open the runtime copy
# ---------------------------------------------------------------------------------------

if not RUNTIME_BLEND.is_file():
    raise SystemExit(f"runtime copy missing: {RUNTIME_BLEND}")
print(f"\n=== opening {RUNTIME_BLEND.name} ({RUNTIME_BLEND.stat().st_size/1e6:.1f} MB) ===")
bpy.ops.wm.open_mainfile(filepath=str(RUNTIME_BLEND))
scene = bpy.context.scene
print(f"  objects {len(scene.objects)}  collections {len(bpy.data.collections)}  "
      f"frame range {scene.frame_start}..{scene.frame_end}  fps {scene.render.fps}")
scene.frame_start = 1
scene.frame_end = FRAME_COUNT
scene.render.fps = BFPS


# ---------------------------------------------------------------------------------------
# assign scene objects to solver bodies, by geometry rather than by guesswork
# ---------------------------------------------------------------------------------------

print("\n=== assigning scene objects to solver bodies ===")
prop_objs = [o for o in scene.objects
             if o.type == "MESH" and any(k in o.name for k in ("Bottiglia", "Bicchiere", "Tappo"))]
print(f"  prop-like objects found: {[o.name for o in prop_objs]}")
if not prop_objs:
    raise SystemExit("no prop objects found in the runtime copy; nothing to animate")

body_origin = {b["instance_id"]: Vector(b["position_m"]) for b in bodies}
assign: dict[str, list] = {}
for o in prop_objs:
    pts = evaluated_world_verts(o)
    c = sum(pts, Vector((0, 0, 0))) / len(pts)
    cands = [(n, (Vector((c.x, c.y, 0.0)) - Vector((p.x, p.y, 0.0))).length)
             for n, p in body_origin.items() if n != TRIGGER]
    name, dist = min(cands, key=lambda t: t[1])
    assign.setdefault(name, []).append(o)
    print(f"  {o.name:28s} centroid ({c.x:.4f}, {c.y:.4f}, {c.z:.4f}) -> {name} "
          f"(xy distance {dist*1000:.2f} mm)")
for b in bodies:
    n = b["instance_id"]
    if n == TRIGGER:
        continue
    print(f"  {n:18s} driven by {[o.name for o in assign.get(n, [])]}")
    if not assign.get(n):
        raise SystemExit(f"body {n} has no scene object; refusing to render a partial replay")

# The striker is not in the scene: it is a solver body built from a downloaded asset, so its visual
# mesh is imported here at the body's frame-0 pose.
print(f"\n=== importing the trigger's VISUAL mesh (not its 124-triangle collision proxy) ===")
striker_visual = GSO / "visual_geometry.obj"
if not striker_visual.is_file():
    raise SystemExit(f"trigger visual mesh missing: {striker_visual}")
before = set(bpy.data.objects.keys())
bpy.ops.wm.obj_import(filepath=str(striker_visual), forward_axis="Y", up_axis="Z")
new = [bpy.data.objects[k] for k in set(bpy.data.objects.keys()) - before]
print(f"  imported: {[o.name for o in new]}")
if not new:
    raise SystemExit("the trigger import produced no objects")
striker = new[0]
striker.name = "trigger__sealed_vessel"
for o in new[1:]:
    o.name = f"trigger_part__{o.name}"
for c in list(striker.users_collection):
    c.objects.unlink(striker)
scene.collection.objects.link(striker)
print(f"  verts {len(striker.data.vertices)}  dims "
      f"{[round(v,6) for v in striker.dimensions]}  location {[round(v,5) for v in striker.location]}")

# The exported OBJ is Z-up already, but the source asset sits with its base at y = -0.5 in its own
# file; the collision proxy was recentred before use, so the visual is recentred the same way. The
# recentring is read from the run's own collision mesh rather than assumed.
def local_aabb(obj):
    pts = [Vector(v.co) for v in obj.data.vertices]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


s_lo, s_hi = local_aabb(striker)
striker_anchor = (s_lo + s_hi) / 2.0  # trigger body origin is the proxy AABB centre
print(f"  local AABB {[round(v,6) for v in s_lo]} .. {[round(v,6) for v in s_hi]}  "
      f"anchor {[round(v,6) for v in striker_anchor]}")


# ---------------------------------------------------------------------------------------
# camera solve
# ---------------------------------------------------------------------------------------

aim = Vector(cam_cfg["aim_point_m"])
focal = float(cam_cfg["focal_length_mm"])
sensor_w = float(cam_cfg["sensor_width_mm"])
sensor_h = sensor_w * RES_Y / RES_X
tan_h = (sensor_w / 2.0) / focal
tan_v = (sensor_h / 2.0) / focal
elev = math.radians(float(cam_cfg["elevation_deg"]))

# WHAT THE CAMERA HAS TO HOLD, AND WHY THERE ARE TWO ANSWERS.
#
# The recorded motion is dominated by the trigger's fall: it is released at z = 1.3076 m and ends at
# z = 0.0663 m on the room floor, a 1.24 m drop, while the interaction it causes -- the glass being
# knocked over -- happens inside the tray within about 0.10 m. Those two scales differ by a factor of
# twelve, so a single framing cannot both contain the whole fall and show the strike at a useful
# size. Rather than pick one and hide the trade-off, both are solved and both are reported:
#
#   full         every recorded position of every body. Nothing leaves frame. The interaction is
#                then necessarily small, and that is measured and stated.
#   interaction  every position while the TRIGGER is still at or above the table surface, plus the
#                TARGET's whole trajectory. This is the interaction window: release, descent,
#                strike and topple. The trigger's subsequent fall to the floor leaves the bottom of
#                the frame, and that is disclosed rather than framed away silently.
#
# The interaction framing is the one used for the delivery, because a video in which the strike is
# not visible does not deliver what the task asks for. The full framing is kept as a diagnostic and
# its numbers are recorded, so the claim "nothing was cropped" can be checked rather than believed.
TABLE_TOP_Z = 0.5150


def motion_points(scope: str) -> list:
    if scope == "full":
        return [Vector(r["position_m"]) for rows in TRAJ.values() for r in rows]
    pts = []
    for name, rows in TRAJ.items():
        for r in rows:
            if name == TRIGGER and r["position_m"][2] < TABLE_TOP_Z - 0.05:
                continue
            pts.append(Vector(r["position_m"]))
    return pts


def solve_camera(pts, az_deg, d0=4.0, margin=0.02, elev_rad=None):
    """Choose the distance that just fits every point inside the safe frame, at this azimuth.

    The projection is perspective, so the span does not scale exactly as 1/distance and the distance
    is refined rather than solved in closed form. The distance is driven to a span of `FIT_SPAN`
    rather than to the safe-frame limit: the projected box is not centred on the aim point (the aim
    is the 3D centre, which projects off-centre), so a fit that exactly touches the limit leaves one
    side outside it. `FIT_SPAN` leaves room for that asymmetry, and the final box is then checked
    against the margin rather than assumed to satisfy it.
    """
    FIT_SPAN = 0.90
    elev = elev_rad if elev_rad is not None else math.radians(float(cam_cfg["elevation_deg"]))
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo + hi) / 2.0
    az = math.radians(az_deg)
    d = d0
    for _ in range(4):
        eye = c + Vector((d * math.cos(elev) * math.cos(az),
                          d * math.cos(elev) * math.sin(az),
                          d * math.sin(elev)))
        fwd, right, up = basis(eye, c)
        ndc = [project(p, eye, fwd, right, up, tan_h, tan_v) for p in pts]
        if any(n is None for n in ndc):
            return None
        sx = max(n[0] for n in ndc) - min(n[0] for n in ndc)
        sy = max(n[1] for n in ndc) - min(n[1] for n in ndc)
        d = d * max(sx, sy) / FIT_SPAN
    # A final small correction for the residual asymmetry: shift the aim so the projected box is
    # centred, then re-fit once. Without this the box can sit off-centre by more than the margin
    # even though its size is right.
    for _ in range(3):
        eye = c + Vector((d * math.cos(elev) * math.cos(az),
                          d * math.cos(elev) * math.sin(az), d * math.sin(elev)))
        fwd, right, up = basis(eye, c)
        ndc = [project(p, eye, fwd, right, up, tan_h, tan_v) for p in pts]
        cx = 0.5 * (max(n[0] for n in ndc) + min(n[0] for n in ndc))
        cy = 0.5 * (max(n[1] for n in ndc) + min(n[1] for n in ndc))
        if abs(cx - 0.5) < 1e-4 and abs(cy - 0.5) < 1e-4:
            break
        # Shift the aim along the image axes by the projected offset, scaled by depth.
        c = c + right * ((cx - 0.5) * 2 * tan_h * d) - up * ((cy - 0.5) * 2 * tan_v * d)
        eye = c + Vector((d * math.cos(elev) * math.cos(az),
                          d * math.cos(elev) * math.sin(az), d * math.sin(elev)))
        fwd, right, up = basis(eye, c)
        ndc = [project(p, eye, fwd, right, up, tan_h, tan_v) for p in pts]
        sx = max(n[0] for n in ndc) - min(n[0] for n in ndc)
        sy = max(n[1] for n in ndc) - min(n[1] for n in ndc)
        d = d * max(sx, sy) / FIT_SPAN
    eye = c + Vector((d * math.cos(elev) * math.cos(az),
                      d * math.cos(elev) * math.sin(az), d * math.sin(elev)))
    fwd, right, up = basis(eye, c)
    ndc = [project(p, eye, fwd, right, up, tan_h, tan_v) for p in pts]
    x0, x1 = min(n[0] for n in ndc), max(n[0] for n in ndc)
    y0, y1 = min(n[1] for n in ndc), max(n[1] for n in ndc)
    inside = x0 >= margin - 1e-6 and x1 <= 1 - margin + 1e-6 and \
        y0 >= margin - 1e-6 and y1 <= 1 - margin + 1e-6
    return {"azimuth_deg": az_deg, "distance_m": d, "aim_m": [float(v) for v in c],
            "eye_m": [float(v) for v in eye], "span_x": x1 - x0, "span_y": y1 - y0,
            "box": [x0, x1, y0, y1], "inside_safe_frame": bool(inside),
            "score": (x1 - x0) * (y1 - y0)}


print("\n=== camera solve ===")
cam_obj = None
print(f"  focal {focal} mm  half-angle tan h {tan_h:.6f} v {tan_v:.6f}")
# 09 prefers a low 0-8 degree elevation for a single interaction, so the LOW band is what is
# searched. If the low band cannot clear the tray rim the elevation is raised and the deviation
# from 09's preference is reported rather than made silently.
ELEVATIONS = [float(cam_cfg["elevation_deg"]), 3.0, 8.0, 12.0, 16.0, 22.0, 30.0]
solutions = {}
for scope in ("full", "interaction"):
    pts = motion_points(scope)
    rows_report = []
    for el_deg in ELEVATIONS:
        elev_r = math.radians(el_deg)
        for az_deg in ([AZ_OVERRIDE] if AZ_OVERRIDE is not None else range(0, 360, 10)):
            r = solve_camera(pts, az_deg, elev_rad=elev_r)
            if r is not None:
                r["elevation_deg"] = el_deg
                rows_report.append(r)
    rows_report.sort(key=lambda r: -r["score"])
    print(f"\n  --- scope '{scope}': {len(pts)} points, {len(rows_report)} candidates ---")
    print(f"  {'az':>5s} {'elev':>6s} {'dist_m':>8s} {'span_x':>8s} {'span_y':>8s} {'safe':>6s}  "
          f"{'x0':>7s} {'x1':>7s} {'y0':>7s} {'y1':>7s}")
    for r in rows_report[:8]:
        b = r["box"]
        print(f"  {r['azimuth_deg']:5d} {r['elevation_deg']:6.1f} {r['distance_m']:8.4f} "
              f"{r['span_x']:8.4f} {r['span_y']:8.4f} {str(r['inside_safe_frame']):>6s}  "
              f"{b[0]:7.4f} {b[1]:7.4f} {b[2]:7.4f} {b[3]:7.4f}")
    good = [r for r in rows_report if r["inside_safe_frame"]]
    if not good:
        # Report the best available fit rather than only failing, so the shortfall is visible.
        b = rows_report[0]["box"]
        print(f"  no candidate fits the 2-98% safe frame; best was az "
              f"{rows_report[0]['azimuth_deg']} elev {rows_report[0]['elevation_deg']} "
              f"with box x[{b[0]:.4f},{b[1]:.4f}] y[{b[2]:.4f},{b[3]:.4f}]")
        solutions[scope] = {"chosen": None, "candidates": rows_report[:60], "points": len(pts),
                            "table_top_z": TABLE_TOP_Z}
        continue
    best = good[0]
    solutions[scope] = {"chosen": best, "candidates": rows_report[:60],
                        "points": len(pts), "table_top_z": TABLE_TOP_Z}
    print(f"  CHOSEN az {best['azimuth_deg']} elev {best['elevation_deg']:.1f} deg "
          f"dist {best['distance_m']:.4f} m span_x {best['span_x']*100:.1f}% "
          f"span_y {best['span_y']*100:.1f}% safe_frame=OK")
SCOPE = "interaction" if solutions.get("interaction", {}).get("chosen") else "full"
if not solutions.get(SCOPE, {}).get("chosen"):
    raise SystemExit("FATAL: neither framing scope fits the 09 safe frame at this field of view; "
                     "a wider lens is needed and that is a camera decision, not a solver one")
print(f"\n  framing scopes solved; the final choice is made AFTER the animation exists, because")
print(f"  which sightline can actually SEE the interaction can only be measured once the moving")
print(f"  objects are in place. Candidate tables are printed above and kept in camera_solve.json.")


def place_camera(eye_v: Vector, aim_v: Vector, name="V55_05_Camera", lens_mm=None):
    """Create or move the delivery camera to look from eye at aim.

    `lens_mm` matters because the framing shortlist varies focal length: a 35 mm camera can sit close
    and still hold the whole interaction, a 50 mm one must sit further back. Placing a 35 mm eye on a
    50 mm lens would reproduce neither the framing nor the visibility that was measured for it.
    """
    global cam_obj, focal, tan_h, tan_v
    if lens_mm is not None:
        focal = float(lens_mm)
        half_v = math.atan((sensor_w * RES_Y / RES_X) / (2.0 * focal))
        tan_v = math.tan(half_v)
        tan_h = tan_v * RES_X / RES_Y
    if cam_obj is None:
        cam_data = bpy.data.cameras.new(name)
        cam_data.sensor_width = sensor_w
        cam_obj = bpy.data.objects.new(name, cam_data)
        scene.collection.objects.link(cam_obj)
    cam_obj.data.lens = focal
    cam_obj.location = eye_v
    cam_obj.rotation_mode = "QUATERNION"
    cam_obj.rotation_quaternion = (-(aim_v - eye_v).normalized()).to_track_quat("Z", "Y")
    scene.camera = cam_obj
    bpy.context.view_layer.update()
    return cam_obj


# ---------------------------------------------------------------------------------------
# build the animation
# ---------------------------------------------------------------------------------------

print("\n=== keyframing the recorded trajectory ===")


def anchor_of(obj, mode: str) -> Vector:
    lo, hi = local_aabb(obj)
    if mode == "centre":
        return (lo + hi) / 2.0
    # Body origin for a prop is the AABB centre in x and y and the AABB minimum in z, which is how
    # v55_final_05.py defined it when it placed the collision proxy on the tray floor.
    return Vector(((lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0, lo.z))


animated = []


def keyframe_rigid(obj, rows, anchor: Vector, orig_rot: Quaternion, name: str):
    """Apply a body's recorded rigid motion to a scene object, anchored at frame 0.

    ORDER MATTERS AND IS THE WHOLE POINT OF THIS FUNCTION. `scene.frame_set` re-evaluates the
    animation, so it must be called BEFORE the pose is written. An earlier version called it after,
    which silently restored the object's already-keyed transform over the new pose and then
    keyframed THAT -- so all 62 keys came out identical and the replay showed a frozen frame. The
    verification below now fails the run instead of shipping it.

    The pose is set through `matrix_world` and then keyframed, rather than decomposed and assigned
    to `location`/`rotation_quaternion` by hand: for a parented object the two frames differ, and
    `matrix_world` is the one the trajectory was recorded in. Blender derives the local basis from
    it, so the keyframes capture the pose that was asked for.
    """
    obj.rotation_mode = "QUATERNION"
    # A parented object's world matrix is the parent's times its own; the trajectory is in world
    # space, so the object is detached from its parent and its world transform carried over.
    if obj.parent is not None:
        keep = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = keep
        print(f"      (detached {obj.name} from its parent; its world pose is unchanged)")
    p0 = Vector(rows[0]["position_m"])
    q0 = q_xyzw_to_blender(rows[0]["quaternion_xyzw"])
    m0 = Matrix.Translation(p0 - orig_rot @ anchor) @ orig_rot.to_matrix().to_4x4()
    for r in rows:
        p = Vector(r["position_m"])
        q = q_xyzw_to_blender(r["quaternion_xyzw"])
        # Rigid relative motion from frame 0: T = Translate(p) Rot(q) Rot(q0)^-1 Translate(-p0).
        t = (Matrix.Translation(p) @ q.to_matrix().to_4x4()
             @ q0.to_matrix().to_4x4().inverted() @ Matrix.Translation(-p0))
        f = int(r["blender_frame"])
        scene.frame_set(f)          # FIRST: advance time and re-evaluate the animation
        obj.matrix_world = t @ m0   # THEN: write the pose for this frame
        obj.keyframe_insert("location", frame=f)
        obj.keyframe_insert("rotation_quaternion", frame=f)
    animated.append({"body": name, "objects": [obj.name], "anchor_local": [float(v) for v in anchor],
                     "keyframes": len(rows),
                     "first_frame": int(rows[0]["blender_frame"]),
                     "last_frame": int(rows[-1]["blender_frame"])})
    print(f"  {name:18s} -> {obj.name:28s} {len(rows)} keys "
          f"({rows[0]['blender_frame']}..{rows[-1]['blender_frame']})")


for name, objs in assign.items():
    rows = TRAJ[name]
    for o in objs:
        keyframe_rigid(o, rows, anchor_of(o, "centre_zmin"), o.matrix_world.to_quaternion(), name)

# The trigger has no authored scene pose, so its frame-0 anchor is defined directly.
s_rows = TRAJ[TRIGGER]
s_p0 = Vector(s_rows[0]["position_m"])
s_q0 = q_xyzw_to_blender(s_rows[0]["quaternion_xyzw"])
striker.rotation_mode = "QUATERNION"
s_m0 = Matrix.Translation(s_p0 - s_q0 @ striker_anchor) @ s_q0.to_matrix().to_4x4()
for r in s_rows:
    p = Vector(r["position_m"])
    q = q_xyzw_to_blender(r["quaternion_xyzw"])
    t = (Matrix.Translation(p) @ q.to_matrix().to_4x4()
         @ s_q0.to_matrix().to_4x4().inverted() @ Matrix.Translation(-s_p0))
    f = int(r["blender_frame"])
    scene.frame_set(f)              # FIRST: advance time
    striker.matrix_world = t @ s_m0  # THEN: write the pose
    striker.keyframe_insert("location", frame=f)
    striker.keyframe_insert("rotation_quaternion", frame=f)
animated.append({"body": TRIGGER, "objects": [striker.name], "anchor_local": [float(v) for v in striker_anchor],
                 "keyframes": len(s_rows),
                 "first_frame": int(s_rows[0]["blender_frame"]),
                 "last_frame": int(s_rows[-1]["blender_frame"])})
print(f"  {TRIGGER:18s} -> {striker.name:28s} {len(s_rows)} keys "
      f"({s_rows[0]['blender_frame']}..{s_rows[-1]['blender_frame']})")

# Linear interpolation, because the states are already at video-frame resolution and a Bezier curve
# would overshoot between them -- the rendered motion would then not be the solved motion.
n_curves = 0
for item in animated:
    for oname in item["objects"]:
        o = bpy.data.objects[oname]
        ad = o.animation_data
        if not ad or not ad.action:
            continue
        for fc in ad.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
            n_curves += 1
print(f"  {n_curves} f-curves set to LINEAR interpolation "
      f"(the states are already at video-frame resolution)")

# ---------------------------------------------------------------------------------------
# verification: does the rendered animation actually move, and is the target visible?
# ---------------------------------------------------------------------------------------

print("\n=== verification of the built animation ===")
# WHAT IS COMPARED, AND WHY IT IS THE ANCHOR RATHER THAN THE OBJECT ORIGIN.
#
# The trajectory stores a BODY position. That body position corresponds to a specific point on the
# object -- its anchor (AABB centre in x/y and AABB minimum in z for a prop) -- not to the object's
# origin. Comparing the object's origin against the body position therefore compares two different
# points and reported a false mismatch of 1.8 mm for a bottle that is genuinely almost still and
# 234 mm for a glass that moves 95 mm: the difference was the anchor's offset being rotated as the
# glass toppled. The anchor's WORLD position is the quantity the solver recorded, so that is what is
# compared, and it is also what the camera projections used.
motion = {}
for name, rows in TRAJ.items():
    entry = next((i for i in animated if i["body"] == name), None)
    if entry is None:
        continue
    objs = [bpy.data.objects[o] for o in entry["objects"]]
    anchor_local = Vector(entry["anchor_local"])
    seen = []
    for f in range(1, FRAME_COUNT + 1):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        o = objs[0]
        seen.append(o.matrix_world @ anchor_local)
    uniq = len({tuple(round(v, 9) for v in s) for s in seen})
    rendered_travel = max((s - seen[0]).length for s in seen)
    rec = [Vector(r["position_m"]) for r in rows]
    recorded_travel = max((p - rec[0]).length for p in rec)
    # The absolute agreement at frame 0 is the placement check; the travel agreement is the replay
    # check. Both are needed: a constant offset would pass the travel test alone.
    placed_err = (seen[0] - rec[0]).length
    delta = abs(rendered_travel - recorded_travel)
    motion[name] = {
        "distinct_positions": uniq, "total_frames": len(seen),
        "rendered_travel_m": rendered_travel, "recorded_travel_m": recorded_travel,
        "travel_error_m": delta, "anchor_placement_error_m": placed_err,
        "travel_matches": delta <= max(2e-4, 0.02 * max(recorded_travel, 1e-4)),
        "placement_matches": placed_err <= 1e-3,
    }
    print(f"  {name:18s} {uniq:3d}/{len(seen)} distinct  rendered travel "
          f"{rendered_travel*1000:10.4f} mm  recorded {recorded_travel*1000:10.4f} mm  "
          f"err {delta*1e6:8.1f} um  anchor placed within {placed_err*1e6:8.1f} um  "
          f"{'MATCH' if motion[name]['travel_matches'] and motion[name]['placement_matches'] else 'MISMATCH'}")

bad = []
for name, m in motion.items():
    if m["distinct_positions"] < 2 and m["recorded_travel_m"] > 1e-3:
        bad.append(f"{name}: only 1 distinct position but the trajectory moves "
                   f"{m['recorded_travel_m']*1000:.3f} mm")
    if not m["travel_matches"]:
        bad.append(f"{name}: rendered {m['rendered_travel_m']*1000:.3f} mm vs recorded "
                   f"{m['recorded_travel_m']*1000:.3f} mm")
    if not m["placement_matches"]:
        bad.append(f"{name}: anchor placed {m['anchor_placement_error_m']*1000:.3f} mm from the "
                   f"recorded frame-0 position")
if bad:
    for b in bad:
        print(f"  !! {b}")
    raise SystemExit("FATAL: the built animation does not reproduce the recorded trajectory: "
                     + "; ".join(bad))
print("  every body's anchor is placed within 1 mm of its recorded frame-0 position and its "
      "rendered travel reproduces the recorded travel")


# ---------------------------------------------------------------------------------------
# final camera choice: the framing that can actually SEE the interaction
# ---------------------------------------------------------------------------------------
#
# The projection-only solve above guarantees that the motion fits the frame. It cannot guarantee
# that the motion is VISIBLE, because the room is full of geometry: the tray rim, the table, and the
# lamp all sit between a camera and the props for some sightlines. The first probe measured only
# 19.3 percent of the target's surface and 12.7 percent of the trigger's from a camera that fitted
# the frame perfectly, which is why the choice is made here, with the animation in place and rays
# actually cast, instead of being taken from the projection score.

print("\n=== final camera choice, by measured surface visibility ===")


def evaluated_tris(obj):
    """World-space triangle centroids and normals of an object's evaluated mesh."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    mw = obj.matrix_world
    nm = mw.to_3x3().inverted().transposed()
    cents, norms = [], []
    for t in me.loop_triangles:
        c = mw @ ((me.vertices[t.vertices[0]].co + me.vertices[t.vertices[1]].co
                   + me.vertices[t.vertices[2]].co) / 3.0)
        n = (nm @ t.normal)
        if n.length > 1e-12:
            n.normalize()
        cents.append(c)
        norms.append(n)
    ev.to_mesh_clear()
    return cents, norms


def visibility_of(eye_v: Vector) -> dict:
    """Unoccluded fraction of each body's CAMERA-FACING surface, plus what occludes the rest.

    WHY THE CAMERA-FACING SURFACE AND NOT THE WHOLE SURFACE. The first version of this measured the
    fraction of ALL sampled surface points that a ray from the camera reached, and it reported 57.6
    percent for the glass and 14.7 percent for the trigger. Those numbers cannot be read as "how
    occluded is it", because a convex solid can never show more than about half of its own surface:
    the far half faces away from every camera, and for a concave open cup it is less. Counting the
    back side as "occluded" measures the object's shape, not the sightline, and would fail any
    camera for any object.

    The measurement that answers the actual question -- can the camera see this object -- is the
    unoccluded fraction of the surface that FACES the camera. A triangle is front-facing when its
    normal points towards the eye; among those, a triangle is occluded when the first thing the ray
    from the eye meets is a DIFFERENT object. This is the definition 09's sixty-percent rule can
    sensibly be applied to, and the occluders are named so a shortfall is actionable.
    """
    out = {}
    fb, rb, ub = basis(eye_v, aim_v)
    for name in (TARGET, TRIGGER):
        entry = next((i for i in animated if i["body"] == name), None)
        objs = [bpy.data.objects[o] for o in entry["objects"]] if entry else []
        own = {o.name for o in objs}
        # ONLY THE FRAMES WHERE THIS BODY IS ACTUALLY ON SCREEN ARE MEASURED.
        #
        # The trigger's trajectory continues for 43 frames after the strike while it falls to the
        # room floor, and that part is deliberately outside the delivery framing. Counting those
        # frames as "occluded" measured geometry the video never claims to show, and it produced a
        # misleading 43 percent. The question 09's rule asks is whether the object is visible WHILE
        # IT IS IN FRAME, so a frame is sampled only when the body's recorded position projects
        # inside the safe frame.
        on_screen = []
        for r in TRAJ[name]:
            n = project(Vector(r["position_m"]), eye_v, fb, rb, ub, tan_h, tan_v)
            if n is not None and 0.0 <= n[0] <= 1.0 and 0.0 <= n[1] <= 1.0:
                on_screen.append(int(r["blender_frame"]))
        if not on_screen:
            out[name] = {"front_facing_samples": 0, "unoccluded": 0, "visible_fraction": 0.0,
                         "frames_on_screen": 0, "blocked_by": {}}
            continue
        pick = [on_screen[0], on_screen[len(on_screen) // 3], on_screen[2 * len(on_screen) // 3],
                on_screen[-1]]
        front = visible = 0
        blockers: dict[str, int] = {}
        for f in sorted(set(pick)):
            scene.frame_set(f)
            bpy.context.view_layer.update()
            deps = bpy.context.evaluated_depsgraph_get()
            for o in objs:
                cents, norms = evaluated_tris(o)
                step = max(1, len(cents) // 900)
                for c, n in list(zip(cents, norms))[::step]:
                    to_eye = eye_v - c
                    ln = to_eye.length
                    if ln < 1e-6 or n.dot(to_eye) <= 0.0:
                        continue          # back-facing: not visible to any camera
                    front += 1
                    hit, loc, _hn, _hi, hit_obj, _hm = scene.ray_cast(
                        deps, c + n * 1e-5, to_eye.normalized(), distance=ln)
                    if not hit or (hit_obj is not None and hit_obj.name in own):
                        visible += 1
                    else:
                        k = hit_obj.name if hit_obj else "(none)"
                        blockers[k] = blockers.get(k, 0) + 1
        out[name] = {"front_facing_samples": front, "unoccluded": visible,
                     "visible_fraction": (visible / front) if front else 0.0,
                     "frames_on_screen": len(on_screen), "frames_sampled": sorted(set(pick)),
                     "back_facing_note": "back-facing triangles are excluded by definition",
                     "blocked_by": dict(sorted(blockers.items(), key=lambda kv: -kv[1])[:8])}
    # Also require that the interaction itself is on screen, not merely unoccluded. This tests the
    # SCOPE's own points, so it asks about the release, the descent, the strike and the topple
    # rather than about the trigger's later fall to the floor.
    in_frame = True
    for p in motion_points(SCOPE):
        n = project(p, eye_v, fb, rb, ub, tan_h, tan_v)
        if n is None or not (0.02 <= n[0] <= 0.98 and 0.02 <= n[1] <= 0.98):
            in_frame = False
            break
    out["interaction_in_safe_frame"] = in_frame
    return out


# Candidate eyes.
#
# The authoritative framing search now lives in `tools/v55_camera_opt_05.py`, which searches azimuth,
# elevation, distance AND focal length and reports 09's bands explicitly -- including the finding
# that this event's 45-65% width band is unreachable at any camera because the interaction is about
# 2.55:1 vertical. That script's shortlist is read here so the two agree instead of the render script
# re-deriving a different answer with a narrower search. The local projection solve above is still
# run, because it is what produces the scopes table and the safe-frame guarantee.
cands = []
seen_az = set()
opt_path = RUN / "camera_opt.json"
if opt_path.is_file():
    opt = json.loads(opt_path.read_text(encoding="utf-8"))
    for r in opt.get("shortlist", []):
        key = (round(r["azimuth_deg"]), round(r["elevation_deg"], 1), round(r["focal_mm"]))
        if key in seen_az:
            continue
        seen_az.add(key)
        cands.append((r["azimuth_deg"], r["elevation_deg"], Vector(r["eye_m"]), Vector(r["aim_m"]),
                      r["distance_m"], r))
    print(f"  candidate cameras taken from camera_opt.json (framing search): {len(cands)}")
    print(f"    width-band note from that search: {opt.get('note', '')[:150]}...")
else:
    print(f"  camera_opt.json not present; falling back to the local projection solve only")
scope_sol = solutions[SCOPE]
for r in scope_sol["candidates"][:6]:
    key = (round(r["azimuth_deg"]), round(r["elevation_deg"], 1), round(focal))
    if key in seen_az:
        continue
    seen_az.add(key)
    cands.append((r["azimuth_deg"], r["elevation_deg"], Vector(r["eye_m"]), Vector(r["aim_m"]),
                  r["distance_m"], r))

print(f"  evaluating {len(cands)} camera candidates by casting rays at the moving objects")
print(f"  candidates are visited in the order camera_opt.json lists them, which is 09's own priority")
print(f"  order (low elevation and full azimuth coverage first). The search stops early once a")
print(f"  candidate satisfies every reachable 09 band AND clears the 60% visibility rule, because")
print(f"  continuing past a fully compliant camera would only spend render time to no purpose.")
results = []
EARLY_EXIT = True
for az_deg, el_deg, eye_v, aim_v, d_v, rr in cands:
    # The candidate carries its own focal length, and visibility depends on the FIELD OF VIEW only
    # through which part of the surface is front-facing, so the eye position is what the rays use.
    lens_c = rr.get("focal_mm")
    v = visibility_of(eye_v)
    tfr = v[TARGET]["visible_fraction"]
    sfr = v[TRIGGER]["visible_fraction"]
    worst = min(tfr, sfr)
    results.append({"azimuth_deg": az_deg, "elevation_deg": el_deg, "distance_m": d_v,
                    "focal_mm": lens_c,
                    "eye_m": [float(q) for q in eye_v], "aim_m": [float(q) for q in aim_v],
                    "target_visible": tfr, "trigger_visible": sfr, "worst_visible": worst,
                    "in_safe_frame": v["interaction_in_safe_frame"],
                    "target_front_facing": v[TARGET]["front_facing_samples"],
                    "trigger_front_facing": v[TRIGGER]["front_facing_samples"],
                    "span_x": rr.get("span_x"), "span_y": rr.get("span_y"),
                    "target_proj_height": rr.get("target_proj_height"),
                    "width_band_met": rr.get("width_band_met"),
                    "target_height_band_met": rr.get("target_height_band_met"),
                    "target_blocked_by": v[TARGET]["blocked_by"],
                    "trigger_blocked_by": v[TRIGGER]["blocked_by"]})
    if EARLY_EXIT:
        _r = results[-1]
        if (_r["in_safe_frame"] and _r.get("target_height_band_met")
                and _r["target_visible"] >= 0.60 and _r["trigger_visible"] >= 0.60
                and _r["elevation_deg"] <= 15.0):
            print(f"  compliant camera found after {len(results)} of {len(cands)} candidates: "
                  f"az {_r['azimuth_deg']} elev {_r['elevation_deg']:.1f} deg, target "
                  f"{_r['target_visible']*100:.1f}% / trigger {_r['trigger_visible']*100:.1f}% "
                  f"visible, height band MET -- stopping the search")
            break
results.sort(key=lambda r: (-(r["worst_visible"] if r["in_safe_frame"] else -1)))
print(f"  {'az':>5s} {'elev':>6s} {'dist':>7s} {'lens':>5s} {'target':>8s} {'trigger':>8s} "
      f"{'safe':>6s}  main occluder")
for r in results[:16]:
    bo = list(r["trigger_blocked_by"].items()) or list(r["target_blocked_by"].items())
    print(f"  {r['azimuth_deg']:5d} {r['elevation_deg']:6.1f} {r['distance_m']:7.3f} "
          f"{(str(r['focal_mm']) if r['focal_mm'] else '50'):>5s} "
          f"{r['target_visible']*100:7.1f}% {r['trigger_visible']*100:7.1f}% "
          f"{str(r['in_safe_frame']):>6s}  {bo[0][0] if bo else '-'}")

fit = [r for r in results if r["in_safe_frame"]]
if not fit:
    raise SystemExit("FATAL: no candidate eye keeps the interaction inside the 09 safe frame")


def vis_rank(r):
    """Pick a camera in 09's own priority order.

    09 section 2 is explicit about the ORDER of preference: keep the key object readable, prefer a
    low 0-8 degree camera, change azimuth and depth before raising elevation, allow 12-15 degrees with
    a recorded reason, and never use a near-overhead close-up. Visibility alone is not the criterion:
    a 70-degree overhead camera measured the best visibility here (100% / 80.4%) while being exactly
    what 09 forbids, so ranking on visibility by itself would select the prohibited shot. The band
    flags come first because they are what 09 actually sets as pass conditions, then elevation, then
    visibility.
    """
    el = r["elevation_deg"]
    el_band = 0 if el <= 8.0 else (1 if el <= 15.0 else (2 if el <= 30.0 else 3))
    return (bool(r.get("target_height_band_met")), -el_band, r["worst_visible"])


chosen = max(fit, key=vis_rank)
best_vis = chosen["worst_visible"]
print(f"\n  CHOSEN az {chosen['azimuth_deg']} elev {chosen['elevation_deg']:.1f} deg "
      f"dist {chosen['distance_m']:.4f} m lens {chosen['focal_mm'] or focal} mm")
print(f"    target surface visible {chosen['target_visible']*100:.1f}%, "
      f"trigger {chosen['trigger_visible']*100:.1f}%")
th_ok = "MET" if chosen.get("target_height_band_met") else "NOT MET"
wd_ok = ("MET" if chosen.get("width_band_met")
         else "NOT MET - geometrically unreachable for this event, see camera_opt.json")
print(f"    target projected height {chosen['target_proj_height']*100:.1f}% of frame "
      f"(09 band 8-12%: {th_ok})")
print(f"    span_x {chosen['span_x']*100:.1f}% of frame width (09 band 45-65%: {wd_ok})")
print(f"    this is the BEST candidate among the {len(fit)} that keep the")
print(f"    interaction inside the safe frame, ranked by 09's reachable bands then by visibility")
eye = Vector(chosen["eye_m"])
aim_v = Vector(chosen["aim_m"])
place_camera(eye, aim_v, lens_mm=chosen.get("focal_mm"))
fwd, right, up = basis(eye, aim_v)
dist = chosen["distance_m"]
az_deg = chosen["azimuth_deg"]
elev = math.radians(chosen["elevation_deg"])
span_x = chosen["span_x"]
span_y = chosen["span_y"]
n_trig_out = sum(1 for r in TRAJ[TRIGGER] if r["position_m"][2] < TABLE_TOP_Z - 0.05)
print(f"    {n_trig_out} of {len(TRAJ[TRIGGER])} trigger samples (its fall to the floor after the "
      f"strike) are outside this framing; disclosed rather than hidden")
print(f"    existing cameras left untouched: "
      f"{[o.name for o in scene.objects if o.type == 'CAMERA' and o is not cam_obj]}")

vis = {TARGET: {"samples": 0, "visible": 0, "visible_fraction": chosen["target_visible"],
                "blocked_by": chosen["target_blocked_by"]},
       TRIGGER: {"samples": 0, "visible": 0, "visible_fraction": chosen["trigger_visible"],
                 "blocked_by": chosen["trigger_blocked_by"]}}
occluded = [k for k, v in vis.items() if v["visible_fraction"] < 0.60]
if occluded:
    print(f"  !! below 09's 60% surface visibility: "
          f"{[(k, round(vis[k]['visible_fraction']*100,1)) for k in occluded]} -- reported, not "
          f"hidden. The occluders are named in animation_checks.json")

camera_solve = {
    "mode": MODE, "resolution": [RES_X, RES_Y], "samples_per_pixel": SPP,
    "focal_length_mm": focal, "sensor_width_mm": sensor_w,
    "elevation_deg": chosen["elevation_deg"],
    "used_scope": SCOPE,
    "azimuth_deg": az_deg, "distance_m": dist,
    "eye_m": [float(v) for v in eye], "aim_point_m": [float(v) for v in aim_v],
    "span_x": span_x, "span_y": span_y,
    "safe_frame_margin": 0.02, "inside_safe_frame": True,
    "bands_09": {
        "safe_frame_critical_window": "MET",
        "target_projected_height": chosen.get("target_proj_height"),
        "target_height_band_8_12pct": chosen.get("target_height_band_met"),
        "path_span_width_band_45_65pct": chosen.get("width_band_met"),
        "width_band_note": (
            "NOT MET, and proven unreachable rather than merely unmet: the interaction is about "
            "2.55:1 vertical (the trigger falls 1241 mm while moving ~90 mm horizontally), so in a "
            "16:9 frame span_y/span_x is about 4.5 and a span_y of 100% of frame height yields only "
            "about 22% of frame width. The full azimuth/elevation/distance/focal search in "
            "camera_opt.json found a maximum of 43.7% and only at an 80-degree near-overhead camera "
            "that 09 explicitly forbids. No threshold was relaxed; the shortfall is reported."),
    },
    "framing_source": ("shortlist from tools/v55_camera_opt_05.py, which searches azimuth, "
                       "elevation, distance and focal length and reports 09's bands explicitly; "
                       "the render-side projection solve is still run for the scopes table"),
    "surface_visibility": {k: {"visible_fraction": v["visible_fraction"],
                               "blocked_by": v["blocked_by"]} for k, v in vis.items()},
    "visibility_candidates": results,
    "scopes": {k: {"chosen": v["chosen"], "points": v["points"]}
               for k, v in solutions.items()},
    "disclosure": (
        f"the '{SCOPE}' scope is used: it holds the release, the descent, the strike and the "
        f"topple. The trigger's later fall to the floor leaves the bottom of the frame "
        f"({n_trig_out} of {len(TRAJ[TRIGGER])} samples). The camera is the best-visibility "
        f"candidate among those that keep the interaction inside the 2-98 percent safe frame, "
        f"chosen by casting rays at the moving geometry rather than by the projection fit alone."),
    "budget_09": BUDGET[MODE if MODE in BUDGET else "final"],
    "note": ("elevation/deviation from 09's preferred 0-8 degrees and any visibility shortfall are "
             "reported here with their numbers; the full candidate table is in "
             "`visibility_candidates`"),
}
(RUN / "camera_solve.json").write_text(json.dumps(camera_solve, indent=2), encoding="utf-8")
print(f"  written: {RUN / 'camera_solve.json'}")

scene.frame_set(1)
bpy.context.view_layer.update()

(RUN / "animation_checks.json").write_text(json.dumps({
    "mode": MODE, "resolution": [RES_X, RES_Y], "samples_per_pixel": SPP,
    "frame_count": FRAME_COUNT, "video_fps": BFPS,
    "animated": animated, "motion": motion,
    "visibility": {k: {kk: vv for kk, vv in v.items()} for k, v in vis.items()},
    "min_visibility_required": 0.60,
    "visibility_ok": not occluded,
    "visibility_note": ("`visibility` is the measurement for the CHOSEN camera, taken while the "
                        "camera was being selected; the occluders behind each shortfall are named "
                        "in its `blocked_by` field"),
    "camera_chosen": {"azimuth_deg": chosen["azimuth_deg"],
                      "elevation_deg": chosen["elevation_deg"],
                      "distance_m": chosen["distance_m"],
                      "eye_m": chosen["eye_m"],
                      "target_visible": chosen["target_visible"],
                      "trigger_visible": chosen["trigger_visible"]},
}, indent=2), encoding="utf-8")
print(f"  written: {RUN / 'animation_checks.json'}")


# ---------------------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------------------

if MODE == "probe":
    print("\n=== probe mode: no frames rendered ===")
    raise SystemExit(0)

# `replay` mode builds the scene, the animation and the camera, saves the replayable project, and
# renders nothing. It exists so the required `replay.blend` can be produced and checked without
# spending hours re-rendering, and so a render that is interrupted cannot leave the project missing.
RENDER_NOTHING = MODE == "replay"

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SPP
scene.cycles.use_denoising = True
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = False
scene.render.filepath = str(OUT / f"frames_{MODE}" / "f_")
print(f"\n=== rendering {MODE}: frames {FRAME_LIST if len(FRAME_LIST) < 20 else f'{FRAME_LO}..{FRAME_HI}'}"
      f", {RES_X}x{RES_Y}, {SPP} spp, Cycles CPU, {os.cpu_count()} threads ===")

# ---------------------------------------------------------------------------------------
# redirect the scene's external File Output nodes into this run
# ---------------------------------------------------------------------------------------
#
# 09 section 1 requires this explicitly: "if the scene has external File Output nodes or cache
# paths, redirect them to this run's workspace output first; do not save to the author's old paths."
# The runtime copy carries the author's compositor, and it was in fact writing EXRs to `C:\tmp\`
# (observed: C:\tmp\0001.exr, 0003.exr, 0009.exr during the first keyframe render) -- outside the
# project workspace entirely, which is exactly the behaviour the rule forbids. The nodes are
# re-pointed at this run's `compositor/` directory and every path is recorded, so the redirect is
# evidence rather than an assertion.
node_tree = getattr(scene, "node_tree", None)
redirected = []
if node_tree is not None and getattr(scene, "use_nodes", False):
    comp_dir = OUT / "compositor"
    comp_dir.mkdir(parents=True, exist_ok=True)
    for node in node_tree.nodes:
        if node.type != "OUTPUT_FILE":
            continue
        old_base = getattr(node, "base_path", "") or ""
        node.base_path = str(comp_dir)
        slots = []
        for slot in getattr(node, "file_slots", []):
            slots.append({"old_path": slot.path, "new_path": slot.path})
        redirected.append({"node": node.name, "old_base_path": old_base,
                           "new_base_path": str(comp_dir), "slots": slots})
        print(f"  redirected File Output node '{node.name}': '{old_base}' -> '{comp_dir}'")
if not redirected:
    print("  no File Output nodes in the scene compositor; nothing outside the workspace is written")
else:
    (RUN / "compositor_redirect.json").write_text(json.dumps({
        "note": ("09 section 1: external File Output nodes are redirected into this run so nothing "
                 "is written to the author's paths or outside the project workspace"),
        "output_dir": str(OUT / "compositor"),
        "nodes": redirected,
    }, indent=2), encoding="utf-8")
    print(f"  written: {RUN / 'compositor_redirect.json'}")

# Each mode writes into its OWN frame directory. Keyframe stills, the continuous preview and the
# final delivery are separate passes at different resolutions, and sharing one directory would make
# the refuse-to-overwrite guard reject the second pass while also mixing resolutions in one folder.
frame_dir = OUT / f"frames_{MODE}"
frame_dir.mkdir(parents=True, exist_ok=True)
existing = sorted(frame_dir.glob("f_*.png"))
if existing:
    raise SystemExit(f"FATAL: {len(existing)} frames already exist in {frame_dir}; this project "
                     f"deletes nothing, so move them to remove/ first rather than overwriting")

# Keep the render tractable without changing what is rendered. The defaults (12 bounces in every
# category) are far more than this scene needs and dominate the cost; glass needs transmission, and
# everything else is diffuse or glossy. Sampling is adaptive with a threshold, which is what lets a
# simple frame stop early while a frame full of glass and caustics keeps sampling.
scene.cycles.max_bounces = 6
scene.cycles.diffuse_bounces = 2
scene.cycles.glossy_bounces = 3
scene.cycles.transmission_bounces = 6
scene.cycles.transparent_max_bounces = 8
scene.cycles.volume_bounces = 0
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = 0.01
scene.cycles.use_denoising = True

# ---------------------------------------------------------------------------------------
# persistence: the single largest cost reducer, and it changes nothing about the image
# ---------------------------------------------------------------------------------------
#
# The runtime copy has 527 objects and 464 of them are static room geometry that never moves for the
# whole clip. The first keyframe render measured 185 s/frame at 960x540/16 spp, which is far too slow
# to produce a 62-frame clip: about 3.2 hours even at that reduced resolution. Cycles rebuilds and
# re-shades that unchanging geometry every frame unless persistence is enabled.
#
# `use_persistent_data` keeps the tessellated geometry, the BVH and the shader state between frames;
# only what actually changed is re-synchronised. This is a pure optimisation: the sampled image is
# the same computation, so it does not alter what is rendered or how long the physics takes. The
# per-frame times are recorded either way, so the effect is measurable rather than assumed.
scene.render.use_persistent_data = True
# 09 section 3 fixes the resource envelope: "Cycles device=CPU, 8 threads, one heavy task". Blender
# otherwise defaults to every logical core, which on this machine is 16 -- twice the permitted
# budget. The thread count is set explicitly and recorded, because a run that quietly used more
# threads than allowed would be out of policy even though its output looked identical.
scene.render.threads_mode = "FIXED"
scene.render.threads = THREADS
print(f"  threads: FIXED at {THREADS} (09 section 3 ceiling; machine has {os.cpu_count()} logical)")
print(f"  persistent data: {scene.render.use_persistent_data} (geometry/BVH/shader reuse between "
      f"frames; the image is unchanged, only the rebuild is skipped)")

import time  # noqa: E402

# ---------------------------------------------------------------------------------------
# save the replayable project, which is a required deliverable
# ---------------------------------------------------------------------------------------
#
# 09 section 4 requires a `replay.blend` that stores the runtime copy with the dynamic instances
# bound to the recorded trajectory, so the delivered clip can be reproduced by opening the project
# and pressing play. Without it the only way to regenerate the video is to re-run this script, which
# is not the same thing: the scene, the camera, the animation curves and the frame range all have to
# be in the file.
#
# The save happens BEFORE rendering, so a render that fails or is interrupted still leaves a valid
# replay project. It is written once, into `replays/`, and refuses to overwrite an existing file,
# because this project deletes nothing and a second run belongs in a new run_id.
replay_dir = OUT / "replays"
replay_dir.mkdir(parents=True, exist_ok=True)
replay_path = replay_dir / f"replay_{MODE}.blend"
if replay_path.exists():
    raise SystemExit(f"FATAL: {replay_path} already exists; 09 requires a new run_id rather than "
                     f"overwriting an existing replay project")
scene.frame_start = 1
scene.frame_end = FRAME_COUNT
scene.render.fps = BFPS
scene.frame_set(1)
# The delivery camera is the active one, so opening the file and pressing play reproduces the shot.
scene.camera = cam_obj
bpy.ops.wm.save_as_mainfile(filepath=str(replay_path), copy=True)
print(f"\n=== replay project ===")
print(f"  saved {replay_path}  ({replay_path.stat().st_size/1048576:.1f} MiB)")
print(f"  scene frame range {scene.frame_start}..{scene.frame_end} at {scene.render.fps} fps, "
      f"active camera '{cam_obj.name}' at {focal:.0f} mm")
print(f"  opening this file and pressing play reproduces the delivered shot; the dynamic objects "
      f"carry the recorded trajectory as LINEAR keyframes at video-frame resolution")

if RENDER_NOTHING:
    print(f"\n=== replay mode: replay project written, no frames rendered ===")
    (RUN / "replay_build.json").write_text(json.dumps({
        "replay_blend": str(replay_path),
        "scene_frame_range": [scene.frame_start, scene.frame_end],
        "fps": scene.render.fps,
        "active_camera": cam_obj.name,
        "focal_length_mm": focal,
        "eye_m": [float(v) for v in cam_obj.location],
        "azimuth_deg": az_deg, "elevation_deg": math.degrees(elev),
        "distance_m": dist,
        "animated_objects": animated,
        "verification": motion,
        "note": ("09 section 4: opening `replay_blend` and pressing play reproduces the delivered "
                 "shot. Blender's own rigid-body simulation is off in this scene, so the replayed "
                 "motion comes only from the recorded trajectory keyframes and cannot be "
                 "re-simulated differently."),
    }, indent=2), encoding="utf-8")
    print(f"  written: {RUN / 'replay_build.json'}")
    raise SystemExit(0)

t0 = time.time()
timings = []
for f in FRAME_LIST:
    scene.frame_set(f + 1)
    target_name = frame_dir / f"f_{f:04d}.png"
    # THE OUTPUT PATH IS SET PER FRAME. `bpy.ops.render.render(write_still=True)` writes to
    # `scene.render.filepath` and does not reliably append a frame number to a path that has none,
    # which is why an earlier run rendered 121 seconds and produced no file: the still was written
    # to a name the code did not then look for. Naming the file explicitly removes the guesswork.
    scene.render.filepath = str(target_name)
    ts = time.time()
    bpy.ops.render.render(write_still=True)
    ok = target_name.is_file()
    timings.append({"frame": f, "seconds": time.time() - ts, "file": target_name.name,
                    "written": bool(ok),
                    "bytes": target_name.stat().st_size if ok else 0})
    if not ok:
        raise SystemExit(f"FATAL: frame {f} rendered but {target_name} was not written")
    if (len(timings) % 2 == 0) or f == FRAME_HI:
        rate = (time.time() - t0) / max(1, len(timings))
        print(f"  frame {f:4d}  {time.time()-ts:8.2f} s  "
              f"{target_name.stat().st_size/1024:8.1f} KB  "
              f"mean {rate:7.2f} s/frame  elapsed {time.time()-t0:8.1f} s", flush=True)
    # Keep the marginal cost visible: the first frame includes the BVH build for the whole scene, so
    # its time is not representative and a projection from it alone would be badly pessimistic.
    if len(timings) == 1:
        print(f"  (frame 1 includes the one-off BVH build for {len(scene.objects)} objects)",
              flush=True)

total = time.time() - t0
per = total / max(1, len(timings))
# The first frame carries the BVH build, so the marginal rate is reported from the later frames
# where there are enough of them to mean something.
marginal = (sum(t["seconds"] for t in timings[1:]) / len(timings[1:])) if len(timings) > 2 else per
print(f"\n  rendered {len(timings)} frames in {total:.1f} s "
      f"(mean {per:.2f} s/frame, marginal {marginal:.2f} s/frame after the first)")
(OUT / f"render_timings_{MODE}.json").write_text(json.dumps({
    "mode": MODE, "resolution": [RES_X, RES_Y], "samples_per_pixel": SPP,
    "frame_range": [FRAME_LO, FRAME_HI], "frames_rendered": len(timings),
    "total_seconds": total, "seconds_per_frame": per,
    "marginal_seconds_per_frame": marginal,
    "engine": "CYCLES", "device": "CPU", "denoising": True, "threads": THREADS,
    "persistent_data": bool(scene.render.use_persistent_data),
    "max_bounces": scene.cycles.max_bounces,
    "transmission_bounces": scene.cycles.transmission_bounces,
    "adaptive_threshold": scene.cycles.adaptive_threshold,
    "per_frame": timings,
    "projected_seconds_for_full_clip_marginal": marginal * FRAME_COUNT,
}, indent=2), encoding="utf-8")
print(f"  written: {OUT / f'render_timings_{MODE}.json'}")
print("RENDER DONE")
