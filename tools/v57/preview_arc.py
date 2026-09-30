"""Build a V5.7 domino arc PREVIEW: lay 9 boxes on a real visible pavement strip and render candidates.

WHY THIS EXISTS
---------------
The previous attempt placed a straight chain at world y=2.68, which is (a) 3.1 deg off level, (b) cut by an
authored light-blocker face, and (c) largely outside the scene's own camera framing. The plan for this round
requires an ARC on REAL ground that is actually IN SHOT, shown to the user as real Cycles renders before any
full render is committed.

This script does the visual half of that, deliberately separated from the physics half:

  * picks the pavement strip from measurements (flattest run inside the authored camera's view);
  * lays N boxes along a circular arc, each box's THICKNESS axis along the path tangent (the direction it
    must topple), width across the path, upright +Z -- the axis convention the plan calls out explicitly,
    because using the wide edge as the topple axis is the mistake that makes a chain look wrong;
  * fits the real ground plane at the chosen site and seats every box on it;
  * imports the real GSO visuals in their collision-proxy frames (reusing the verified `box_visual` API);
  * renders candidate cameras at a cheap resolution.

What this script does NOT do: it does not simulate. Preview images from here are labelled VISUAL-ONLY so
they can never be presented as a physics result. The trajectory comes from the solver.

Usage:
    blender --background --factory-startup --python tools/v57/preview_arc.py -- \
        --blend <source.blend> --out <run dir> --n 9 [--cams C1,C2] --res 640x360 --spp 8
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

argv = sys.argv
ARGS = {}
if "--" in argv:
    rest = argv[argv.index("--") + 1:]
    for i in range(0, len(rest) - 1, 2):
        if rest[i].startswith("--"):
            ARGS[rest[i][2:]] = rest[i + 1]

ROOT = Path(ARGS.get("root", r"D:\workspace\project1_database")).resolve()
BLEND = Path(ARGS["blend"]).resolve()
OUT = Path(ARGS["out"]).resolve()
N = int(ARGS.get("n", "9"))
RES = ARGS.get("res", "640x360")
SPP = int(ARGS.get("spp", "8"))
THREADS = int(ARGS.get("threads", "8"))
CAMS = [c.strip() for c in ARGS.get("cams", "C1").split(",") if c.strip()]
ARC_R = float(ARGS.get("arc_r", "2.0"))
SPACING = float(ARGS.get("spacing", "0.155"))
# The uniform CENTRE-TO-CENTRE pitch, in metres. This is the spacing the user approved on screen, and the
# solver is driven with the same value, so the preview and the simulation describe one chain.
PITCH_M = float(ARGS.get("pitch_m", "0.155"))
# Mesh collision margin per side; matches the solver's default so the face gap implied by PITCH_M is the
# same on both sides.
MARGIN_M = float(ARGS.get("margin_mm", "1.0")) / 1000.0
# Retained only for the per-pair reporting line, so the alternative rule stays visible.
GAP_FRAC = float(ARGS.get("gap_frac", "0.25"))
SITE = ARGS.get("site", "")
ONLY_BUILD = ARGS.get("only_build", "0") in ("1", "true", "yes")
# Save the built scene (source scene + the imported boxes + the chosen camera as the active one) so the
# renderer can open it directly. Without this the renderer would have to re-import the visuals, and the two
# would be able to disagree about object names and the collision-frame mapping.
SAVE_BLEND = ARGS.get("save_blend", "")
CAM_SAVE = [c.strip() for c in ARGS.get("cam_save", "").split(",") if c.strip()]
RES_X, RES_Y = (int(v) for v in RES.lower().split("x"))
# The fitting maths below works in the DELIVERY resolution (720p) so the plan's 720p-referenced gates
# (span fraction, >=80 px box height, >=30 px arc deviation) are evaluated at the resolution they were
# written for, independent of whatever preview resolution is actually rendered.
FIT_X, FIT_Y = 1280, 720

sys.path.insert(0, str(ROOT / "tools" / "v56"))
from box_visual import import_asset_object  # noqa: E402

bpy.ops.wm.open_mainfile(filepath=str(BLEND))
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()

ASSET_ROOT = ROOT / "models" / "gso"
# The three real assets, cycled so each appears three times at N=9, plus the real trigger separate.
ASSETS = [
    ("Supernatural_Ouija_Board_Game", "Ouija"),
    ("Hasbro_Trivial_Pursuit_Family_Edition_Game", "TrivialPursuit"),
    ("Hasbro_Cranium_Performance_and_Acting_Game", "Cranium"),
]
TRIGGER_ASSET = ("LEGO_Star_Wars_Advent_Calendar", "Calendar")

# Collision dims measured from the proxies in the previous round (metres, t x w x h in the proxy frame).
# Reused rather than re-derived: these were verified against the proxy report to 1e-8 m.
DIMS = {
    "Supernatural_Ouija_Board_Game": [0.062496879194, 0.275466365908, 0.408406312812],
    "Hasbro_Trivial_Pursuit_Family_Edition_Game": [0.073462, 0.209265, 0.272852],
    "Hasbro_Cranium_Performance_and_Acting_Game": [0.055838, 0.207669099, 0.272573856],
    "LEGO_Star_Wars_Advent_Calendar": [0.0782, 0.2659, 0.3871],
}
PROXY_DIR = ROOT / "outcomes" / "v56" / "mixed_box_domino" / "20260929T142714" / "proxies"

OUT.mkdir(parents=True, exist_ok=True)

print("=" * 108)
print(f"V5.7 arc preview build | N={N} boxes, arc R={ARC_R} m, spacing={SPACING} m")
print(f"  source blend : {BLEND}")
print(f"  output       : {OUT}")
print("=" * 108)

# ---------------------------------------------------------------------------------------------
# 1. pick the site: the flattest visible run, found by the visible_site report if given
# ---------------------------------------------------------------------------------------------
SITE_DEFAULT = {"cx": -1.20, "cy": 12.20, "chord_deg": 30.0}
site = dict(SITE_DEFAULT)
site_path = ROOT / "tmp" / "v57" / "site_choice.json"
if site_path.is_file():
    site = json.loads(site_path.read_text(encoding="utf-8"))
print(f"  site centre  : ({site['cx']:+.3f}, {site['cy']:+.3f})  chord {site['chord_deg']:+.1f} deg")

# Fit the terrain only as a REPORTED REFERENCE, never as the seating authority: the earlier build seated
# boxes on a fitted plane whose residual reached 21.93 mm, which put one box on `leaves` instead of
# pavement. Each box is now seated on the ray measured under its own footprint.
samples = []
for i in range(9):
    for j in range(9):
        x = site["cx"] - 1.6 + 3.2 * i / 8.0
        y = site["cy"] - 1.6 + 3.2 * j / 8.0
        ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, (x, y, 1.5), (0, 0, -1), distance=6.0)
        if ok and obj.name == "Floor_main":
            samples.append((x, y, loc.z))
print(f"  reference ground samples: {len(samples)} on Floor_main (of 81)")
if len(samples) < 8:
    raise SystemExit(f"FATAL: only {len(samples)} ground samples near the site")

n = float(len(samples))
sx = sum(s[0] for s in samples); sy = sum(s[1] for s in samples); sz = sum(s[2] for s in samples)
sxx = sum(s[0] * s[0] for s in samples); syy = sum(s[1] * s[1] for s in samples)
sxy = sum(s[0] * s[1] for s in samples)
sxz = sum(s[0] * s[2] for s in samples); syz = sum(s[1] * s[2] for s in samples)
det = sxx * (syy * n - sy * sy) - sxy * (sxy * n - sy * sx) + sx * (sxy * sy - syy * sx)
a = (sxz * (syy * n - sy * sy) - sxy * (syz * n - sy * sz) + sx * (syz * sy - syy * sz)) / det
b = (sxx * (syz * n - sy * sz) - sxz * (sxy * n - sy * sx) + sx * (sxy * sz - syz * sx)) / det
c = (sz - a * sx - b * sy) / n
resid = [abs(a * s[0] + b * s[1] + c - s[2]) for s in samples]
slope_deg = math.degrees(math.atan(math.hypot(a, b)))
print(f"  fitted ground plane: z = {a:+.6f}*x {b:+.6f}*y {c:+.6f}")
print(f"    slope {slope_deg:.4f} deg, max residual {max(resid) * 1000:.2f} mm, "
      f"height spread {1000 * (max(s[2] for s in samples) - min(s[2] for s in samples)):.2f} mm")


def ground_z(x, y):
    """Real floor height directly under (x, y), not the fitted plane.

    The fitted plane leaves up to 21.93 mm of residual at this site, which would seat some boxes floating
    and others sunk -- far outside the <=1 mm the plan requires. Each box is therefore seated on the floor
    MEASURED at its own footprint, and the residual is reported so the discrepancy is visible rather than
    hidden inside an average.
    """
    ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, (x, y, 1.5), (0.0, 0.0, -1.0), distance=6.0)
    if ok and obj.name == "Floor_main":
        return loc.z, obj.name
    return None, (obj.name if ok else "<nothing>")


# ---------------------------------------------------------------------------------------------
# 2. lay the arc
# ---------------------------------------------------------------------------------------------
# The arc is placed from the scanned site, whose own measurement already proved that every box and the
# trigger land on the declared floor.
cx = site["cx"]
cy = site["cy"]
chord = math.radians(site["chord_deg"])

# SPACING IS A UNIFORM CENTRE PITCH, matching the approved image. The user reviewed and approved the frames
# laid at this spacing, and the solver is driven with the SAME number (`--pitch-m`), so the preview and the
# simulation describe one chain rather than two.
#
# This is also the spacing that keeps the framing gate: tightening to the per-pair 0.25-of-shorter-height
# rule shortens the chain from 1.24 m to 1.06 m and drops the measured span fraction from 0.680 to about
# 0.58, below the 0.60 floor. The uniform pitch corresponds to face gaps of 87-96 mm, i.e. gap fractions of
# 0.319-0.352 of the shorter height -- wider than the 0.25 the straight chain used, but still only about a
# third of a box height, well inside the range that transfers.
pitch_m = []
for i in range(N - 1):
    # Named d_a/d_b, NOT a/b: `a` and `b` are the fitted ground plane's coefficients in the enclosing
    # scope, and reusing those names silently replaced the plane with a dimension list.
    d_a = DIMS[ASSETS[i % len(ASSETS)][0]]
    d_b = DIMS[ASSETS[(i + 1) % len(ASSETS)][0]]
    virtual_gap = PITCH_M - d_a[0] / 2.0 - d_b[0] / 2.0 - 2.0 * MARGIN_M
    pitch_m.append(d_a[0] / 2.0 + virtual_gap + 2.0 * MARGIN_M + d_b[0] / 2.0)
cum = [0.0]
for p in pitch_m:
    cum.append(cum[-1] + p)
total_len = cum[-1]
print("")
print(f"  per-pair centre pitch: {[round(p, 4) for p in pitch_m]}")
print(f"  chain length {total_len:.4f} m (uniform {SPACING} would have been {(N - 1) * SPACING:.4f} m)")

phi0 = -total_len / (2.0 * ARC_R)
arc_cx = cx - ARC_R * math.sin(phi0 + chord)
arc_cy = cy + ARC_R * math.cos(phi0 + chord)

boxes = []
for i in range(N):
    aid, short = ASSETS[i % len(ASSETS)]
    # Arc-length position along the curve, so the chord angle is the true tangent direction.
    phi = phi0 + cum[i] / ARC_R
    ang = chord + phi
    px = arc_cx + ARC_R * math.sin(ang)
    py = arc_cy - ARC_R * math.cos(ang)
    pz, support = ground_z(px, py)
    if pz is None:
        raise SystemExit(f"FATAL: box {i} at ({px:+.3f},{py:+.3f}) has no Floor_main below it; "
                         f"the hit was '{support}'. Refusing to seat a box on an undeclared support.")
    # Tangent points along the arc; the box's THICKNESS axis must lie along it, because that is the axis
    # the box rotates about as it topples forward. Width goes across the path, height stays up.
    tx = math.cos(ang)
    ty = math.sin(ang)
    dims = DIMS[aid]
    t, w, h = dims
    # Local axes: X = tangent (thickness), Y = across path (width), Z = up (height).
    rot = Matrix(((tx, -ty, 0.0), (ty, tx, 0.0), (0.0, 0.0, 1.0)))
    centre_z = pz + h / 2.0
    boxes.append({"index": i, "asset_id": aid, "asset_short": short,
                  "position_m": [px, py, centre_z], "dims_m": [t, w, h],
                  "yaw_rad": ang, "yaw_deg": math.degrees(ang),
                  "rot": [list(r) for r in rot], "ground_z": pz,
                  "support_object": support,
                  "fitted_plane_z": a * px + b * py + c,
                  "seating_residual_m": pz - (a * px + b * py + c)})

# The trigger sits behind box 0 along the tangent, rotated to face it.
tg_aid, tg_short = TRIGGER_ASSET
tg_dims = DIMS[tg_aid]
phi_t = phi0 - (pitch_m[0] * 1.05) / ARC_R
ang_t = chord + phi_t
tgx = arc_cx + ARC_R * math.sin(ang_t)
tgy = arc_cy - ARC_R * math.cos(ang_t)
tgz, tg_support = ground_z(tgx, tgy)
if tgz is None:
    raise SystemExit(f"FATAL: the trigger at ({tgx:+.3f},{tgy:+.3f}) has no Floor_main below it; "
                     f"the hit was '{tg_support}'")
tg_t = math.cos(ang_t); tg_ty = math.sin(ang_t)
trigger = {"index": -1, "asset_id": tg_aid, "asset_short": tg_short,
           "position_m": [tgx, tgy, tgz + tg_dims[2] / 2.0], "dims_m": list(tg_dims),
           "yaw_rad": ang_t, "yaw_deg": math.degrees(ang_t),
           "rot": [[tg_t, -tg_ty, 0.0], [tg_ty, tg_t, 0.0], [0.0, 0.0, 1.0]], "ground_z": tgz,
           "support_object": tg_support}

print("")
print(f"  arc centre ({arc_cx:+.3f}, {arc_cy:+.3f}), phi0 {math.degrees(phi0):+.2f} deg, "
      f"total turn {math.degrees(total_len / ARC_R):.2f} deg")
print(f"  {'i':>3s} {'asset':16s} {'position (x,y,z)':34s} {'yaw':>8s} {'ground z':>10s}")
for b_ in [trigger] + boxes:
    p = b_["position_m"]
    print(f"  {b_['index']:3d} {b_['asset_short']:16s} ({p[0]:+8.4f},{p[1]:+8.4f},{p[2]:+8.4f}) "
          f"{b_['yaw_deg']:+8.2f} {b_['ground_z']:+10.5f}")

# ---------------------------------------------------------------------------------------------
# 3. import the real visuals into the proxy frames and seat them on the arc
# ---------------------------------------------------------------------------------------------
print("")
print("=== importing real visuals ===")
created = []
for b_ in [trigger] + boxes:
    obj_name = f"{'trigger' if b_['index'] < 0 else 'box' + str(b_['index'])}_{b_['asset_short']}"
    proxy = PROXY_DIR / f"{b_['asset_id']}__proxy_collision.obj"
    if not proxy.is_file():
        raise SystemExit(f"FATAL: proxy missing for {b_['asset_id']}: {proxy}")
    proxy_dims = b_["dims_m"]
    # `import_asset_object` already applies the collision-frame mapping and returns (object, report).
    # The body pose is then composed on the left, so the visual's origin lands on the simulated body.
    o, rep = import_asset_object(b_["asset_id"], ASSET_ROOT, proxy_dims, obj_name)
    T_body = Matrix.Translation(Vector(b_["position_m"])) @ \
        Matrix([[b_["rot"][r][c] for c in range(3)] for r in range(3)]).to_4x4()
    o.matrix_world = T_body @ o.matrix_world
    created.append({"name": obj_name, "body": b_["index"], "asset_id": b_["asset_id"],
                    "proxy_frame_offset_m": rep.get("centre_offset_from_origin_m")})
    print(f"  {obj_name:26s} {b_['asset_id'][:40]:40s} verts {len(o.data.vertices)}")

print(f"  created {len(created)} objects")

# ---------------------------------------------------------------------------------------------
# 4. cameras, aimed at the arc
# ---------------------------------------------------------------------------------------------
mid = boxes[N // 2]["position_m"]
chord = Vector((boxes[-1]["position_m"][0] - boxes[0]["position_m"][0],
                boxes[-1]["position_m"][1] - boxes[0]["position_m"][1], 0.0)).normalized()
chord_ang = math.atan2(chord.y, chord.x)
overall = 0.5 * (boxes[0]["dims_m"][2] + boxes[-1]["dims_m"][2])

# The side of the chain the camera must stand on is the side the SCENE ITSELF photographs from. The alley
# only opens toward the authored camera, so the first V5.7 attempt, which placed eyes at larger y than the
# boxes, put all three candidates 0.27-0.52 m inside `paralax_interior_panel_049` and rendered near-black
# frames. `side_sign` therefore points from the chain toward the authored camera position, and every
# candidate azimuth is taken on that side only.
AUTHOR_EYE = Vector((-0.0722, -4.4245, 1.3000))
side = Vector((AUTHOR_EYE.x - mid[0], AUTHOR_EYE.y - mid[1], 0.0)).normalized()
# +1 when the open side lies to the chain's left, -1 when to its right.
side_sign = 1.0 if (chord.x * side.y - chord.y * side.x) >= 0 else -1.0
print("")
print(f"  chain mid {[round(v, 3) for v in mid]}  chord angle {math.degrees(chord_ang):+.2f} deg")
print(f"  authored camera lies on the {'left' if side_sign > 0 else 'right'} of the chain "
      f"(sign {side_sign:+.0f}); all candidate eyes are placed on that side only")

CAM_SPECS = {
    "C1": {"az": 60.0, "dep": 28.0, "dist": 2.6, "lens": 40.0, "target_span": 0.68},
    "C2": {"az": 50.0, "dep": 32.0, "dist": 2.9, "lens": 45.0, "target_span": 0.68},
    "C3": {"az": 70.0, "dep": 25.0, "dist": 2.6, "lens": 40.0, "target_span": 0.68},
}

results = {"boxes": boxes, "trigger": trigger, "site": site,
           "ground_plane": {"a": a, "b": b, "c": c, "slope_deg": slope_deg,
                            "max_residual_m": max(resid)},
           "created": created, "cameras": {}, "mode": "VISUAL_PREVIEW_ONLY__NOT_SIMULATED",
           "arc_r": ARC_R, "gap_frac": GAP_FRAC, "pitch_m": pitch_m,
           "total_turn_deg": math.degrees(total_len / ARC_R)}

cam_obj = scene.camera
if cam_obj is None:
    cam_obj = bpy.data.objects.new("v57_camera", bpy.data.cameras.new("v57_camera"))
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SPP
scene.cycles.use_denoising = True
scene.render.use_compositing = False
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = False
scene.render.threads_mode = "FIXED"
scene.render.threads = THREADS
scene.render.use_persistent_data = True

aim = Vector((mid[0], mid[1], mid[2] * 0.85))


def fit_distance(spec, aim_pt):
    """Solve for the eye distance that puts the chain's span at the target fraction of frame width.

    The span in pixels scales almost exactly as 1/distance for a distant subject, so a closed form is
    available: measure the span at the nominal distance, then scale. This is done arithmetically instead of
    by rendering repeatedly, so a candidate can be framed correctly before any pixels are spent.
    """
    lens = spec["lens"]
    fpx = lens / 36.0 * FIT_X
    # Azimuth is taken on the open side of the chain only, so a candidate can never end up behind a wall.
    ang = chord_ang + side_sign * math.radians(spec["az"])

    def px_of(p, e, fwd, right):
        d = Vector(p) - e
        z = d.dot(fwd)
        return (FIT_X / 2 + fpx * d.dot(right) / z, z)

    def span_at(r):
        e = Vector((aim_pt.x + r * math.cos(ang), aim_pt.y + r * math.sin(ang),
                    aim_pt.z + r * math.tan(math.radians(spec["dep"]))))
        fwd = (aim_pt - e).normalized()
        right = fwd.cross(Vector((0.0, 0.0, 1.0))).normalized()
        lo = px_of(boxes[0]["position_m"], e, fwd, right)
        hi = px_of(boxes[-1]["position_m"], e, fwd, right)
        half0 = 0.5 * fpx * boxes[0]["dims_m"][2] / lo[1]
        half1 = 0.5 * fpx * boxes[-1]["dims_m"][2] / hi[1]
        return (max(lo[0], hi[0]) + half1) - (min(lo[0], hi[0]) - half0)

    nominal = spec["dist"]
    s_nom = span_at(nominal)
    if s_nom <= 1.0:
        return nominal, 0.0, ang
    r_fit = nominal * (s_nom / (spec["target_span"] * FIT_X))
    r_fit = min(max(r_fit, 1.2), 7.0)
    return r_fit, span_at(r_fit) / FIT_X, ang


def clear_eye(aim_pt, ang, r, dep):
    """Shorten the eye distance until the camera is not inside geometry, and report what was in the way.

    An eye inside a wall renders a near-black frame, so this is checked before spending any render time: the
    ray from the chain to the eye is cast, and if a surface appears before the eye the distance is reduced
    to just in front of it. A minimum working distance is enforced, and failure to reach it is reported
    rather than silently accepted.
    """
    dep_r = math.radians(dep)
    tried = []
    for scale in (1.0, 0.92, 0.84, 0.76, 0.68, 0.60, 0.52):
        rr = r * scale
        e = Vector((aim_pt.x + rr * math.cos(ang), aim_pt.y + rr * math.sin(ang),
                    aim_pt.z + rr * math.tan(dep_r)))
        ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, e, (aim_pt - e).normalized(),
                                                     distance=rr)
        gap = (loc - e).length if ok else None
        clear = (not ok) or gap > rr - 0.06
        tried.append({"scale": scale, "r": rr, "eye": list(e), "first_hit": obj.name if ok else None,
                      "gap_m": gap, "clear": clear})
        if clear:
            return e, rr, tried
    return None, None, tried


print("")
print("=== cameras ===")
for key in CAMS:
    spec = CAM_SPECS[key]
    r_nom, achieved_nom, ang = fit_distance(spec, aim)
    eye, r_used, tried = clear_eye(aim, ang, r_nom, spec["dep"])
    if eye is None:
        # Report the obstruction honestly instead of rendering a known-bad frame.
        first = tried[-1]
        results["cameras"][key] = {"spec": spec, "eye": None, "aim": list(aim),
                                   "blocked_by": first["first_hit"], "tried": tried,
                                   "status": "NO_CLEAR_EYE"}
        print(f"  {key}: NO CLEAR EYE found; nearest attempt hit {first['first_hit']} "
              f"at {first['gap_m']:.3f} m. Not rendering.")
        continue
    scene.camera = cam_obj
    cam_obj.data.lens = spec["lens"]
    cam_obj.data.sensor_width = 36.0
    cam_obj.location = eye
    cam_obj.rotation_mode = "QUATERNION"
    cam_obj.rotation_quaternion = (aim - eye).normalized().to_track_quat("-Z", "Y")
    # Blender does not refresh `matrix_world` until the dependency graph is evaluated. Without this the
    # background census below reads the PREVIOUS camera's matrix and reports a ray census for the wrong
    # viewpoint -- which it did, claiming the boxes covered 0.5 % of the frame when they cover ~18 %.
    bpy.context.view_layer.update()
    # Re-measure the span at the distance actually used, and report any shortening.
    fpx = spec["lens"] / 36.0 * FIT_X
    fwd = (aim - eye).normalized()
    right = fwd.cross(Vector((0.0, 0.0, 1.0))).normalized()

    def px_now(p):
        d = Vector(p) - eye
        return (FIT_X / 2 + fpx * d.dot(right) / d.dot(fwd), d.dot(fwd))

    lo = px_now(boxes[0]["position_m"])
    hi = px_now(boxes[-1]["position_m"])
    span_px = ((max(lo[0], hi[0]) + 0.5 * fpx * boxes[-1]["dims_m"][2] / hi[1])
               - (min(lo[0], hi[0]) - 0.5 * fpx * boxes[0]["dims_m"][2] / lo[1]))
    span_frac = span_px / FIT_X
    results["cameras"][key] = {"spec": dict(spec, dist_fitted=r_nom, dist_used=r_used,
                                            span_achieved=span_frac),
                               "eye": list(eye), "aim": list(aim),
                               "chord_angle_deg": math.degrees(chord_ang),
                               "eye_side_sign": side_sign,
                               "eye_shortened": bool(r_used < r_nom - 1e-6),
                               "clearance_attempts": tried[-3:],
                               "first_hit": None, "line_of_sight_blocked": False,
                               "status": "CLEAR"}
    print(f"  {key}: eye {[round(v, 3) for v in eye]} aim {[round(v, 3) for v in aim]} "
          f"lens {spec['lens']} az {spec['az']} deg off chord dep {spec['dep']} "
          f"dist {r_nom:.3f}"
          f"{' -> shortened to %.3f' % r_used if r_used < r_nom - 1e-6 else ''} "
          f"span {span_frac:.3f}  CLEAR")
    if not ONLY_BUILD:
        # Background census BEFORE rendering: if the shot is filled by a single untextured slab, an
        # authored light-blocker, or nothing at all, that must be known from the geometry rather than
        # discovered by the user looking at a bad picture.
        CENSUS_COLS, CENSUS_ROWS = 48, 27
        cen = {}
        ray_o = cam_obj.matrix_world.translation
        for cr in range(CENSUS_ROWS):
            for cc in range(CENSUS_COLS):
                pxc = (cc + 0.5) / CENSUS_COLS * RES_X
                pyc = (cr + 0.5) / CENSUS_ROWS * RES_Y
                xl = (pxc - RES_X / 2.0) / (spec["lens"] / 36.0 * RES_X)
                yl = (RES_Y / 2.0 - pyc) / (spec["lens"] / 36.0 * RES_X)
                dirn = (cam_obj.matrix_world.to_3x3() @ Vector((xl, yl, -1.0))).normalized()
                ok, loc, nrm, idx, obj, mat = scene.ray_cast(deps, ray_o, dirn, distance=200.0)
                cen[obj.name if ok else "<nothing>"] = cen.get(obj.name if ok else "<nothing>", 0) + 1
        tot_c = CENSUS_COLS * CENSUS_ROWS
        top = sorted(cen.items(), key=lambda kv: -kv[1])
        results["cameras"][key]["background_census"] = dict(top[:20])
        blockers = {k: v for k, v in cen.items() if k.startswith("light_blocker")}
        box_px = sum(v for k, v in cen.items() if k.startswith(("box", "trigger")))
        print(f"    background: {len(cen)} objects in frame; boxes+trigger occupy "
              f"{100.0 * box_px / tot_c:.1f}% of rays")
        for nm, cnt in top[:8]:
            print(f"      {100.0 * cnt / tot_c:6.2f}%  {nm}")
        if blockers:
            print(f"    !! light_blocker* visible: {blockers}")
        else:
            print("    light_blocker* visible: none")

        scene.render.filepath = str(OUT / f"candidate_{key}_start.png")
        # Write the report BEFORE rendering, so a long render that is interrupted still leaves the site,
        # camera and census measurements on disk. A previous run lost its whole log to buffering when the
        # 720p render was killed, which is exactly what this avoids.
        (OUT / "preview_build.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print("    report flushed before render", flush=True)
        bpy.ops.render.render(write_still=True)
        w = (OUT / f"candidate_{key}_start.png")
        ok_w = w.is_file()
        print(f"    rendered {w.name}: {'%.1f KB' % (w.stat().st_size / 1024) if ok_w else 'NOT WRITTEN'}",
              flush=True)
        if not ok_w:
            raise SystemExit(f"FATAL: {w} was not written")

(OUT / "preview_build.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

if SAVE_BLEND:
    # The active camera is whichever candidate was named in --cam_save, so the saved file renders the
    # approved view by default and the renderer's own camera block still overrides it explicitly.
    if CAM_SAVE:
        if CAM_SAVE[0] not in results["cameras"]:
            raise SystemExit(f"FATAL: --cam_save {CAM_SAVE[0]} was not built")
        cs = results["cameras"][CAM_SAVE[0]]
        if cs.get("status") != "CLEAR":
            raise SystemExit(f"FATAL: refusing to save a blend with camera status {cs.get('status')}")
        cam_obj.location = Vector(cs["eye"])
        cam_obj.rotation_mode = "QUATERNION"
        cam_obj.rotation_quaternion = (Vector(cs["aim"]) - Vector(cs["eye"])).normalized() \
            .to_track_quat("-Z", "Y")
        cam_obj.data.lens = cs["spec"]["lens"]
        scene.camera = cam_obj
        bpy.context.view_layer.update()
    # Compositing OFF is mandatory: the scene's own compositor renders a second volumetric Fog scene, which
    # exceeded 25 GB on a 15.7 GB machine and never produced a frame.
    scene.render.use_compositing = False
    p = Path(SAVE_BLEND).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(p), compress=True)
    results["saved_blend"] = {"path": str(p), "active_camera": CAM_SAVE[0] if CAM_SAVE else None,
                              "size_mb": round(p.stat().st_size / 1024 / 1024, 1)}
    (OUT / "preview_build.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"  saved runtime blend: {p}  ({results['saved_blend']['size_mb']} MB) "
          f"active camera {results['saved_blend']['active_camera']}")

print("")
print(f"  wrote preview_build.json  (mode {results['mode']})")
print("=" * 108)
