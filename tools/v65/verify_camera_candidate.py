"""V6.5 -- verify a candidate camera path: is the followed subject inside the frame on every frame?

This is the check that `check_in_frame.py` performs on the delivered path, applied to a CANDIDATE directory before any
rendering is committed to. It projects the subject each frame follows through that candidate's own camera orientation
and reports which frames put it outside 1280x720, plus the aim's per-frame rotation.

It exists because the choice between camera variants has to be made on the two numbers that decide gate 4 -- subject in
frame, and rotation -- and both are computable exactly from `camera_path.json` and `trajectory.npz` with no rendering.
Choosing by intuition instead is what produced the r9/r12/r13 sequence.
"""

import argparse
import json
import math

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--camera", required=True, help="camera_path.json of the candidate")
ap.add_argument("--trajectory", required=True)
ap.add_argument("--out", default=None)
args = ap.parse_args()

cam = json.load(open(args.camera))
traj = np.load(args.trajectory)
T = traj["t"]
HZ = 1.0 / float(T[1] - T[0])
W, H = cam["res"]
focal = (W / 2.0) / math.tan(math.radians(cam["fov_deg"]) / 2.0)
fps = cam["fps"]
camx = np.array(cam["camera_xyz"], dtype=float)
lookx = np.array(cam["look_xyz"], dtype=float)
subjects = cam["frame_subject"]
n = len(camx)

outside = []
min_edge = 1e9
for k in range(n):
    f = lookx[k] - camx[k]
    f = f / (np.linalg.norm(f) + 1e-12)
    r = np.cross(f, np.array([0.0, 0.0, 1.0]))
    r = r / (np.linalg.norm(r) + 1e-12)
    u = np.cross(r, f)
    i = int(np.clip(round((k / fps) * HZ), 0, len(T) - 1))
    p = traj[f"pos_{subjects[k]}"][i].astype(float)
    d = p - camx[k]
    z = float(d @ f)
    if z <= 0.02:
        outside.append({"frame": k, "t": round(k / fps, 4), "subject": subjects[k], "reason": "behind camera"})
        continue
    x = W / 2.0 + focal * float(d @ r) / z
    y = H / 2.0 - focal * float(d @ u) / z
    if not (0 <= x <= W and 0 <= y <= H):
        outside.append({"frame": k, "t": round(k / fps, 4), "subject": subjects[k],
                        "x": round(x, 1), "y": round(y, 1)})
    else:
        min_edge = min(min_edge, x, W - x, y, H - y)

aim = lookx - camx
aim /= np.linalg.norm(aim, axis=1, keepdims=True)
ang = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", aim[:-1], aim[1:]), -1.0, 1.0)))
v = np.linalg.norm(np.diff(camx, axis=0), axis=1) * fps

print(f"camera: {args.camera}")
print(f"  {W}x{H} at {fps} fps, {n} frames, focal {focal:.1f} px")
print(f"  subject INSIDE the frame: {n - len(outside)}/{n}")
print(f"  subject OUTSIDE the frame: {len(outside)}")
for e in outside[:15]:
    print(f"      {e}")
print(f"  closest approach of the subject to any frame edge: {min_edge:.1f} px")
print(f"  aim rotation: mean {ang.mean():.3f} deg/frame, max {ang.max():.3f} deg/frame "
      f"(a 1 deg turn moves the image ~{focal * math.tan(math.radians(1)):.1f} px)")
print(f"  frames over 5 deg aim: {int((ang > 5).sum())}, over 10 deg: {int((ang > 10).sum())}")
print(f"  camera speed: max {v.max():.3f} m/s (cap {cam.get('max_speed_cap')})")

res = {"camera": args.camera, "frames": n, "inside": n - len(outside), "outside": len(outside),
       "outside_frames": outside[:40], "min_edge_px": round(float(min_edge), 1),
       "aim_rotation_deg_per_frame": {"mean": float(ang.mean()), "max": float(ang.max()),
                                      "over_5deg": int((ang > 5).sum()), "over_10deg": int((ang > 10).sum())},
       "max_speed": float(v.max())}
if args.out:
    json.dump(res, open(args.out, "w"), indent=2)
    print(f"  wrote {args.out}")
