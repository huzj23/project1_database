"""V6.5 -- choose the aim controller by MEASURING subject-in-frame and rotation, without rendering anything.

Three aim controllers have now been tried and each failed in a different, measurable way:

  r9   first-order lag on the switching target  -> subject OUTSIDE the frame on 5/216 frames (frames 15-18, 62)
  r12  rate-limited to 3 deg/frame              -> the aim fell permanently behind; 5 blocked frames, 14 frames with
                                                   the subject's upright height under 50 px
  r13  blended continuous target                -> aim travelled the GAP between subjects; subject OUTSIDE the frame on
                                                   74/216 frames, far worse than either

The pattern says the controller should not be chosen by intuition. Two quantities decide gate 4, and both are cheap to
compute exactly, because projecting a known world point through a known camera path needs no rendering and no physics:

  * IN FRAME -- the followed subject must project inside 1280x720. This is the hard requirement; a subject outside the
    frame is not readable at any resolution.
  * ROTATION -- the aim's per-frame turn. At this focal length the whole image moves roughly focal*tan(angle) px, so a
    turn of d degrees smears the frame by about 29*d px. Large single-frame turns are whip pans.

This sweeps the RATE-LIMIT for the plain raw target (no blending, since blending demonstrably overshoots into the gap)
and reports both quantities for every setting, so the choice is read off a table rather than guessed. Note that with a
rate limit the aim LAGS the subject, which is what pushes the subject toward the frame edge, and the two requirements
pull in opposite directions -- which is exactly why the tradeoff has to be measured.
"""

import argparse
import json
import math
import sys

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
ap.add_argument("--fov-deg", type=float, default=42.0)
ap.add_argument("--res-x", type=int, default=1280)
ap.add_argument("--res-y", type=int, default=720)
ap.add_argument("--look-height", type=float, default=0.10)
ap.add_argument("--damp-tau", type=float, default=0.22)
ap.add_argument("--max-speed", type=float, default=1.6)
ap.add_argument("--height", type=float, default=0.70)
ap.add_argument("--side", type=float, default=1.05)
ap.add_argument("--sign", type=int, default=-1)
args = ap.parse_args()

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
W, H = args.res_x, args.res_y
# FOCAL LENGTH, AND A UNITS BUG IN THE FIRST VERSION OF THIS PROBE
# ---------------------------------------------------------------
# The scene builds the camera with sensor_fit = HORIZONTAL and angle = the FOV, so Blender's focal length follows
# f = (sensor_width/2) / tan(fov/2) and one pixel subtends atan(1/f). In pixels that is (W/2)/tan(fov/2) = 1667.3 at
# 1280x720 and fov 42. The first version of this probe used (H/2)/tan(fov/2) = 937.8 -- the VERTICAL focal -- which
# understated every pixel figure by a factor of 1.78.
focal = (W / 2.0) / math.tan(math.radians(args.fov_deg) / 2.0)


def pos_at(name, t):
    i = int(np.clip(round(t * SOL_HZ), 0, len(T) - 1))
    return traj[f"pos_{name}"][i].astype(float)


def build_anchors():
    a = []

    def add(t, s):
        a.append({"t": round(float(max(0.0, t)), 4), "subject": s})

    add(0.0, "B")
    for key, subj, off in (("t_B_A", "A", 0.12), ("t_A_R", "R", 0.10)):
        if events.get(key) is not None:
            add(events[key] - off, subj)
    t = (rows.get("F01", {}).get("first_dynamic") or {}).get("t")
    if t is not None:
        add(t - 0.06, "F01")
    turns = []
    for i in range(1, len(order) - 1):
        p, q, r = P[order[i - 1]][:2], P[order[i]][:2], P[order[i + 1]][:2]
        u, v = q - p, r - q
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
        tt = (rows.get(pid, {}).get("first_dynamic") or {}).get("t")
        if tt is not None:
            add(tt - 0.25, pid)
        if len(picked) == 2:
            break
    for pid in ("F22", "F23", "F45", "F46", "F47", "F48"):
        tt = (rows.get(pid, {}).get("first_dynamic") or {}).get("t")
        if tt is not None:
            add(tt - 0.25, pid)
    a.sort(key=lambda x: x["t"])
    ded = []
    for x in a:
        if ded and abs(x["t"] - ded[-1]["t"]) < 1.0 / fps:
            continue
        ded.append(x)
    return ded


anchors = build_anchors()


def anchor_at(t):
    best = anchors[0]
    for c in anchors:
        if c["t"] <= t + 1e-9:
            best = c
        else:
            break
    return best


def lateral_of(subject, sign):
    i = order.index(subject) if subject in order else None
    if i is None:
        return np.array([0.0, sign])
    a, b = P[order[max(i - 1, 0)]], P[order[min(i + 1, len(order) - 1)]]
    u = (b - a)[:2]
    u = u / (np.linalg.norm(u) + 1e-12)
    return np.array([-u[1], u[0]]) * sign


frame_subject = [anchor_at(ft[k])["subject"] for k in range(n_frames)]
raw_look = np.stack([pos_at(frame_subject[k], ft[k]) + np.array([0, 0, args.look_height])
                     for k in range(n_frames)])

# camera path (speed-capped damped follow of the lateral standoff), identical for every row of the sweep
desired = np.empty((n_frames, 3))
for k in range(n_frames):
    s = pos_at(frame_subject[k], ft[k])
    lat = lateral_of(frame_subject[k], args.sign)
    desired[k] = s + np.array([lat[0] * args.side, lat[1] * args.side, args.height])
alpha = 1.0 - np.exp(-1.0 / (args.damp_tau * fps))
cam = np.empty((n_frames, 3))
cam[0] = desired[0]
for k in range(1, n_frames):
    step = alpha * (desired[k] - cam[k - 1])
    ns = np.linalg.norm(step)
    if ns > args.max_speed / fps:
        step *= (args.max_speed / fps) / ns
    cam[k] = cam[k - 1] + step


def project(p, k, look):
    """World point -> pixel, using the camera's ACTUAL orientation.

    The first version of this probe built the frame from `raw_look` -- the exact subject position -- rather than from
    the controller's aim. That made the "in frame" column identical for every controller, because every row was judged
    against the same, best-possible orientation; the sweep therefore could not distinguish the controllers at all and
    its reassuring "216/216 in frame" for a lagging controller was meaningless. The orientation must be the one the
    controller produces, which is the whole point of comparing controllers.
    """
    fwd = look[k] - cam[k]
    fwd = fwd / (np.linalg.norm(fwd) + 1e-12)
    right = np.cross(fwd, np.array([0.0, 0.0, 1.0]))
    right /= (np.linalg.norm(right) + 1e-12)
    up = np.cross(right, fwd)
    d = p - cam[k]
    z = float(d @ fwd)
    if z <= 0.02:
        return None
    return (W / 2.0 + focal * float(d @ right) / z, H / 2.0 - focal * float(d @ up) / z)


print("=" * 108, flush=True)
print("V6.5 aim-controller sweep: subject-in-frame and rotation, measured by projection (no rendering)", flush=True)
print(f"  {W}x{H}, focal {focal:.1f} px, 1 deg of turn moves the image ~{focal * math.tan(math.radians(1)):.1f} px",
      flush=True)
print("=" * 108, flush=True)
print(f"\n{'controller':>26} {'in frame':>9} {'out':>5} {'max rot':>8} {'mean rot':>9} {'>64px':>6} "
      f"{'min subj px':>12}", flush=True)

rows_out = []


def evaluate(name, look):
    inside = 0
    outside = []
    min_px = 1e9
    for k in range(n_frames):
        p = project(pos_at(frame_subject[k], ft[k]), k, look)
        # judged against the FRAME the controller's aim defines -- this is what makes the column meaningful
        if p is None:
            outside.append((k, frame_subject[k], None))
            continue
        x, y = p
        if 0 <= x <= W and 0 <= y <= H:
            inside += 1
        else:
            outside.append((k, frame_subject[k], (round(x), round(y))))
        dm = float(np.linalg.norm(raw_look[k] - cam[k]))
        if frame_subject[k] in D:
            min_px = min(min_px, focal * float(D[frame_subject[k]][2]) / max(dm, 1e-6))
    aim = look - cam
    aim /= np.linalg.norm(aim, axis=1, keepdims=True)
    ang = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", aim[:-1], aim[1:]), -1.0, 1.0)))
    steps = ang * focal * math.tan(math.radians(1))
    return {"name": name, "inside": inside, "outside": len(outside), "outside_frames": outside[:12],
            "max_rot": float(ang.max()), "mean_rot": float(ang.mean()),
            "over_64px": int((steps > 64).sum()), "min_subj_px": round(float(min_px), 1)}


def rate_limited(target, max_deg):
    out = np.empty((n_frames, 3))
    out[0] = target[0]
    for k in range(1, n_frames):
        d_cur = out[k - 1] - cam[k]
        d_want = target[k] - cam[k]
        nc, nw = np.linalg.norm(d_cur), np.linalg.norm(d_want)
        if nc < 1e-9 or nw < 1e-9:
            out[k] = target[k]
            continue
        c = float(np.clip((d_cur / nc) @ (d_want / nw), -1.0, 1.0))
        a = math.degrees(math.acos(c))
        if a <= max_deg:
            out[k] = target[k]
        else:
            perp = (d_want / nw) - c * (d_cur / nc)
            nperp = np.linalg.norm(perp)
            nd = ((math.cos(math.radians(max_deg)) * (d_cur / nc))
                  + (math.sin(math.radians(max_deg)) * (perp / nperp) if nperp > 1e-12 else 0))
            out[k] = cam[k] + nd * nw
    return out


# reference: aim exactly at the subject every frame -- best possible for "in frame", worst for rotation
exact = raw_look.copy()
r = evaluate("exact aim (no lag)", exact)
rows_out.append(r)
print(f"{r['name']:>26} {r['inside']:>9} {r['outside']:>5} {r['max_rot']:>8.2f} {r['mean_rot']:>9.2f} "
      f"{r['over_64px']:>6} {r['min_subj_px']:>12.1f}", flush=True)

for maxdeg in (25, 20, 16, 13, 10, 8, 6, 5):
    r = evaluate(f"rate limit {maxdeg} deg", rate_limited(raw_look, maxdeg))
    rows_out.append(r)
    print(f"{r['name']:>26} {r['inside']:>9} {r['outside']:>5} {r['max_rot']:>8.2f} {r['mean_rot']:>9.2f} "
          f"{r['over_64px']:>6} {r['min_subj_px']:>12.1f}", flush=True)

# A LAG ON THE SWITCHING TARGET is what r9 used, and the whole point of this sweep is to reproduce that failure so the
# table can be trusted. If no row here shows the subject leaving the frame, the probe is not measuring orientation.
for tau in (0.40, 0.30, 0.22, 0.15, 0.10, 0.06):
    la = 1.0 - np.exp(-1.0 / (tau * fps))
    look = np.empty((n_frames, 3))
    look[0] = raw_look[0]
    for k in range(1, n_frames):
        look[k] = look[k - 1] + la * (raw_look[k] - look[k - 1])
    r = evaluate(f"first-order lag tau {tau}", look)
    rows_out.append(r)
    print(f"{r['name']:>26} {r['inside']:>9} {r['outside']:>5} {r['max_rot']:>8.2f} {r['mean_rot']:>9.2f} "
          f"{r['over_64px']:>6} {r['min_subj_px']:>12.1f}", flush=True)

# CROSSFADE: blend the target over a fixed time before each anchor so the target is continuous, but keep the blend
# local to the switch rather than spanning the whole inter-anchor interval (r13 spanned the interval and aimed at the
# empty gap between two distant pieces for seconds at a time).
for blend_s in (0.60, 0.45, 0.30, 0.22, 0.15):
    look = raw_look.copy()
    n_bl = max(1, int(round(blend_s * fps)))
    for ai in range(1, len(anchors)):
        k_switch = int(round(anchors[ai]["t"] * fps))
        for j in range(n_bl):
            k = k_switch - n_bl + j
            if k < 1 or k >= n_frames:
                continue
            u = (j + 1) / (n_bl + 1.0)
            uu = u * u * (3.0 - 2.0 * u)
            prev_subj = anchors[ai - 1]["subject"]
            new_subj = anchors[ai]["subject"]
            look[k] = ((1.0 - uu) * (pos_at(prev_subj, ft[k]) + np.array([0, 0, args.look_height]))
                       + uu * (pos_at(new_subj, ft[k]) + np.array([0, 0, args.look_height])))
    r = evaluate(f"crossfade {blend_s} s", look)
    rows_out.append(r)
    print(f"{r['name']:>26} {r['inside']:>9} {r['outside']:>5} {r['max_rot']:>8.2f} {r['mean_rot']:>9.2f} "
          f"{r['over_64px']:>6} {r['min_subj_px']:>12.1f}", flush=True)

# the probe must be able to FAIL: if every controller reports the subject in frame, the column is not measuring anything
if len({r["outside"] for r in rows_out}) == 1:
    raise SystemExit("PROBE IS BROKEN: every controller reports the same 'outside' count, so the orientation is not "
                     "being applied to the subject's projection")

json.dump(rows_out, open(args.out, "w"), indent=2)
print(f"\nwrote {args.out}", flush=True)

best = max(rows_out, key=lambda r: (r["inside"], -r["over_64px"]))
print(f"\nBEST by (subject in frame, fewest smeared frames): {best['name']}", flush=True)
print(f"  {best['inside']}/{n_frames} frames with the subject inside, {best['outside']} outside, "
      f"max rotation {best['max_rot']:.2f} deg, {best['over_64px']} frames over 64 px", flush=True)
zero = [r for r in rows_out if r["outside"] == 0]
if zero:
    z = min(zero, key=lambda r: r["over_64px"])
    print(f"  among controllers that keep the subject in frame EVERY frame, the calmest is '{z['name']}': "
          f"{z['over_64px']} frames over 64 px, max rotation {z['max_rot']:.2f} deg", flush=True)
else:
    print("  NO controller keeps the subject in frame on every frame; the residual must be disclosed", flush=True)
    for r in rows_out:
        if r["outside"]:
            print(f"    {r['name']}: outside frames {[f[0] for f in r['outside_frames']]}", flush=True)
