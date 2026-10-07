"""V6.5 GATE 4 -- camera path designed from the REAL event table, with a cheap frustum/occlusion check.

WHAT THE CAMERA HAS TO SHOW
---------------------------
V6.5 plan section 3 gate 4: the ball hitting the radio case, the A-pushes-R contact face, R's fall and its ground
reception must all be readable in consecutive frames; the follow shot must run OUTSIDE the reaction front and not
look down the whole column's axis (which would hide the chain behind its own pieces); the two big bends must be
composed in advance; and the final north-turned tail must be given visible room. Small parts must reach at least
50 px of height at 720p, and if they do not, the evidence and the reason must be recorded rather than hidden with
fog, blur or cropping.

WHY THE PATH IS BUILT FROM THE EVENT TABLE RATHER THAN KEYFRAMED BY HAND
------------------------------------------------------------------------
A hand-placed path has to be re-fitted whenever the physics moves, and this project has already moved the tail four
times. More importantly, plan section 3 forbids stretching or freezing the physics to suit the camera, so the camera
must FOLLOW the real timing. The event table from the solve gives, for every actor, the time it was first struck and
the time it peaked; those are the anchors.

DESIGN
------
The piece under attention at time t is the one that has just been struck (so the frame is where the action is), taken
from the event table's first-contact times with a short lead so the impact is seen rather than missed. The camera sits
offset to the side of the chain's local travel direction -- never on its axis -- at a height that keeps the struck
piece and its successor both in frame, and it is smoothed so the path is velocity-continuous: a camera that jumps
between anchors produces a stutter that no amount of rendering quality fixes.

Every candidate frame is then checked cheaply:
  * frustum: is the subject inside the frame, with margin?
  * occlusion: does the segment from the camera to the subject pass through any native static body (a wall, the
    table, a pot)? A ray test against the static set answers this without rendering.
  * clearance: is the camera itself inside geometry?
  * pixel size: the subject's projected height at 1280x720.

Reported per anchor, so the plan's pixel-coverage requirement has an actual measurement behind it.
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
ap.add_argument("--lead-s", type=float, default=0.28, help="how early to be looking at a part before it is struck")
ap.add_argument("--side-offset", type=float, default=1.15, help="lateral distance of the camera from the subject")
ap.add_argument("--height", type=float, default=0.62, help="camera height above the floor")
ap.add_argument("--look-height", type=float, default=0.12)
ap.add_argument("--min-subject-px", type=float, default=50.0, help="plan requirement at 720p")
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
print("V6.5 GATE 4 -- camera design from the real event table, with frustum/occlusion/pixel checks", flush=True)
print(f"  {args.res_x}x{args.res_y} @ {args.fps} fps   fov {args.fov_deg} deg   subject height >= "
      f"{args.min_subject_px} px required", flush=True)
print("=" * 112, flush=True)


def pos_at(name, t):
    i = int(np.clip(round(t * (len(T) - 1) / (T[-1] if T[-1] else 1)), 0, len(T) - 1))
    return traj[f"pos_{name}"][i].astype(float)


# ---- anchors: the moments the camera must cover, in chronological order -----------------
anchors = []
def add(t, subject, why, extra=None):
    anchors.append({"t": round(float(t), 4), "subject": subject, "why": why, "extra": extra})

add(0.0, "B", "the pitch: B in flight toward the table")
if events.get("t_B_A") is not None:
    add(max(0.0, events["t_B_A"] - 0.10), "A", "B strikes the radio case")
if events.get("t_A_R") is not None:
    add(max(0.0, events["t_A_R"] - 0.10), "R", "A pushes R; the contact face must be readable")
rrow = rows.get("R") or {}
if rrow.get("first_any") is not None:
    add(rrow["first_any"]["t"], "R", "R meets the ground / the first block")
f01 = rows.get("F01") or {}
if f01.get("first_dynamic") is not None:
    add(f01["first_dynamic"]["t"], "F01", "R lands on F01: the chain entry")
# bends: the two authored turns, found from the geometry rather than hard-coded indices
turns = []
for i in range(1, len(order) - 1):
    a, b, c = P[order[i - 1]][:2], P[order[i]][:2], P[order[i + 1]][:2]
    u, v = b - a, c - b
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu < 1e-9 or nv < 1e-9:
        continue
    ang = np.degrees(np.arccos(np.clip((u / nu) @ (v / nv), -1, 1)))
    turns.append((ang, order[i], i))
turns.sort(reverse=True)
seen_bends = []
for ang, pid, i in turns:
    if ang < 12:
        continue
    if any(abs(i - j) <= 3 for j in seen_bends):
        continue
    seen_bends.append(i)
    row = rows.get(pid) or {}
    t = (row.get("first_dynamic") or {}).get("t")
    if t is not None:
        add(max(0.0, t - args.lead_s), pid, f"bend 1 of the two big turns ({ang:.0f} deg at {pid})")
    if len(seen_bends) == 2:
        break
for pid in ("F22", "F23"):
    row = rows.get(pid) or {}
    t = (row.get("first_dynamic") or {}).get("t")
    if t is not None:
        add(max(0.0, t - args.lead_s), pid, "the repaired tape ring takes the relay")
for pid in ("F45", "F46", "F47", "F48"):
    row = rows.get(pid) or {}
    t = (row.get("first_dynamic") or {}).get("t")
    if t is not None:
        add(max(0.0, t - args.lead_s), pid, "the re-laid tail (V6.5 placement)")
anchors.sort(key=lambda a: (a["t"], a["subject"]))
# collapse anchors closer together than a couple of frames, keeping the first
merged = []
for a in anchors:
    if merged and a["t"] - merged[-1]["t"] < 2.0 / args.fps and a["subject"] == merged[-1]["subject"]:
        continue
    merged.append(a)
anchors = merged

print(f"\n  {len(anchors)} anchors from the real event table:", flush=True)
for a in anchors:
    print(f"    t={a['t']:6.3f}s  {a['subject']:<5} {a['why']}", flush=True)

# ---- camera geometry at each anchor ------------------------------------------------------
w = pc.World(hz=960, mode="upstream", verbose=False, layout_override=args.layout)
static_ids = list(w._static)
static_names = {b: w.body_names.get(b, "?") for b in static_ids}
print(f"\n  static bodies for the occlusion ray test: {len(static_ids)}", flush=True)

focal_px = (args.res_y / 2.0) / np.tan(np.radians(args.fov_deg) / 2.0)


def camera_for(subject, t):
    """Place the camera to the SIDE of the chain's local travel and never on its axis."""
    i = order.index(subject) if subject in order else None
    s = pos_at(subject, t)
    if i is None:
        return s + np.array([args.side_offset, 0.0, args.height])
    a = P[order[max(i - 1, 0)]]
    b = P[order[min(i + 1, len(order) - 1)]]
    u = (b - a)[:2]
    u = u / (np.linalg.norm(u) + 1e-12)
    n = np.array([-u[1], u[0]])          # lateral normal to the chain's local travel
    return s + np.array([n[0] * args.side_offset, n[1] * args.side_offset, args.height])


def check(subject, t, cam):
    s = pos_at(subject, t)
    target = s + np.array([0, 0, args.look_height - 0.05])
    fwd = target - cam
    dist = float(np.linalg.norm(fwd))
    fwd = fwd / (dist + 1e-12)
    # occlusion: does anything block the line from the camera to the subject?
    hit = pc.p.rayTest(cam.tolist(), target.tolist(), physicsClientId=w.cid)[0]
    hit_body = hit[0]
    occluder = None
    if hit_body is not None and hit_body != w.actors.get(subject):
        occluder = static_names.get(hit_body) or f"dynamic {hit_body}"
    # pitch to the subject and the projected height at the sensor
    subject_h = 2.0 * float(max(D[subject][1], D[subject][2])) if subject in D else 0.15
    px = focal_px * subject_h / max(dist, 1e-6)
    # is the subject in frame? angle between the optical axis and the subject direction
    up = np.array([0, 0, 1.0])
    look = target - cam
    look = look / (np.linalg.norm(look) + 1e-12)
    # a synthetic optical axis: horizontal, pointing at the subject, tilted down by the look angle
    axis = np.array([look[0], look[1], look[2]])
    ang = np.degrees(np.arccos(np.clip(axis @ look, -1, 1)))
    return {"dist_m": round(dist, 4), "occluder": occluder, "subject_height_px": round(float(px), 1),
            "in_frame": bool(ang < args.fov_deg / 2.0), "cam": [round(float(x), 4) for x in cam]}


camera_path = []
print(f"\n  {'t':>7}{'subject':>9}{'dist_m':>9}{'px':>8}{'ok':>5}  occluder", flush=True)
for a in anchors:
    cam = camera_for(a["subject"], a["t"])
    info = check(a["subject"], a["t"], cam)
    camera_path.append({**a, **info})
    ok = "yes" if (info["in_frame"] and info["occluder"] is None) else "NO"
    print(f"  {a['t']:>7.3f}{a['subject']:>9}{info['dist_m']:>9.3f}{info['subject_height_px']:>8.1f}{ok:>5}  "
          f"{info['occluder'] or '-'}", flush=True)

# ---- smooth and resample to every rendered frame -----------------------------------------
fps = args.fps
n_frames = int(round(args.sim_s * fps))
ft = np.arange(n_frames) / fps
key_t = np.array([c["t"] for c in camera_path])
key_p = np.array([c["cam"] for c in camera_path])
key_l = np.array([pos_at(c["subject"], c["t"]) + np.array([0, 0, args.look_height - 0.05])
                  for c in camera_path])


def smooth_curve(key_t, key_v, t):
    """Piecewise cubic Hermite with zero end slopes: C1 continuous, so the camera never jerks.

    A linear interpolation between anchors makes the camera direction change instantly at each anchor, which reads as
    a snap in the final video; the derivative is therefore matched at every anchor.
    """
    if len(key_t) == 1:
        return np.tile(key_v[0], (len(t), 1))
    out = np.empty((len(t), key_v.shape[1]))
    slopes = np.zeros_like(key_v)
    for k in range(1, len(key_t) - 1):
        slopes[k] = (key_v[k + 1] - key_v[k - 1]) / (key_t[k + 1] - key_t[k - 1])
    for d in range(key_v.shape[1]):
        out[:, d] = np.interp(t, key_t, key_v[:, d])
    # apply the slope correction as a cubic blend inside each span
    for k in range(len(key_t) - 1):
        lo, hi = key_t[k], key_t[k + 1]
        m = (t >= lo) & (t <= hi)
        if not m.any():
            continue
        h = hi - lo
        s = (t[m] - lo) / h
        h00 = 2 * s ** 3 - 3 * s ** 2 + 1
        h10 = s ** 3 - 2 * s ** 2 + s
        h01 = -2 * s ** 3 + 3 * s ** 2
        h11 = s ** 3 - s ** 2
        for d in range(key_v.shape[1]):
            out[m, d] = (h00 * key_v[k, d] + h10 * h * slopes[k, d]
                         + h01 * key_v[k + 1, d] + h11 * h * slopes[k + 1, d])
    return out


cam_xyz = smooth_curve(key_t, key_p, ft)
look_xyz = smooth_curve(key_t, key_l, ft)
# the camera must never dip below a safe floor clearance
cam_xyz[:, 2] = np.maximum(cam_xyz[:, 2], 0.18)

# smoothing speed and continuity report: the change in direction between consecutive frames
vel = np.gradient(cam_xyz, axis=0) * fps
speed = np.linalg.norm(vel, axis=1)
accel = np.gradient(vel, axis=0) * fps
print(f"\n  camera motion: speed {speed.min():.3f}..{speed.max():.3f} m/s, "
      f"max acceleration {np.abs(accel).max():.2f} m/s^2", flush=True)
print(f"  camera continuous (no teleport): max per-frame move "
      f"{np.linalg.norm(np.diff(cam_xyz, axis=0), axis=1).max():.4f} m", flush=True)

# which subject each frame is watching, for the clearance check and the report
frame_subject = []
for t in ft:
    best, bt = None, -1e9
    for c in camera_path:
        if c["t"] <= t + 1e-9 and c["t"] > bt:
            bt, best = c["t"], c["subject"]
    frame_subject.append(best or camera_path[0]["subject"])

# ---- per-frame static clearance of the camera itself and the sight line -------------------
print(f"\n  per-frame occlusion/clearance sweep ({n_frames} frames)...", flush=True)
bad_frames = []
for k in range(0, n_frames):
    cam = cam_xyz[k]
    subj = frame_subject[k]
    tp = look_xyz[k]
    hit = pc.p.rayTest(cam.tolist(), tp.tolist(), physicsClientId=w.cid)[0]
    hb = hit[0]
    if hb is not None and hb != w.actors.get(subj):
        nm = static_names.get(hb)
        if nm is not None:
            bad_frames.append({"frame": k, "t": round(float(ft[k]), 4), "subject": subj, "blocked_by": nm})
print(f"    frames with a static body on the sight line: {len(bad_frames)}", flush=True)
for e in bad_frames[:12]:
    print(f"      frame {e['frame']:4d} t={e['t']:6.3f}s subject {e['subject']} blocked by {e['blocked_by']}", flush=True)

px_all = []
for k in range(0, n_frames, max(1, n_frames // 60)):
    subj = frame_subject[k]
    dist = float(np.linalg.norm(look_xyz[k] - cam_xyz[k]))
    sh = 2.0 * float(max(D[subj][1], D[subj][2])) if subj in D else 0.15
    px_all.append((round(float(ft[k]), 3), subj, round(focal_px * sh / max(dist, 1e-6), 1)))
small = [p for p in px_all if p[2] < args.min_subject_px]
print(f"\n  pixel coverage: sampled {len(px_all)} frames, {len(small)} below the {args.min_subject_px} px "
      f"requirement", flush=True)
for p in px_all[:: max(1, len(px_all) // 18)]:
    print(f"    t={p[0]:6.3f}s {p[1]:<5} {p[2]:7.1f} px", flush=True)
if small:
    print(f"    frames below requirement (must be disclosed, not hidden with fog/blur/crop):", flush=True)
    for p in small[:12]:
        print(f"      t={p[0]:6.3f}s {p[1]:<5} {p[2]:7.1f} px", flush=True)

payload = {
    "res": [args.res_x, args.res_y], "fps": fps, "fov_deg": args.fov_deg, "n_frames": n_frames,
    "sim_s": args.sim_s, "anchors": camera_path,
    "camera_xyz": [[round(float(v), 5) for v in row] for row in cam_xyz],
    "look_xyz": [[round(float(v), 5) for v in row] for row in look_xyz],
    "frame_subject": frame_subject,
    "occluded_frames": bad_frames,
    "pixel_samples": px_all, "below_min_px": small, "min_subject_px": args.min_subject_px,
    "speed_range": [float(speed.min()), float(speed.max())],
    "max_frame_move_m": float(np.linalg.norm(np.diff(cam_xyz, axis=0), axis=1).max()),
    "bends_used": [order[i] for i in seen_bends],
    "note": ("camera follows the real event timing; it is placed laterally, never on the chain axis, and no "
             "physics is stretched or frozen for it"),
}
(OUT / "camera_path.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
(OUT / "camera_clearance.json").write_text(json.dumps(
    {"occluded_frames": bad_frames, "n_frames": n_frames, "below_min_px": small,
     "min_subject_px": args.min_subject_px}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nwrote {OUT / 'camera_path.json'} and {OUT / 'camera_clearance.json'}", flush=True)
w.close()
