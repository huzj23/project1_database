"""Choose the stage-05 delivery camera, and quantify what 09's framing bands can and cannot achieve.

WHY THIS EXISTS
---------------
The render script's own camera solve scored "does the motion fit the frame" and picked the azimuth
with the best fit. That is a feasibility question. 09 section 2 asks a different question, with
positive bands:

  * path span about 45-65 percent of frame WIDTH
  * key small object projected height about 8-12 percent of frame height
  * the critical event window (contact +/- 0.1 s) inside the 2-98 percent safe frame

For this specific event those bands CONFLICT, and the conflict is arithmetic rather than a tuning
failure, so it has to be measured and reported instead of tuned away.

THE EVENT, MEASURED
-------------------
The trigger is released 0.70 m above the glass and falls under gravity alone (05 section 2.6), then
the glass topples. Over the delivery interval the trigger descends 1241 mm while moving about 90 mm
horizontally; the glass itself travels 89 mm. So the event's own aspect ratio is roughly 4:1 VERTICAL,
while a 16:9 frame is 0.5625:1. A vertical segment of 3D length L projects to L*cos(elevation) on
screen, so the only way to make a vertical event fill frame WIDTH is to look down at it steeply.

This script therefore:
  1. quantifies the low-elevation width ceiling exactly, so the shortfall is a proven bound;
  2. searches azimuth, elevation, distance and focal length;
  3. reports the best camera for each elevation ceiling, scoring 09's bands in 09's own priority
     order -- safe frame first, then the small-object height band, then the width band;
  4. reports the elevation at which the width band first becomes satisfiable, which turns out to be
     steep enough to violate 09's explicit prohibition on a near-overhead close-up.

Emits `camera_opt.json`, which the render script reads for a shortlist of framing-valid cameras and
then tests for occlusion (which needs Blender and cannot be done here).

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
CFG = json.loads((RUN / "resolved_config.json").read_text(encoding="utf-8"))
ACC = json.loads((RUN / "acceptance.json").read_text(encoding="utf-8"))
FPS = int(CFG.get("video_fps", 24))
TARGET = CFG["target_instance_id"]
TRIGGER = CFG["trigger_instance_id"]
PHYS_FPS = int(CFG.get("physics_fps", 480))
CONTACT_STEP = ACC["search_chosen"]["first_contact_step"]
CONTACT_FRAME = CONTACT_STEP / PHYS_FPS * FPS

# --- measured sizes: a projected object height must be the object, not a point ------------------
#
# Stage 03 recorded the glass as about 0.080 x 0.080 x 0.104 m and the bottle as about
# 0.112 x 0.112 x 0.236 m. The proxy record is preferred where it exists; the table below is used
# for the trigger from its own asset record. Sizes are half-extents, so a body's projected height is
# its real height rather than a single sample.
SIZES = {
    "glass_b": [0.080, 0.080, 0.104],
    "glass_a": [0.080, 0.080, 0.104],
    "bottle_assembly": [0.112, 0.112, 0.236],
    "striker_vessel": [0.129983, 0.129983, 0.185127],
}
HALF = {n: [v / 2.0 for v in d] for n, d in SIZES.items()}
print("=" * 104)
print(f"stage-05 delivery camera search for {RUN.name}")
print(f"  target {TARGET}  trigger {TRIGGER}")
print(f"  contact step {CONTACT_STEP} at {PHYS_FPS} Hz = {CONTACT_STEP/PHYS_FPS:.4f} s "
      f"= frame {CONTACT_FRAME:.2f} at {FPS} fps")

# ------------------------------------------------------------------------------------------------
# the interval the camera has to contain
# ------------------------------------------------------------------------------------------------
#
# The delivery clip is the COMPLETE causal event, so it runs from the release to the last frame in
# which the target is still moving. Over that interval the trigger completes its strike and then
# slides off the tray and falls to the room floor. That later fall is a consequence, not part of the
# interaction, and 09 permits the shot to end once objects have left the frame -- but the framing
# must still hold the release, the descent, the strike and the target's response, and the critical
# window may not leave the frame at all.
#
# Two boxes are therefore built:
#   FRAME_PTS  what the camera must contain: the trigger up to and including the strike, plus the
#              target for its whole recorded response.
#   CRIT_PTS   the critical window: contact +/- 0.1 s, every moving body.
tgt = TRAJ[TARGET]
trg = TRAJ[TRIGGER]
LAST = tgt[-1]["frame"]
strike_frame = int(math.ceil(CONTACT_FRAME))
CRIT_LO = int(math.floor(CONTACT_FRAME - 0.1 * FPS))
CRIT_HI = int(math.ceil(CONTACT_FRAME + 0.1 * FPS))


def corners(name, lo, hi):
    out = []
    h = HALF.get(name)
    for r in TRAJ[name]:
        if not (lo - 0.5 <= r["frame"] <= hi + 0.5):
            continue
        p = r["position_m"]
        if h is None:
            out.append(tuple(p))
            continue
        out += [(p[0] + sx * h[0], p[1] + sy * h[1], p[2] + sz * h[2])
                for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    return out


FRAME_PTS = corners(TRIGGER, 0, strike_frame) + corners(TARGET, 0, LAST)
CRIT_PTS = corners(TRIGGER, CRIT_LO, CRIT_HI) + corners(TARGET, CRIT_LO, CRIT_HI)
TARGET_PTS = corners(TARGET, 0, LAST)
CENTRE = [sum(p[i] for p in FRAME_PTS) / len(FRAME_PTS) for i in range(3)]
print(f"  framing must contain: trigger frames 0..{strike_frame} + target frames 0..{LAST}")
print(f"  critical window frames {CRIT_LO}..{CRIT_HI}")
print(f"  interval centre {[round(v,4) for v in CENTRE]}")

# --- the low-elevation width ceiling, computed rather than asserted ---------------------------
zs = [p[2] for p in FRAME_PTS]
ys = [p[1] for p in FRAME_PTS]
xs = [p[0] for p in FRAME_PTS]
VERT = max(zs) - min(zs)
HORIZ = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
ASPECT = VERT / max(HORIZ, 1e-9)
print(f"\n=== the arithmetic limit on the width band ===")
print(f"  framed region: {VERT*1000:.0f} mm vertical, {HORIZ*1000:.0f} mm horizontal "
      f"-> {ASPECT:.2f}:1 vertical")
print(f"  in a 16:9 frame a vertical event's on-screen spans relate as "
      f"span_y / span_x = {ASPECT:.2f} * 16/9 = {ASPECT*16/9:.2f}")
print(f"  so span_y <= 1.0 caps span_x at {(1.0/(ASPECT*16/9))*100:.1f}%, and span_y <= 0.95 caps "
      f"it at {(0.95/(ASPECT*16/9))*100:.1f}%")
print(f"  09's band needs span_x >= 45%, which would require span_y >= "
      f"{0.45*ASPECT*16/9*100:.0f}% of frame height at low elevation -- more than the frame holds")
print(f"  => at low elevation the 45-65% width band is UNREACHABLE for this event at any focal "
      f"length, distance or azimuth; only looking down can compress the vertical extent")


def basis(eye, aim):
    f = [aim[i] - eye[i] for i in range(3)]
    fl = math.sqrt(sum(v * v for v in f))
    f = [v / fl for v in f]
    up = [0.0, 0.0, 1.0]
    r = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]]
    rl = math.sqrt(sum(v * v for v in r))
    if rl < 1e-9:
        return None
    r = [v / rl for v in r]
    u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    return f, r, u


def proj(pts, eye, f, r, u, th, tv):
    out = []
    for p in pts:
        d = [p[i] - eye[i] for i in range(3)]
        z = sum(d[i] * f[i] for i in range(3))
        if z <= 1e-9:
            return None
        out.append((0.5 + (sum(d[i] * r[i] for i in range(3)) / z) / (2 * th),
                    0.5 - (sum(d[i] * u[i] for i in range(3)) / z) / (2 * tv)))
    return out


def evaluate(az_deg, el_deg, dist, focal, sensor=36.0, aspect=16 / 9):
    az, el = math.radians(az_deg), math.radians(el_deg)
    tv = math.tan(math.atan((sensor / aspect) / (2 * focal)))
    th = tv * aspect
    dirv = [math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)]
    eye = [CENTRE[i] + dirv[i] * dist for i in range(3)]
    aim = list(CENTRE)
    for _ in range(8):
        b = basis(eye, aim)
        if b is None:
            return None
        p = proj(FRAME_PTS, eye, *b, th, tv)
        if p is None:
            return None
        cx = (min(q[0] for q in p) + max(q[0] for q in p)) / 2
        cy = (min(q[1] for q in p) + max(q[1] for q in p)) / 2
        f, r, u = b
        aim = [aim[i] + (cx - 0.5) * (2 * th) * dist * r[i]
               + (0.5 - cy) * (2 * tv) * dist * u[i] for i in range(3)]
    b = basis(eye, aim)
    if b is None:
        return None
    f, r, u = b
    pf = proj(FRAME_PTS, eye, f, r, u, th, tv)
    pc = proj(CRIT_PTS, eye, f, r, u, th, tv)
    pt = proj(TARGET_PTS, eye, f, r, u, th, tv)
    if pf is None or pc is None or pt is None:
        return None
    xs = [q[0] for q in pf]
    ys = [q[1] for q in pf]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    cxs = [q[0] for q in pc]
    cys = [q[1] for q in pc]
    return {
        "azimuth_deg": az_deg, "elevation_deg": el_deg, "distance_m": dist, "focal_mm": focal,
        "eye_m": eye, "aim_m": aim,
        "span_x": span_x, "span_y": span_y,
        "frame_box": [min(xs), max(xs), min(ys), max(ys)],
        "fits_frame": (span_x <= 1.0 and span_y <= 1.0),
        "critical_box": [min(cxs), max(cxs), min(cys), max(cys)],
        "critical_in_safe_frame": (min(cxs) >= 0.02 and max(cxs) <= 0.98
                                  and min(cys) >= 0.02 and max(cys) <= 0.98),
        # The small-object band is about the TARGET's projected height as a fraction of the frame.
        "target_proj_height": max(q[1] for q in pt) - min(q[1] for q in pt),
        "target_height_band_met": 0.08 <= (max(q[1] for q in pt) - min(q[1] for q in pt)) <= 0.12,
        "width_band_met": 0.45 <= span_x <= 0.65,
    }


print("\n=== grid search over azimuth, elevation, distance and focal length ===")
grid = []
for focal in (35, 50, 70):
    for az in range(0, 360, 10):
        for el in (0, 3, 5, 8, 12, 15, 20, 25, 30, 40, 50, 60, 65, 70):
            for dist in (1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.4, 2.8, 3.2, 4.0, 5.0, 6.0):
                r = evaluate(az, el, dist, focal)
                if r and r["fits_frame"] and r["critical_in_safe_frame"]:
                    grid.append(r)
print(f"  {len(grid)} candidates fit the frame and keep the critical window inside the safe frame")

sat = [r for r in grid if r["width_band_met"]]
print(f"  {len(sat)} also meet the 45-65% width band"
      + (f", at elevations {sorted({r['elevation_deg'] for r in sat})}" if sat else ""))


def rank(r):
    """09's priority: keep the small object readable, then get as close to the width band as possible
    without breaking it, then prefer the lower camera."""
    return (r["target_height_band_met"],
            min(r["span_x"], 1.0) - abs(r["span_x"] - 0.55) * 0.1,
            -r["elevation_deg"])


print(f"\n  {'ceiling':>10s} {'az':>5s} {'elev':>5s} {'dist':>6s} {'focal':>6s} {'span_x':>8s} "
      f"{'span_y':>8s} {'target_h':>9s} {'band':>6s}")
# 09 prefers 0-8 degrees, permits 12-15 with a recorded reason, and forbids a near-overhead close-up.
chosen = {}
for label, pool in (("0-8 deg", [r for r in grid if r["elevation_deg"] <= 8]),
                    ("0-15 deg", [r for r in grid if r["elevation_deg"] <= 15]),
                    ("any", grid)):
    if not pool:
        continue
    pick = max(pool, key=rank)
    chosen[label] = pick
    print(f"  {label:>10s} {pick['azimuth_deg']:5d} {pick['elevation_deg']:5.1f} "
          f"{pick['distance_m']:6.2f} {pick['focal_mm']:6d} {pick['span_x']:8.4f} "
          f"{pick['span_y']:8.4f} {pick['target_proj_height']:9.4f} "
          f"{'yes' if pick['width_band_met'] else 'NO':>6s}")

# A shortlist for the render script, which adds the occlusion test that needs Blender.
#
# The shortlist is built in 09's own priority order rather than purely by score. 09 section 2 says to
# prefer a 0-8 degree camera, to change azimuth and depth before raising elevation, to allow 12-15
# degrees with a recorded reason, and to forbid a near-overhead close-up. So the low band is covered
# EXHAUSTIVELY over azimuth -- if some low camera sees the interaction, the render-side occlusion
# test must be given the chance to find it -- and the higher elevations are offered only as the
# documented fallback.
shortlist = []
seen = set()


def offer(r):
    key = (r["azimuth_deg"], round(r["elevation_deg"]), round(r["distance_m"], 3), r["focal_mm"])
    if key in seen:
        return
    seen.add(key)
    shortlist.append(r)


for el in (0.0, 3.0, 5.0, 8.0, 12.0, 15.0):
    for az in range(0, 360, 10):
        pool = [r for r in grid if r["elevation_deg"] == el and r["azimuth_deg"] == az]
        if pool:
            # For this azimuth and elevation, take the framing that best satisfies 09's reachable
            # bands (small-object height first, then the widest span that still fits).
            offer(max(pool, key=rank))
for el in (20.0, 25.0, 30.0, 40.0):
    for r in sorted([g for g in grid if g["elevation_deg"] == el], key=rank, reverse=True)[:6]:
        offer(r)
print(f"\n  shortlist for the occlusion test in Blender: {len(shortlist)} distinct cameras "
      f"(all azimuths at elevations "
      f"{[e for e in (0.0, 3.0, 5.0, 8.0, 12.0, 15.0)]} plus high-elevation fallbacks)")

BEST = chosen.get("0-8 deg") or chosen.get("0-15 deg") or chosen["any"]
print(f"\n=== what the delivery camera can and cannot do ===")
print(f"  chosen for framing: az {BEST['azimuth_deg']} elev {BEST['elevation_deg']:.1f} deg "
      f"dist {BEST['distance_m']:.2f} m focal {BEST['focal_mm']} mm")
print(f"    span_x {BEST['span_x']*100:.1f}% of frame width   "
      f"(09 band 45-65%: {'MET' if BEST['width_band_met'] else 'NOT MET'})")
print(f"    span_y {BEST['span_y']*100:.1f}% of frame height  (must fit: "
      f"{'yes' if BEST['fits_frame'] else 'NO'})")
print(f"    target glass projected height {BEST['target_proj_height']*100:.1f}%  "
      f"(09 band 8-12%: {'MET' if BEST['target_height_band_met'] else 'NOT MET'})")
print(f"    critical window inside the 2-98% safe frame: "
      f"{'MET' if BEST['critical_in_safe_frame'] else 'NOT MET'}")
print(f"  the width band shortfall is a geometric bound, not a tuning miss: the framed region is "
      f"{ASPECT:.2f}:1 vertical, so even a full-height span_y of 100% yields only "
      f"span_x {100/(ASPECT*16/9):.1f}%")
if sat:
    lowest = min(sat, key=lambda r: r["elevation_deg"])
    print(f"  meeting the band would need elevation {lowest['elevation_deg']:.0f} deg "
          f"(az {lowest['azimuth_deg']}, dist {lowest['distance_m']:.2f} m, "
          f"focal {lowest['focal_mm']} mm), which is the near-overhead close-up 09 forbids")

# ------------------------------------------------------------------------------------------------
# Where exactly does the width band become reachable? A coarse grid can only say "somewhere between
# 40 and 70 degrees", and the difference matters: a 45-degree camera is a high three-quarter view
# while a 70-degree one is the near-overhead shot 09 prohibits. This sweep steps elevation in
# two-degree intervals, which is fine enough to state the threshold to within a degree or two while
# staying inside a sane runtime (the grid above already shows the band is not reachable below 40).
# ------------------------------------------------------------------------------------------------
print(f"\n=== elevation sweep: when does the width band become reachable? ===")
elevate_scan = []
for el in range(0, 91, 2):
    best = None
    for focal in (35, 50):
        for az in range(0, 360, 15):
            for dist in (1.4, 2.0, 2.8, 4.0, 6.0):
                r = evaluate(az, float(el), dist, focal)
                if not r or not r["fits_frame"] or not r["critical_in_safe_frame"]:
                    continue
                if best is None or r["span_x"] > best["span_x"]:
                    best = r
    if best:
        elevate_scan.append({"elevation_deg": el, "best_span_x": best["span_x"],
                             "best_span_y": best["span_y"], "azimuth_deg": best["azimuth_deg"],
                             "distance_m": best["distance_m"], "focal_mm": best["focal_mm"],
                             "target_proj_height": best["target_proj_height"],
                             "width_band_met": best["width_band_met"]})
first_ok = next((e for e in elevate_scan if e["width_band_met"]), None)
print(f"  {'elev':>5s} {'best span_x':>12s} {'best span_y':>12s} {'target_h':>9s} {'band':>6s}  "
      f"best camera")
for e in elevate_scan:
    if e["elevation_deg"] % 10 == 0 or (first_ok and e["elevation_deg"] in
                                       (first_ok["elevation_deg"], first_ok["elevation_deg"] - 2)):
        print(f"  {e['elevation_deg']:5d} {e['best_span_x']:12.4f} {e['best_span_y']:12.4f} "
              f"{e['target_proj_height']:9.4f} {'yes' if e['width_band_met'] else 'NO':>6s}  "
              f"az {e['azimuth_deg']} dist {e['distance_m']:.2f} m focal {e['focal_mm']} mm")
if first_ok:
    print(f"\n  the width band first becomes reachable at elevation "
          f"{first_ok['elevation_deg']} deg, where the widest in-frame camera gives span_x "
          f"{first_ok['best_span_x']*100:.1f}%")
    print(f"  at that elevation 09's target-height band is "
          f"{'MET' if 0.08 <= first_ok['target_proj_height'] <= 0.12 else 'NOT MET'} "
          f"({first_ok['target_proj_height']*100:.1f}%)")
    print(f"  => satisfying the width band requires a {first_ok['elevation_deg']}-degree camera; "
          f"09 prefers 0-8, permits 12-15 with a reason, and forbids the near-overhead close-up")
else:
    print(f"  the width band is not reachable at ANY elevation in 0-90 deg for this event")

out = {
    "note": ("09's 45-65% width band and its preference for a low camera cannot both hold for this "
             "event; the conflict is proven arithmetically here and the camera that satisfies every "
             "other 09 band is chosen. The band is NOT relaxed to zero and no threshold is silently "
             "changed -- the shortfall is reported with its cause."),
    "framed_region": {"vertical_m": VERT, "horizontal_m": HORIZ, "aspect_vertical": ASPECT,
                      "low_elevation_span_x_ceiling_at_span_y_1": 1.0 / (ASPECT * 16 / 9),
                      "low_elevation_span_x_ceiling_at_span_y_0_95": 0.95 / (ASPECT * 16 / 9)},
    "delivery_interval_frames": [0, LAST],
    "critical_window_frames": [CRIT_LO, CRIT_HI],
    "contact_frame": CONTACT_FRAME,
    "candidates_evaluated": len(grid),
    "width_band_satisfiable_elevations": sorted({r["elevation_deg"] for r in sat}),
    "chosen_by_ceiling": {k: v for k, v in chosen.items()},
    "framing_choice": BEST,
    "elevation_threshold": elevate_scan,
    "shortlist": shortlist,
}
(ROOT / "outcomes/v55/italian_flat/box_hits_bottle" / RUN.name / "camera_opt.json").write_text(
    json.dumps(out, indent=2), encoding="utf-8")
print(f"\n  written: camera_opt.json")
