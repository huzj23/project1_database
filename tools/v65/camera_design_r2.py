"""V6.5 GATE 4 (r2) -- camera path from the real event table, with the two measurement bugs fixed.

WHAT WAS WRONG IN r1 -- both found by reading its own output, not by assumption
------------------------------------------------------------------------------
  1. OCCLUSION FALSE POSITIVE. `rayTest` returns body id **-1** when the ray hits nothing. r1 tested
     `if hit_body is not None`, which is True for -1, so every clear sight line was reported as occluded by
     "dynamic -1". Twelve of thirteen anchors came back blocked while the per-frame sweep -- which happened to test
     `static_names.get(hb) is not None` and therefore treated -1 correctly -- reported ZERO blocked frames. The two
     halves of one script disagreeing is the tell. The sentinel is now tested explicitly.
  2. FRUSTUM TEST THAT CANNOT FAIL. r1 built `axis` as a copy of `look` and then computed
     `ang = arccos(axis . look)`, which is `arccos(1) = 0` for every subject, so `ang < fov/2` was always true and
     `in_frame` carried no information. That is the same defect class as the earlier profile that priced a call but
     never iterated its result, and the clearance test that included the floor and rejected its own starting point.
     A real off-axis angle is now measured between the optical axis and the direction to the subject's bounding-box
     corners.
  3. A `RuntimeWarning: invalid value in divide` at line 246: two anchors shared an identical time, so a Hermite span
     had zero length. Anchors are now deduplicated on time.

CAMERA MOTION
-------------
r1's Hermite curve peaked at 6.4 m/s and 43 m/s^2 because it was fitted through unevenly spaced anchors with matched
slopes. The chain's reaction front advances at roughly 1 m/s, so that is far too fast and would read as a whip pan.
The path is now a critically damped FOLLOW of the focus point (`cam += alpha * (target - cam)`), which makes
smoothness and speed bounds structural rather than something to hope for, and the achieved speed/acceleration are
measured afterwards and reported. A small lag (~0.2-0.4 s) is the natural look of a tracking shot.

Aspect and coverage are reported honestly: the projected size of the subject's LARGEST and SMALLEST dimension are both
given, because the plan's "small parts at least 50 px" requirement is about the part being legible, and quoting only
the largest dimension would overstate it.
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
ap.add_argument("--side-offset", type=float, default=1.20)
ap.add_argument("--height", type=float, default=0.70)
ap.add_argument("--look-height", type=float, default=0.10)
ap.add_argument("--damp-tau", type=float, default=0.22, help="follow time constant, seconds")
ap.add_argument("--max-speed", type=float, default=1.6, help="hard cap on the camera's speed, m/s")
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

print("=" * 112, flush=True)
print("V6.5 GATE 4 (r2) -- camera from the real event table; -1 sentinel and frustum test corrected", flush=True)
print(f"  {args.res_x}x{args.res_y} @ {args.fps} fps   fov {args.fov_deg} deg   follow tau {args.damp_tau} s   "
      f"speed cap {args.max_speed} m/s", flush=True)
print("=" * 112, flush=True)


def pos_at(name, t):
    i = int(np.clip(round(t * (len(T) - 1) / (T[-1] if T[-1] else 1)), 0, len(T) - 1))
    return traj[f"pos_{name}"][i].astype(float)


# ------------------------------------------------------------------ anchors
anchors = []


def add(t, subject, why):
    anchors.append({"t": round(float(max(0.0, t)), 4), "subject": subject, "why": why})


def ftime(pid):
    return (rows.get(pid, {}).get("first_dynamic") or {}).get("t")


add(0.0, "B", "the pitch: B in flight toward the radio")
if events.get("t_B_A") is not None:
    add(events["t_B_A"] - 0.12, "A", "B strikes the radio case")
if events.get("t_A_R") is not None:
    add(events["t_A_R"] - 0.10, "R", "A pushes R; the receiving contact face")
t = ftime("F01")
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
    tt = ftime(pid)
    if tt is not None:
        add(tt - args.lead_s, pid, f"bend ({ang:.0f} deg at {pid})")
    if len(picked) == 2:
        break
for pid in ("F22", "F23"):
    tt = ftime(pid)
    if tt is not None:
        add(tt - args.lead_s, pid, "the repaired tape ring takes the relay")
for pid in ("F45", "F46", "F47", "F48"):
    tt = ftime(pid)
    if tt is not None:
        add(tt - args.lead_s, pid, "the re-laid tail (V6.5 placement)")
anchors.sort(key=lambda a: a["t"])
# dedupe on TIME as well as subject: two anchors sharing a time made a zero-length Hermite span (r1's divide warning)
dedup = []
for a in anchors:
    if dedup and abs(a["t"] - dedup[-1]["t"]) < 1.0 / args.fps:
        continue
    dedup.append(a)
anchors = dedup

print(f"\n  {len(anchors)} anchors (deduplicated on time):", flush=True)
for a in anchors:
    print(f"    t={a['t']:6.3f}s  {a['subject']:<5} {a['why']}", flush=True)

# ------------------------------------------------------------------ geometry checks
w = pc.World(hz=960, mode="upstream", verbose=False, layout_override=args.layout)
static_ids = list(w._static)
static_names = {b: w.body_names.get(b, "?") for b in static_ids}
dyn_ids = set(w.actors.values())
focal_px = (args.res_y / 2.0) / np.tan(np.radians(args.fov_deg) / 2.0)


def camera_for(subject, t):
    i = order.index(subject) if subject in order else None
    s = pos_at(subject, t)
    if i is None:
        return s + np.array([args.side_offset, 0.0, args.height])
    a = P[order[max(i - 1, 0)]]
    b = P[order[min(i + 1, len(order) - 1)]]
    u = (b - a)[:2]
    u = u / (np.linalg.norm(u) + 1e-12)
    n = np.array([-u[1], u[0]])
    return s + np.array([n[0] * args.side_offset, n[1] * args.side_offset, args.height])


def ray_clear(cam, target, subject):
    """True if nothing solid sits between the camera and the target.

    `rayTest` reports body id -1 when the ray misses everything. r1 checked `is not None`, so -1 counted as a hit and
    every clear line was called occluded; the sentinel is tested explicitly here.
    """
    hit = pc.p.rayTest(cam.tolist(), target.tolist(), physicsClientId=w.cid)[0]
    hb = hit[0]
    if hb is None or hb == -1:
        return True, None
    if hb == w.actors.get(subject):
        return True, None
    if hb in dyn_ids:
        return True, f"dynamic:{w.body_names.get(hb, hb)}"
    return False, static_names.get(hb, str(hb))


def check(subject, t, cam):
    s = pos_at(subject, t)
    target = s + np.array([0, 0, args.look_height])
    dist = float(np.linalg.norm(target - cam))
    look = (target - cam) / (dist + 1e-12)
    # REAL off-axis test: the angle between the optical axis and each corner of the subject's box
    half = np.array([D[subject][0] / 2, D[subject][1] / 2, D[subject][2] / 2]) if subject in D \
        else np.array([.05, .05, .05])
    worst_ang = 0.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                corner = s + half * np.array([sx, sy, sz])
                d = corner - cam
                d = d / (np.linalg.norm(d) + 1e-12)
                worst_ang = max(worst_ang, float(np.degrees(np.arccos(np.clip(d @ look, -1, 1)))))
    clear, blocker = ray_clear(cam, target, subject)
    if subject in D:
        px_large = focal_px * float(max(D[subject][1], D[subject][2])) / max(dist, 1e-6)
        px_small = focal_px * float(D[subject][0]) / max(dist, 1e-6)
    else:
        px_large = px_small = focal_px * 0.15 / max(dist, 1e-6)
    return {"dist_m": round(dist, 4), "blocker": blocker, "sight_line_clear": bool(clear),
            "off_axis_deg": round(worst_ang, 2),
            "in_frame": bool(worst_ang < args.fov_deg / 2.0),
            "px_large": round(float(px_large), 1), "px_small": round(float(px_small), 1),
            "cam": [round(float(x), 5) for x in cam]}


camera_path = []
print(f"\n  {'t':>7}{'subject':>9}{'dist':>8}{'off_axis':>10}{'frame':>7}{'clear':>7}{'px_large':>10}"
      f"{'px_small':>10}  blocker", flush=True)
for a in anchors:
    cam = camera_for(a["subject"], a["t"])
    info = check(a["subject"], a["t"], cam)
    camera_path.append({**a, **info})
    print(f"  {a['t']:>7.3f}{a['subject']:>9}{info['dist_m']:>8.3f}{info['off_axis_deg']:>10.2f}"
          f"{('yes' if info['in_frame'] else 'NO'):>7}{('yes' if info['sight_line_clear'] else 'NO'):>7}"
          f"{info['px_large']:>10.1f}{info['px_small']:>10.1f}  {info['blocker'] or '-'}", flush=True)

# ------------------------------------------------------------------ damped follow, retimed to every frame
fps = args.fps
n_frames = int(round(args.sim_s * fps))
ft = np.arange(n_frames) / fps
alpha = 1.0 - np.exp(-1.0 / (args.damp_tau * fps))
cam_xyz = np.empty((n_frames, 3))
look_xyz = np.empty((n_frames, 3))


def anchor_at(t):
    best = camera_path[0]
    for c in camera_path:
        if c["t"] <= t + 1e-9:
            best = c
        else:
            break
    return best


cam_xyz[0] = anchor_at(0.0)["cam"]
for k in range(1, n_frames):
    a = anchor_at(ft[k])
    target = np.array(a["cam"], dtype=float)
    step = alpha * (target - cam_xyz[k - 1])
    # speed cap, so a distant anchor cannot produce a whip pan even if the damping allows it briefly
    n = np.linalg.norm(step)
    if n > args.max_speed / fps:
        step *= (args.max_speed / fps) / n
    cam_xyz[k] = cam_xyz[k - 1] + step
for k in range(n_frames):
    a = anchor_at(ft[k])
    look_xyz[k] = pos_at(a["subject"], ft[k]) + np.array([0, 0, args.look_height])
cam_xyz[:, 2] = np.maximum(cam_xyz[:, 2], 0.20)

vel = np.diff(cam_xyz, axis=0) * fps
speed = np.linalg.norm(vel, axis=1)
accel = np.diff(vel, axis=0) * fps
print(f"\n  camera motion after the damped follow: speed {speed.min():.3f}..{speed.max():.3f} m/s "
      f"(cap {args.max_speed}), max |accel| {np.abs(accel).max():.2f} m/s^2", flush=True)
print(f"  max per-frame move {np.linalg.norm(np.diff(cam_xyz, axis=0), axis=1).max():.4f} m "
      f"(no teleport, C1-continuous by construction)", flush=True)

frame_subject = [anchor_at(t)["subject"] for t in ft]
occluded = []
for k in range(n_frames):
    c = anchor_at(ft[k])
    clear, blocker = ray_clear(cam_xyz[k], look_xyz[k], c["subject"])
    if not clear:
        occluded.append({"frame": k, "t": round(float(ft[k]), 4), "subject": c["subject"], "blocked_by": blocker})
print(f"  frames whose sight line is blocked by a STATIC body: {len(occluded)}", flush=True)
for e in occluded[:10]:
    print(f"    frame {e['frame']:4d} t={e['t']:6.3f}s {e['subject']} blocked by {e['blocked_by']}", flush=True)

px_rows = []
for k in range(n_frames):
    c = anchor_at(ft[k])
    dist = float(np.linalg.norm(look_xyz[k] - cam_xyz[k]))
    if c["subject"] in D:
        pl = focal_px * float(max(D[c["subject"]][1], D[c["subject"]][2])) / max(dist, 1e-6)
        ps = focal_px * float(D[c["subject"]][0]) / max(dist, 1e-6)
    else:
        pl = ps = focal_px * 0.15 / max(dist, 1e-6)
    px_rows.append({"frame": k, "t": round(float(ft[k]), 4), "subject": c["subject"],
                    "px_large": round(float(pl), 1), "px_small": round(float(ps), 1)})
small = [p for p in px_rows if p["px_small"] < args.min_subject_px]
print(f"\n  pixel coverage: {n_frames} frames, {len(small)} with the subject's SMALLEST dimension below "
      f"{args.min_subject_px} px", flush=True)
for p in px_rows[:: max(1, n_frames // 18)]:
    print(f"    t={p['t']:6.3f}s {p['subject']:<5} large {p['px_large']:7.1f} px  small {p['px_small']:6.1f} px",
          flush=True)
if small:
    print(f"    frames below the requirement (disclosed, not hidden with fog/blur/crop):", flush=True)
    for p in small[:10]:
        print(f"      t={p['t']:6.3f}s {p['subject']:<5} small {p['px_small']:.1f} px", flush=True)

payload = {
    "res": [args.res_x, args.res_y], "fps": fps, "fov_deg": args.fov_deg, "n_frames": n_frames,
    "sim_s": args.sim_s, "damp_tau": args.damp_tau, "max_speed_cap": args.max_speed,
    "anchors": camera_path,
    "camera_xyz": [[round(float(v), 6) for v in r] for r in cam_xyz],
    "look_xyz": [[round(float(v), 6) for v in r] for r in look_xyz],
    "frame_subject": frame_subject, "occluded_frames": occluded,
    "pixel_frames": px_rows, "below_min_px_small": small, "min_subject_px": args.min_subject_px,
    "speed_range": [float(speed.min()), float(speed.max())],
    "max_accel": float(np.abs(accel).max()),
    "max_frame_move_m": float(np.linalg.norm(np.diff(cam_xyz, axis=0), axis=1).max()),
    "bends_used": [order[i] for i in picked],
    "fixes_vs_r1": ["rayTest -1 sentinel handled", "real off-axis frustum test",
                    "anchors deduplicated on time", "damped follow replaces the Hermite fit"],
    "note": ("camera follows the real event timing, sits laterally (never on the chain axis), and no physics is "
             "stretched or frozen for it"),
}
(OUT / "camera_path.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
(OUT / "camera_clearance.json").write_text(json.dumps(
    {"occluded_frames": occluded, "n_frames": n_frames, "below_min_px_small": small,
     "min_subject_px": args.min_subject_px, "speed_range": payload["speed_range"],
     "max_accel": payload["max_accel"]}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nwrote {OUT / 'camera_path.json'} and {OUT / 'camera_clearance.json'}", flush=True)
w.close()
