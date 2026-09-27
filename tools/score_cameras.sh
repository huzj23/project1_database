#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Score camera candidates WITHOUT relying on segmentation (which currently comes
# out all-zero -- a separate defect).
#
# Occlusion test by depth:
#   1. take the subject's world position from trajectory.json
#   2. unproject it to a pixel with the recorded intrinsics/extrinsics
#   3. read the depth there; if something is much closer than the subject, the
#      view is blocked
#
# Richness test: colour variance of the frame away from the subject -- a bare wall
# is nearly uniform, a furnished room has structure.
#
# Prominence test: how large the subject is on screen (from its world size and the
# camera distance), so it stays readable without filling the frame.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$PY" - "$REPO" <<'PY'
import json, os, sys, math
import numpy as np
import cv2

REPO = sys.argv[1]
base = os.path.join(REPO, "datasets/free_fall")
rows = []
for g in sorted(os.listdir(base)):
    D = os.path.join(base, g, "x0.5")
    if not os.path.isfile(os.path.join(D, "metadata.json")):
        continue
    md = json.load(open(os.path.join(D, "metadata.json")))
    cam = (md.get("camera") or {})
    pos = np.array(cam.get("position"), dtype=float)
    look = np.array(cam.get("look_at"), dtype=float)
    focal = float(cam.get("focal_length_mm") or 50.0)
    sensor = float((md.get("render") or {}).get("camera_sensor_width_mm") or 36.0)
    res = (md.get("render") or {}).get("resolution") or [480, 270]
    W, H = int(res[0]), int(res[1])

    tr = json.load(open(os.path.join(D, "trajectory.json")))
    st = tr if isinstance(tr, list) else tr.get("states", [])
    P = np.array([s["position"] for s in st], dtype=float)

    # camera basis
    fwd = look - pos
    fwd /= max(np.linalg.norm(fwd), 1e-9)
    up_w = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up_w)
    right /= max(np.linalg.norm(right), 1e-9)
    up = np.cross(right, fwd)

    fx = focal / sensor * W                     # pixels
    fy = fx

    def project(pt):
        d = pt - pos
        z = float(np.dot(d, fwd))
        if z <= 1e-6:
            return None
        x = float(np.dot(d, right))
        y = float(np.dot(d, up))
        u = W * 0.5 + fx * (x / z)
        v = H * 0.5 - fy * (y / z)
        return u, v, z

    rgb_dir = os.path.join(D, "rgb")
    dep_dir = os.path.join(D, "depth")
    rgbs = sorted(f for f in os.listdir(rgb_dir) if f.endswith(".png"))
    deps = sorted(f for f in os.listdir(dep_dir) if f.endswith(".png"))

    occl, rich, prom = [], [], []
    for i, (rn, dn) in enumerate(zip(rgbs, deps)):
        img = cv2.imread(os.path.join(rgb_dir, rn))
        dm = cv2.imread(os.path.join(dep_dir, dn), cv2.IMREAD_UNCHANGED)
        if img is None or dm is None:
            continue
        if dm.ndim == 3:
            dm = dm[..., 0]
        st_i = min(i, len(P) - 1)
        pr = project(P[st_i])
        if pr is None:
            occl.append(0.0)
            continue
        u, v, z = pr
        ui, vi = int(round(u)), int(round(v))
        if not (0 <= ui < W and 0 <= vi < H):
            occl.append(0.0)
            continue
        d = float(dm[vi, ui])
        # depth is stored in millimetres in our pipeline; normalise defensively
        if d > 1000:
            d = d / 1000.0
        occl.append(1.0 if d >= 0.85 * z else 0.0)
        # prominence: subject size on screen
        size_world = float(md.get("asset", {}).get("size_m") or 0.268) if isinstance(md.get("asset"), dict) else 0.268
        prom.append((fx * size_world / z) / W)
        # richness away from the subject
        y0, y1 = max(0, vi - 30), min(H, vi + 30)
        x0, x1 = max(0, ui - 30), min(W, ui + 30)
        mask = np.ones((H, W), bool)
        mask[y0:y1, x0:x1] = False
        if mask.sum() > 200:
            bg = img[mask].astype(np.float32)
            rich.append(float(bg.reshape(-1, 3).std(axis=0).mean()))

    if not occl:
        continue
    rows.append({
        "group": g,
        "visible": float(np.mean(occl)),
        "richness": float(np.median(rich)) if rich else 0.0,
        "prominence": float(np.median(prom)) if prom else 0.0,
        "cam": pos.round(2).tolist(),
    })

rows.sort(key=lambda r: (-r["visible"], -r["richness"]))
print(f"{'group':<14}{'visible':>9}{'richness':>10}{'promin':>8}  camera")
for r in rows:
    print(f"{r['group']:<14}{r['visible']*100:8.0f}%{r['richness']:10.1f}"
          f"{r['prominence']*100:7.1f}%  {r['cam']}")

if rows:
    best = rows[0]
    print()
    print(f"BEST -> {best['group']}  visible={best['visible']*100:.0f}%  "
          f"richness={best['richness']:.1f}")
    open(os.path.join(REPO, "configs/_best_camera.json"), "w").write(
        json.dumps(best, indent=2))
PY
