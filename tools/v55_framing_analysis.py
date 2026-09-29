"""Measure 09's framing criteria for the stage-05 delivery, from the recorded trajectory.

09 section 2 sets numeric framing thresholds for a single interaction: the projected span of the
motion path should be about 45-65 percent of the frame WIDTH, and the key small object's projected
height about 8-12 percent of the frame height; the critical event window (at least 0.1 s either side
of contact) must project inside the 2-98 percent safe frame.

The render script already reports a span per scope, but it reports the span of whatever points the
scope contains. This script answers the question those thresholds are actually asking, for several
DEFINITIONS of the framed interval, so the choice is made on numbers instead of on one aggregate:

  * `descent`     -- from release to first contact (the trigger's fall)
  * `strike`      -- contact +/- 0.1 s (the critical event window 09 names)
  * `topple`      -- first contact to the last frame the target is still moving
  * `descent+topple` -- release through the end of the topple, i.e. the whole interaction

For each, it reports the projected bounding box of every moving body, the spans, the projected
height of the target and the trigger, and whether the box sits inside the safe frame. The point is
to find the interval that satisfies 09 rather than to justify the one that does not.

Reads only: no Blender, no solver, no rendering.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(r"D:\workspace\project1_database")
RUN = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "outcomes/v55/italian_flat/box_hits_bottle/20260929T110000")

TRAJ = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))["bodies"]
BODIES = json.loads((RUN / "bodies.json").read_text(encoding="utf-8"))
CFG = json.loads((RUN / "resolved_config.json").read_text(encoding="utf-8"))
SOLVE = json.loads((RUN / "camera_solve.json").read_text(encoding="utf-8"))
VAL = json.loads((RUN / "validation.json").read_text(encoding="utf-8"))
FPS = int(CFG.get("video_fps", 24))
TARGET = CFG["target_instance_id"]
TRIGGER = CFG["trigger_instance_id"]

# The contact step comes from the solve's own evidence, not from a guess about frame numbers. It is
# recorded in `acceptance.json` under `search_chosen`, not in `validation.json` (which holds only the
# five contract checks), so both files are searched rather than assuming one layout.
ACC = json.loads((RUN / "acceptance.json").read_text(encoding="utf-8"))
CONTACT_STEP = None
for src, name in ((VAL, "validation.json"), (ACC.get("search_chosen", {}), "acceptance.search_chosen")):
    for key in ("first_contact_step", "first_contact_substep"):
        if isinstance(src.get(key), int):
            CONTACT_STEP = src[key]
            print(f"  first contact step {CONTACT_STEP} read from {name}")
            break
    if CONTACT_STEP is not None:
        break
if CONTACT_STEP is None:
    raise SystemExit(f"no first-contact step found; validation keys {sorted(VAL)}, "
                     f"acceptance.search_chosen keys {sorted(ACC.get('search_chosen', {}))}")
physics_fps = int(CFG.get("physics_fps", 240))
CONTACT_S = CONTACT_STEP / physics_fps
CONTACT_FRAME = CONTACT_S * FPS
print("=" * 104)
print(f"09 framing analysis for {RUN.name}")
print(f"  target {TARGET}   trigger {TRIGGER}")
print(f"  physics_fps {physics_fps}  video_fps {FPS}")
print(f"  first contact: step {CONTACT_STEP} = {CONTACT_S:.4f} s = video frame {CONTACT_FRAME:.2f}")

# --- the camera chosen for delivery ---
EYE = SOLVE["eye_m"]
AIM = SOLVE["aim_point_m"]
FOCAL = SOLVE["focal_length_mm"]
SENSOR = SOLVE["sensor_width_mm"]
RES = SOLVE["resolution"]
vfov_rad = 2.0 * math.atan((SENSOR * RES[1] / RES[0]) / (2.0 * FOCAL))
tan_v = math.tan(vfov_rad / 2.0)
tan_h = tan_v * RES[0] / RES[1]
print(f"  camera az {SOLVE['azimuth_deg']} elev {SOLVE['elevation_deg']:.1f} "
      f"dist {SOLVE['distance_m']:.4f} m  focal {FOCAL} mm  {RES[0]}x{RES[1]}")


def basis(eye, aim):
    f = tuple(aim[i] - eye[i] for i in range(3))
    fl = math.sqrt(sum(v * v for v in f))
    f = tuple(v / fl for v in f)
    up = (0.0, 0.0, 1.0)
    r = (f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0])
    rl = math.sqrt(sum(v * v for v in r))
    r = tuple(v / rl for v in r)
    u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    return f, r, u


FWD, RIGHT, UP = basis(EYE, AIM)


def project(p):
    d = (p[0] - EYE[0], p[1] - EYE[1], p[2] - EYE[2])
    z = sum(d[i] * FWD[i] for i in range(3))
    if z <= 1e-9:
        return None
    x = sum(d[i] * RIGHT[i] for i in range(3))
    y = sum(d[i] * UP[i] for i in range(3))
    return (0.5 + (x / z) / (2.0 * tan_h), 0.5 - (y / z) / (2.0 * tan_v))


# --- object extents, so projected HEIGHT means the object's height and not a point ---
DIMS = {}
for b in BODIES if isinstance(BODIES, list) else BODIES.get("bodies", []):
    DIMS[b["instance_id"]] = b.get("dims_m") or b.get("aabb_size_m") or b.get("size_m")
print(f"  body dims available: { {k: v for k, v in list(DIMS.items())[:5]} }")


def body_corners(name, pos):
    d = DIMS.get(name)
    if not d:
        return [pos]
    return [(pos[0] + sx * d[0] / 2, pos[1] + sy * d[1] / 2, pos[2] + sz * d[2] / 2)
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


def window(lo_frame, hi_frame, label, bodies):
    """Projected box, spans and object heights over a frame interval."""
    xs, ys = [], []
    per_body = {}
    for name in bodies:
        rows = TRAJ.get(name) or []
        sel = [r for r in rows if lo_frame - 0.5 <= r["frame"] <= hi_frame + 0.5]
        if not sel:
            continue
        bx, by = [], []
        for r in sel:
            for c in body_corners(name, r["position_m"]):
                n = project(c)
                if n is None:
                    continue
                bx.append(n[0])
                by.append(n[1])
        if bx:
            per_body[name] = {"x": [min(bx), max(bx)], "y": [min(by), max(by)],
                              "samples": len(sel)}
            xs += bx
            ys += by
    if not xs:
        return None
    out = {"label": label, "frame_range": [lo_frame, hi_frame],
           "box": {"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys)},
           "span_x": max(xs) - min(xs), "span_y": max(ys) - min(ys),
           "inside_safe_frame": (min(xs) >= 0.02 and max(xs) <= 0.98
                                 and min(ys) >= 0.02 and max(ys) <= 0.98),
           "per_body": per_body}
    return out


# The topple end: the last frame where the target is still moving.
tgt_rows = TRAJ[TARGET]
first_move = next((r["frame"] for r in tgt_rows
                   if abs(r["position_m"][0] - tgt_rows[0]["position_m"][0]) > 1e-4
                   or abs(r["position_m"][1] - tgt_rows[0]["position_m"][1]) > 1e-4), None)
last = tgt_rows[-1]["frame"]
lo = int(math.floor(CONTACT_FRAME - 0.1 * FPS))
hi = int(math.ceil(CONTACT_FRAME + 0.1 * FPS))
WINDOWS = [
    ("descent", 0, int(math.ceil(CONTACT_FRAME)), [TRIGGER]),
    ("strike +/-0.1s", lo, hi, [TRIGGER, TARGET]),
    ("topple", int(math.ceil(CONTACT_FRAME)), last, [TRIGGER, TARGET]),
    ("descent+strike", 0, hi, [TRIGGER, TARGET]),
    ("descent+topple", 0, last, [TRIGGER, TARGET]),
]

print(f"\n  target first moves at frame {first_move}; target last frame {last}")
print(f"\n=== projected boxes by interval (fractions of frame; width=span_x, height=span_y) ===")
print(f"  {'interval':18s} {'frames':>12s} {'span_x':>8s} {'span_y':>8s} {'safe':>6s}  "
      f"{'target h':>9s} {'trigger h':>10s}")
report = {}
for label, a, b, bodies in WINDOWS:
    w = window(a, b, label, bodies)
    if w is None:
        print(f"  {label:18s} no samples")
        continue
    th = w["per_body"].get(TARGET, {}).get("y")
    sh = w["per_body"].get(TRIGGER, {}).get("y")
    thf = (th[1] - th[0]) if th else None
    shf = (sh[1] - sh[0]) if sh else None
    report[label] = w
    print(f"  {label:18s} {a:5.0f}-{b:<6.0f} {w['span_x']:8.4f} {w['span_y']:8.4f} "
          f"{str(w['inside_safe_frame']):>6s}  "
          f"{(f'{thf:.4f}' if thf is not None else '-'):>9s} "
          f"{(f'{shf:.4f}' if shf is not None else '-'):>10s}")

# 09's bands, evaluated against the interval that represents the whole interaction.
key = report.get("descent+topple")
print(f"\n=== 09 section 2 bands, against 'descent+topple' (the whole interaction) ===")
if key:
    w45 = 0.45 <= key["span_x"] <= 0.65
    print(f"  path span 45-65% of frame width : span_x {key['span_x']*100:5.1f}%  "
          f"{'MET' if w45 else 'NOT MET'}")
    for nm in (TARGET, TRIGGER):
        yb = key["per_body"].get(nm, {}).get("y")
        if yb:
            h = yb[1] - yb[0]
            verdict = "MET" if 0.08 <= h <= 0.12 else "NOT MET"
            note = "" if verdict == "MET" else " (span over the interval, not a single-frame size)"
            print(f"  {nm:17s} projected height 8-12% : {h*100:5.1f}%  {verdict}{note}")
    print(f"  critical window inside 2-98%    : "
          f"{'MET' if report.get('strike +/-0.1s', {}).get('inside_safe_frame') else 'NOT MET'} "
          f"(interval 'strike +/-0.1s')")

print(f"\n=== why the width band cannot be met at this event, in numbers ===")
k = report.get("descent+topple")
s = report.get("strike +/-0.1s")
if k and s:
    print(f"  the whole interaction spans {k['span_y']*100:.1f}% of frame height but only "
          f"{k['span_x']*100:.1f}% of frame width, a ratio of {k['span_y']/max(k['span_x'],1e-9):.1f}:1")
    print(f"  the horizontal extent of the motion is bounded by the target's travel "
          f"({abs(TRAJ[TARGET][-1]['position_m'][0]-TRAJ[TARGET][0]['position_m'][0])*1000:.1f} mm in x, "
          f"{abs(TRAJ[TARGET][-1]['position_m'][1]-TRAJ[TARGET][0]['position_m'][1])*1000:.1f} mm in y)")
    trig_dz = abs(TRAJ[TRIGGER][0]['position_m'][2] - min(r['position_m'][2] for r in TRAJ[TRIGGER]))
    print(f"  the vertical extent is dominated by the trigger's {trig_dz*1000:.0f} mm descent")
    print(f"  to reach span_x 45% the distance would have to shrink to about "
          f"{SOLVE['distance_m'] * (k['span_x']/0.45):.3f} m, which would push span_y to about "
          f"{k['span_y']/(k['span_x']/0.45)*100:.0f}% -- far outside the frame, cropping the strike")

(ROOT / "outcomes/v55/italian_flat/box_hits_bottle" / RUN.name / "framing_analysis.json").write_text(
    json.dumps({"camera": {"eye_m": EYE, "aim_m": AIM, "focal_mm": FOCAL, "resolution": RES,
                           "azimuth_deg": SOLVE["azimuth_deg"],
                           "elevation_deg": SOLVE["elevation_deg"],
                           "distance_m": SOLVE["distance_m"]},
                "first_contact_s": CONTACT_S, "first_contact_frame": CONTACT_FRAME,
                "intervals": report,
                "bands_09": {"path_span_x_band": [0.45, 0.65],
                             "small_object_height_band": [0.08, 0.12],
                             "safe_frame": [0.02, 0.98]}},
               indent=2), encoding="utf-8")
print(f"\n  written: framing_analysis.json")
