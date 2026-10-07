"""V6.5 GATE 4 (r4) -- camera path with aim damping AND an occlusion-avoiding lateral search.

WHAT THE PREVIOUS REVISIONS GOT WRONG
-------------------------------------
r1 read `rayTest`'s no-hit sentinel (-1) as a hit body, so it reported "occluded by dynamic -1" at 12 of 13 anchors,
while its own per-frame sweep reported zero blocked frames -- two halves of one script disagreeing, which is what
exposed it. r1 also built its frustum test from a copy of the look vector, making `arccos(1) = 0` for every subject,
so `in_frame` was always true and carried no information.

r2 fixed both, but damped only the camera POSITION, not its AIM. The anchor table switches subject at each event, so
the look-at point TELEPORTED at those instants: measured single-frame rotations of 82.3 deg (frame 61) and 41.4 deg
(frame 125), equivalent to whole-image displacements of ~2395 px and ~1205 px. The position curve looked perfectly
smooth throughout, which is exactly why the defect was invisible in the motion report and only appeared when the
angular rate was measured separately (`check_camera_rate.py`). r3 damped the aim, cutting the maximum to 7.37 deg.

WHAT r4 ADDS, AND WHY
---------------------
r3's own per-frame sweep found **23 frames whose sight line is blocked**, all in one window (t = 1.63-2.04 s) by
`outdoor_table_chair_set_01_chair_02.001`. A static chair standing between the lens and the subject is not a cosmetic
issue: gate 4 asks for a subject readable on consecutive frames, and for 0.96 s of a 9 s shot the subject is behind a
chair. Reporting it was right; leaving it unaddressed when it is fixable would not be.

The fix searches, for each blocked frame, a small set of alternative lateral offsets and heights around the nominal
camera position and takes the first that (a) clears the sight line with a ray test and (b) keeps the subject inside the
frame with enough pixel coverage. Candidates are ordered by distance from the nominal position, so the chosen path
stays as close to the authored one as the geometry allows. The correction is then smoothed, because a camera that
jumps sideways for one frame and back would trade a blocked subject for a visible jolt.

Every claim below is measured on the resulting path, and the frames that remain blocked are listed individually rather
than summarised as a count.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/data/raw/huzijian/project1_database/tools/v64")
import physics_common_r10 as pc

ap = argparse.ArgumentParser()
ap.add_argument("--events", required=True)
ap.add_argument("--trajectory", required=True)
ap.add_argument("--layout", default="/data/raw/huzijian/project1_database/tmp/v64_node12/"
                                    "layout_v65_tailwest_candidate_b.json")
ap.add_argument("--out", required=True)
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--sim-s", type=float, default=9.0)
ap.add_argument("--res-x", type=int, default=1280)
ap.add_argument("--res-y", type=int, default=720)
ap.add_argument("--fov-deg", type=float, default=42.0)
ap.add_argument("--lead-s", type=float, default=0.25)
ap.add_argument("--side-offset", type=float, default=0.90,
                help="lateral standoff; 0.90 m at height 0.70 m measured as the clearest close standoff")
ap.add_argument("--side-sign", type=int, default=-1, choices=(1, -1),
                help="which side of the chain the camera stands on; the sweep found side +1 blocked on 41 frames "
                     "by a chair where side -1 was clear")
ap.add_argument("--height", type=float, default=0.70,
                help="camera height above the subject; from the standoff sweep, which found that a low standoff "
                     "grazes the table rim and puts the table edge across the sight line to pieces lying on it")
ap.add_argument("--look-height", type=float, default=0.10)
ap.add_argument("--damp-tau", type=float, default=0.22)
ap.add_argument("--aim-tau", type=float, default=0.40,
                help="retained for reference only; r12 uses --max-aim-deg instead")
ap.add_argument("--max-aim-deg", type=float, default=12.0,
                help="backstop limit on aim rotation per frame. r12 set this to 3.0 and the aim fell permanently "
                     "behind the subject; the continuous blended target needs far less than this")
ap.add_argument("--blend-lift", type=float, default=0.10,
                help="metres to raise the aim at the midpoint between two anchors, so the blend between subjects "
                     "passes above the clutter it crosses instead of grazing it")
ap.add_argument("--max-speed", type=float, default=1.6)
ap.add_argument("--min-subject-px", type=float, default=50.0)
args = ap.parse_args()

OUT = Path(args.out) if args.out.startswith("/") else pc.ROOT / args.out
OUT.mkdir(parents=True, exist_ok=True)

manifest = json.loads(pc.DEFAULT_MANIFEST.read_text())
layout = json.loads(open(args.layout, encoding="utf-8").read())
order = [r["id"] for r in layout["objects"]]
P = {r["id"]: np.array(r["settled_position"], dtype=float) for r in layout["objects"]}
D = {o: np.array(manifest["objects"][o]["dims_m"], dtype=float) for o in order}
events = json.loads(open(args.events, encoding="utf-8").read())
rows = {r["piece"]: r for r in events["rows"]}
traj = np.load(args.trajectory)
T = traj["t"]
SOL_HZ = 1.0 / float(T[1] - T[0])

fps = args.fps
n_frames = int(round(args.sim_s * fps))
ft = np.arange(n_frames) / fps
focal_px = (args.res_y / 2.0) / np.tan(np.radians(args.fov_deg) / 2.0)

print("=" * 112, flush=True)
print("V6.5 GATE 4 (r9) -- aim computed FIRST, so the occlusion test and the render use the same ray", flush=True)
print(f"  {args.res_x}x{args.res_y} @ {fps} fps  fov {args.fov_deg} deg  pose tau {args.damp_tau} s  "
      f"max aim {args.max_aim_deg} deg/frame (backstop)  camera speed cap {args.max_speed} m/s", flush=True)
print(f"  trajectory {len(T)} samples at {SOL_HZ:.1f} Hz covering {T[-1]:.4f} s; film is {n_frames / fps:.3f} s",
      flush=True)
print("=" * 112, flush=True)

if n_frames / fps > T[-1] + 1e-9:
    raise RuntimeError("the film is longer than the simulation")
# the pose lookup uses the SOLVER's clock. Getting this wrong is what made an earlier revision render an 80x
# slow-motion of the first 0.11 s while its camera swept the whole path, so it is asserted here too.
assert abs(round(ft[-1] * SOL_HZ) - round((n_frames - 1) / fps * SOL_HZ)) == 0


def pos_at(name, t):
    i = int(np.clip(round(t * SOL_HZ), 0, len(T) - 1))
    return traj[f"pos_{name}"][i].astype(float)


def first_t(pid):
    return (rows.get(pid, {}).get("first_dynamic") or {}).get("t")


# ------------------------------------------------------------------ anchors from the real events
anchors = []


def add(t, subject, why):
    anchors.append({"t": round(float(max(0.0, t)), 4), "subject": subject, "why": why})


add(0.0, "B", "the pitch: B in flight toward the radio")
if events.get("t_B_A") is not None:
    add(events["t_B_A"] - 0.12, "A", "B strikes the radio case")
if events.get("t_A_R") is not None:
    add(events["t_A_R"] - 0.10, "R", "A pushes R; the receiving contact face")
t = first_t("F01")
if t is not None:
    add(t - 0.06, "F01", "R lands on F01: the chain entry")
turns = []
for i in range(1, len(order) - 1):
    a, b, c = P[order[i - 1]][:2], P[order[i]][:2], P[order[i + 1]][:2]
    u, v = b - a, c - b
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu < 1e-9 or nv < 1e-9:
        continue
    turns.append((float(np.degrees(np.arccos(np.clip((u / nu) @ (v / nv), -1, 1)))), order[i], i))
turns.sort(reverse=True)
picked = []
for ang, pid, i in turns:
    if ang < 12 or any(abs(i - j) <= 4 for j in picked):
        continue
    picked.append(i)
    tt = first_t(pid)
    if tt is not None:
        add(tt - args.lead_s, pid, f"bend ({ang:.0f} deg at {pid})")
    if len(picked) == 2:
        break
for pid in ("F22", "F23"):
    tt = first_t(pid)
    if tt is not None:
        add(tt - args.lead_s, pid, "the repaired tape ring takes the relay")
for pid in ("F45", "F46", "F47", "F48"):
    tt = first_t(pid)
    if tt is not None:
        add(tt - args.lead_s, pid, "the re-laid tail (V6.5 placement)")
anchors.sort(key=lambda a: a["t"])
dedup = []
for a in anchors:
    if dedup and abs(a["t"] - dedup[-1]["t"]) < 1.0 / fps:
        continue
    dedup.append(a)
anchors = dedup

print(f"\n  {len(anchors)} anchors (deduplicated on time):", flush=True)
for a in anchors:
    print(f"    t={a['t']:6.3f}s  {a['subject']:<5} {a['why']}", flush=True)

# ------------------------------------------------------------------ world and geometry helpers
w = pc.World(hz=960, mode="upstream", verbose=False, layout_override=args.layout)
static_names = {b: w.body_names.get(b, "?") for b in w._static}
dyn_ids = set(w.actors.values())


def lateral_of(subject):
    """Side direction (unit, horizontal) for a subject, from its neighbours along the chain.

    Multiplied by `--side-sign`. WHICH SIDE THE CAMERA STANDS ON IS NOT COSMETIC: `probe_camera_standoff.py` swept both
    sides on the real world and found the chain has a clear side and a furniture side. At height 1.10 m and 1.20 m out,
    side +1 is blocked on 41 frames by `outdoor_table_chair_set_01_chair_02.001` while side -1 is blocked on **none**.
    The earlier scripts had no way to express this and instead tried to repair the blocked frames one at a time.
    """
    i = order.index(subject) if subject in order else None
    if i is None:
        return np.array([0.0, args.side_sign])
    a, b = P[order[max(i - 1, 0)]], P[order[min(i + 1, len(order) - 1)]]
    u = (b - a)[:2]
    u = u / (np.linalg.norm(u) + 1e-12)
    return np.array([-u[1], u[0]]) * args.side_sign


def ray_blocked(cam, target, subject):
    hit = pc.p.rayTest(cam.tolist(), target.tolist(), physicsClientId=w.cid)[0]
    hb = hit[0]
    if hb is None or hb == -1:
        return None
    if hb == w.actors.get(subject) or hb in dyn_ids:
        return None
    return static_names.get(hb, str(hb))


def off_axis(subject, s, cam):
    target = s + np.array([0, 0, args.look_height])
    d = target - cam
    look = d / (np.linalg.norm(d) + 1e-12)
    half = D[subject] / 2 if subject in D else np.array([.05, .05, .05])
    worst = 0.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                c = s + half * np.array([sx, sy, sz])
                dc = c - cam
                dc = dc / (np.linalg.norm(dc) + 1e-12)
                worst = max(worst, float(np.degrees(np.arccos(np.clip(dc @ look, -1, 1)))))
    return worst


def anchor_at(t):
    best = None
    for c in anchors:
        if c["t"] <= t + 1e-9:
            best = c
        else:
            break
    return best or anchors[0]


# ------------------------------------------------------------------ nominal camera per frame
raw_cam = np.empty((n_frames, 3))
frame_subject = []
nominal_blocker = {}
for k in range(n_frames):
    a = anchor_at(ft[k])
    s = pos_at(a["subject"], ft[k])
    lat = lateral_of(a["subject"])
    raw_cam[k] = s + np.array([lat[0] * args.side_offset, lat[1] * args.side_offset, args.height])
    frame_subject.append(a["subject"])

# ------------------------------------------------------------------ occlusion-avoiding search
# ordered outward from the nominal position: first a change of lateral distance, then a change of height, then both.
CANDIDATES = []
for dlat in (0.0, 0.25, -0.25, 0.5, -0.5, 0.75, -0.75, 1.0, -1.0):
    for dh in (0.0, 0.15, 0.3, -0.15, 0.45, -0.3):
        CANDIDATES.append((dlat, dh))
CANDIDATES.sort(key=lambda c: abs(c[0]) + abs(c[1]))  # nearest-first, so the path stays near the authored one


def try_clear(base_cam, subj, s, aim):
    """First candidate offset around `base_cam` that clears the ACTUAL aimed ray and keeps `subj` framed.

    `aim` is passed in rather than recomputed from `s`, because the aim is damped and therefore lags the subject: a
    ray to the raw subject position is a different ray from the one the camera will render, and testing the wrong one
    is what let 12 frames remain blocked in r6 while the search believed it had cleared them.
    """
    lat = lateral_of(subj)
    for dlat, dh in CANDIDATES:
        cam = base_cam + np.array([lat[0] * dlat, lat[1] * dlat, dh])
        cam[2] = max(cam[2], 0.25)
        if ray_blocked(cam, aim, subj) is not None:
            continue
        if off_axis(subj, s, cam) >= args.fov_deg / 2.0:
            continue
        return cam, dlat, dh
    return None, None, None


alpha = 1.0 - np.exp(-1.0 / (args.damp_tau * fps))


def damp(desired):
    """Speed-capped damped follow toward `desired`. This IS the smoother, and it never zero-pads."""
    out = np.empty((n_frames, 3))
    out[0] = desired[0]
    for k in range(1, n_frames):
        step = alpha * (desired[k] - out[k - 1])
        nstep = np.linalg.norm(step)
        if nstep > args.max_speed / fps:
            step *= (args.max_speed / fps) / nstep
        out[k] = out[k - 1] + step
    out[:, 2] = np.maximum(out[:, 2], 0.20)
    return out


# THE AIM, AND THE DEFECT r12 FIXES
# ---------------------------------
# The aim is a damped function of the subject's trajectory alone -- it does not depend on where the camera is -- so it
# is computed FIRST and every occlusion test afterwards uses that exact ray.
#
# r9 (this file's parent) used a plain first-order lag on the aim and then MEASURED the result: `check_in_frame.py`
# projected the authored path and found that on **5 of 216 frames the followed subject is OUTSIDE the 1280x720 frame**
# entirely -- frames 15-18 (the chain entry, subject F04 then F01) and frame 62 (the tape-ring relay, F22). Those are
# not incidental frames: frames 15-18 are where the chain starts, so the moment the piece in the film's whole premise
# is the payoff is off-screen. The cause is a first-order lag behaves badly across a STEP: at an anchor switch the aim
# has to travel from the old subject to the new one, and a lag covers most of that distance in the first couple of
# frames, swinging the frame through the gap. r9's aim reached 11.66 deg/frame, which at this focal length is a 340 px
# whole-image displacement.
#
# r13 FIXES THE DISCONTINUITY AT ITS SOURCE INSTEAD OF THROTTLING IT
# ------------------------------------------------------------------
# r9 lagged the aim and the subject left the frame on 5 frames. r12 then rate-limited the aim to 3 deg/frame, and that
# was WORSE in a different way: constrained to 3 deg/frame the aim could not keep up with an ordinary event, so it fell
# permanently behind the subject and ended with 5 blocked frames and 14 frames where the subject's upright height was
# under 50 px. Throttling a discontinuous input just makes it late.
#
# The input is discontinuous because `pos_at(frame_subject[k], ...)` SWITCHES subject at each anchor: at frame k the
# target jumps from R's position to F01's, which can be metres apart. Every previous revision inherited that step and
# then tried to soften its consequences.
#
# r13 instead makes the TARGET continuous. The look-at point is a BLEND of the previous anchor's subject and the new
# one, weighted by how far the film has progressed between the two anchors' times, so the aim's target travels smoothly
# along the chain from one subject to the next over the whole interval rather than teleporting at the boundary. There is
# then no step to lag or to rate-limit, and the aim tracks it with a plain damped follow.
raw_look = np.stack([pos_at(frame_subject[k], ft[k]) + np.array([0, 0, args.look_height])
                     for k in range(n_frames)])

# blended target: at time t, mix the subject of the anchor before t with the subject of the anchor after t
blended_look = np.empty((n_frames, 3))
for k in range(n_frames):
    t = ft[k]
    prev_a, next_a = anchors[0], None
    for a in anchors:
        if a["t"] <= t + 1e-9:
            prev_a = a
        else:
            next_a = a
            break
    if next_a is None:
        blended_look[k] = pos_at(prev_a["subject"], t) + np.array([0, 0, args.look_height])
        continue
    span = max(next_a["t"] - prev_a["t"], 1e-6)
    u = float(np.clip((t - prev_a["t"]) / span, 0.0, 1.0))
    # smoothstep: zero derivative at both ends, so the target has no corner at an anchor boundary either
    uu = u * u * (3.0 - 2.0 * u)
    p_prev = pos_at(prev_a["subject"], t)
    p_next = pos_at(next_a["subject"], t)
    blended_look[k] = (1.0 - uu) * p_prev + uu * p_next + np.array([0, 0, args.look_height])
    # the blend can pass through the gap between two pieces, so the look HEIGHT is raised where the blend is between
    # subjects, keeping the aim above the clutter it crosses
    blended_look[k, 2] += args.blend_lift * (1.0 - abs(2.0 * uu - 1.0))

# how discontinuous was each aim target? this is the number that decides whether a lag or a rate limit is needed at all
tgt_jump = np.linalg.norm(np.diff(raw_look, axis=0), axis=1)
bl_jump = np.linalg.norm(np.diff(blended_look, axis=0), axis=1)
print(f"\n  aim target step per frame: raw (subject-switching) max {tgt_jump.max():.4f} m, "
      f"blended (continuous) max {bl_jump.max():.4f} m", flush=True)
print(f"  raw target steps over 0.10 m: {int((tgt_jump > 0.10).sum())}   "
      f"blended: {int((bl_jump > 0.10).sum())}", flush=True)


def aim_path(cam):
    """Damped follow of the CONTINUOUS blended target, then a generous safety rate limit.

    The damping is kept because it gives the aim inertia, which reads as a real operator panning; the rate limit is
    kept only as a backstop against a genuinely impossible demand, and is set well above what this target requires.
    """
    la = 1.0 - np.exp(-1.0 / (args.aim_tau * fps))
    out = np.empty((n_frames, 3))
    out[0] = blended_look[0]
    for k in range(1, n_frames):
        out[k] = out[k - 1] + la * (blended_look[k] - out[k - 1])
    # backstop in angle, generous by default
    for k in range(1, n_frames):
        d_cur = out[k] - cam[k]
        d_prev = out[k - 1] - cam[k - 1]
        nc, npv = np.linalg.norm(d_cur), np.linalg.norm(d_prev)
        if nc < 1e-9 or npv < 1e-9:
            continue
        c = float(np.clip((d_cur / nc) @ (d_prev / npv), -1.0, 1.0))
        ang = np.degrees(np.arccos(c))
        if ang > args.max_aim_deg:
            perp = (d_cur / nc) - c * (d_prev / npv)
            nperp = np.linalg.norm(perp)
            if nperp > 1e-12:
                new_dir = (np.cos(np.radians(args.max_aim_deg)) * (d_prev / npv)
                           + np.sin(np.radians(args.max_aim_deg)) * (perp / nperp))
                out[k] = cam[k] + new_dir * nc
    return out


def blocked_at(cam, k):
    """The ray this camera will ACTUALLY render -- to the rate-limited aim -- versus the static world."""
    return ray_blocked(cam, look_xyz[k], frame_subject[k])


desired = raw_cam.copy()
cam_xyz = damp(desired)
look_xyz = aim_path(cam_xyz)
blocked_nominal = sum(1 for k in range(n_frames) if blocked_at(cam_xyz[k], k) is not None)
print(f"\n  blocked frames on the damped nominal path: {blocked_nominal} of {n_frames}", flush=True)

WINDOW = 4
passes = []
for pass_i in range(12):
    blocked = [k for k in range(n_frames) if blocked_at(cam_xyz[k], k) is not None]
    passes.append(len(blocked))
    print(f"  pass {pass_i}: {len(blocked)} of {n_frames} frames blocked", flush=True)
    if not blocked:
        break
    for k in blocked:
        subj = frame_subject[k]
        s = pos_at(subj, ft[k])
        cam, dlat, dh = try_clear(cam_xyz[k], subj, s, look_xyz[k])
        if cam is None:
            continue
        delta = cam - cam_xyz[k]
        for j in range(max(0, k - WINDOW), min(n_frames, k + WINDOW + 1)):
            # the taper weight must NOT be called `w`: that name is the pybullet World handle in this module, and
            # rebinding it here crashed the next ray_blocked() call with "'float' object has no attribute 'cid'".
            taper = 1.0 - abs(j - k) / (WINDOW + 1.0)
            desired[j] = desired[j] + delta * taper
    cam_xyz = damp(desired)
    # the aim is a function of the camera position, so it MUST be recomputed whenever the camera moves; reusing the
    # old aim here would test one ray and render another, which is the error that cost every earlier revision
    look_xyz = aim_path(cam_xyz)

dd = look_xyz - cam_xyz
dist = np.linalg.norm(dd, axis=1, keepdims=True)
close = (dist < 0.35).ravel()
if close.any():
    ahead = dd / np.where(dist < 1e-9, 1.0, dist)
    look_xyz[close] = cam_xyz[close] + ahead[close] * 0.35

# ------------------------------------------------------------------ measurements on the FINAL path
vel = np.diff(cam_xyz, axis=0) * fps
speed = np.linalg.norm(vel, axis=1)
accel = np.diff(vel, axis=0) * fps
aim = look_xyz - cam_xyz
aim /= np.linalg.norm(aim, axis=1, keepdims=True)
ang = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", aim[:-1], aim[1:]), -1.0, 1.0)))
print(f"\n  camera position: speed {speed.min():.3f}..{speed.max():.3f} m/s (cap {args.max_speed}), "
      f"max |accel| {np.abs(accel).max():.2f} m/s^2, max per-frame move "
      f"{np.linalg.norm(np.diff(cam_xyz, axis=0), axis=1).max():.4f} m", flush=True)
print(f"  camera AIM rotation: mean {ang.mean():.3f} deg/frame, max {ang.max():.3f} deg/frame "
      f"({ang.mean() * fps:.2f} deg/s mean)", flush=True)
print(f"    frames over 1 deg {int((ang > 1).sum())}, over 2 deg {int((ang > 2).sum())}, "
      f"over 5 deg {int((ang > 5).sum())}", flush=True)

final_blocked = []
for k in range(n_frames):
    subj = frame_subject[k]
    b = ray_blocked(cam_xyz[k], look_xyz[k], subj)
    if b is not None:
        final_blocked.append({"frame": k, "t": round(float(ft[k]), 4), "subject": subj, "blocked_by": b})
print(f"  AFTER the correction, frames still blocked by a static body: {len(final_blocked)}", flush=True)
for e in final_blocked[:12]:
    print(f"    frame {e['frame']:4d} t={e['t']:6.3f}s {e['subject']} behind {e['blocked_by']}", flush=True)

# pixel coverage, largest and smallest subject dimension reported separately
px_rows = []
for k in range(n_frames):
    subj = frame_subject[k]
    dist_m = float(np.linalg.norm(look_xyz[k] - cam_xyz[k]))
    if subj in D:
        pl = focal_px * float(max(D[subj][1], D[subj][2])) / max(dist_m, 1e-6)
        ps = focal_px * float(D[subj][0]) / max(dist_m, 1e-6)
        ph = focal_px * float(D[subj][2]) / max(dist_m, 1e-6)
    else:
        pl = ps = ph = focal_px * 0.15 / max(dist_m, 1e-6)
    px_rows.append({"frame": k, "t": round(float(ft[k]), 4), "subject": subj,
                    "px_large": round(float(pl), 1), "px_small": round(float(ps), 1), "px_height": round(float(ph), 1),
                    "dist_m": round(dist_m, 4)})
below_large = [p for p in px_rows if p["px_large"] < args.min_subject_px]
below_height = [p for p in px_rows if p["px_height"] < args.min_subject_px]
print(f"\n  pixel coverage over {n_frames} frames at {args.res_x}x{args.res_y}:", flush=True)
print(f"    subject's LARGEST dimension below {args.min_subject_px} px: {len(below_large)} frames", flush=True)
print(f"    subject's UPRIGHT HEIGHT below {args.min_subject_px} px:   {len(below_height)} frames", flush=True)
for p in px_rows[::max(1, n_frames // 12)]:
    print(f"      t={p['t']:6.3f}s {p['subject']:<5} large {p['px_large']:7.1f}  height {p['px_height']:7.1f}  "
          f"thickness {p['px_small']:6.1f}  at {p['dist_m']:.3f} m", flush=True)

payload = {
    "res": [args.res_x, args.res_y], "fps": fps, "fov_deg": args.fov_deg, "n_frames": n_frames,
    "sim_s": args.sim_s, "damp_tau": args.damp_tau, "max_aim_deg": args.max_aim_deg, "max_speed_cap": args.max_speed,
    "sol_hz": SOL_HZ,
    "anchors": [{**a, "cam": [round(float(x), 5) for x in raw_cam[anchors.index(a)]]} for a in anchors],
    "camera_xyz": [[round(float(v), 6) for v in r] for r in cam_xyz],
    "look_xyz": [[round(float(v), 6) for v in r] for r in look_xyz],
    "frame_subject": frame_subject,
    "occluded_frames_before": blocked_nominal, "occluded_frames_after": final_blocked,
    "occlusion_correction": {"passes": passes, "candidate_offsets": len(CANDIDATES),
                             "applied_on": "the desired path, before the damped follow, so the certified position IS "
                                            "the rendered one"},
    "pixel_frames": px_rows,
    "below_min_px_large": below_large, "below_min_px_height": below_height,
    "min_subject_px": args.min_subject_px,
    "speed_range": [float(speed.min()), float(speed.max())],
    "max_accel": float(np.abs(accel).max()),
    "max_frame_move_m": float(np.linalg.norm(np.diff(cam_xyz, axis=0), axis=1).max()),
    "aim_rotation_deg_per_frame": {"mean": float(ang.mean()), "max": float(ang.max()),
                                   "over_1deg": int((ang > 1).sum()), "over_2deg": int((ang > 2).sum()),
                                   "over_5deg": int((ang > 5).sum())},
    "bends_used": [order[i] for i in picked],
    "history": {"r1": "rayTest -1 sentinel read as a hit; frustum test always 0 deg",
                "r2": "position damped but the AIM snapped at subject switches: 82.3 deg single-frame rotation",
                "r3": "aim damped (max 7.37 deg) but 23 frames left blocked by a chair",
                "r4": "blocked frames searched for a clear offset, BUT the search ran before the smoothing and the "
                      "damped follow, both of which move the camera again -- so the certified position was not the "
                      "rendered one, and 1 frame stayed blocked",
                "r5": "fixed a zero-padding bug in the smoothing (`np.convolve(mode='same')` dragged the opening "
                      "frames toward the world origin, shrinking the subject to 30 px); coverage then passed at 0 "
                      "frames below 50 px, but 13 frames were blocked because the smoothing and the damping still "
                      "ran after the search",
                "r6": "moved the search before the damping and iterated, but the loop still tested the ray to the RAW "
                      "look-at point while the audit tested the ray to the DAMPED aim -- two different rays, so 6 "
                      "frames were 'cleared' that were still blocked, and the audit found 12",
                "r7": "this file -- the aim is computed FIRST (it does not depend on the camera position), every "
                      "occlusion test and the final audit use that same ray, and corrections are tapered over a "
                      "9-frame window so a single-frame move cannot push its neighbours into the obstacle"},
    "note": ("the camera follows the real event timing on the SOLVER's clock, sits laterally (never on the chain "
             "axis), and no physics is stretched or frozen for it"),
}
(OUT / "camera_path.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
(OUT / "camera_clearance.json").write_text(json.dumps(
    {"occluded_frames_before": blocked_nominal, "occluded_frames": final_blocked, "n_frames": n_frames,
     "occlusion_correction": payload["occlusion_correction"],
     "below_min_px_large": len(below_large), "below_min_px_height": len(below_height),
     "min_subject_px": args.min_subject_px, "speed_range": payload["speed_range"],
     "aim_rotation_deg_per_frame": payload["aim_rotation_deg_per_frame"],
     "max_accel": payload["max_accel"]}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nwrote {OUT / 'camera_path.json'} and {OUT / 'camera_clearance.json'}", flush=True)
w.close()
