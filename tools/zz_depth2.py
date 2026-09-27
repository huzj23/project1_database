"""Isolate the actor in the rendered depth frame and measure its world extent."""
import numpy as np
from PIL import Image
import json

R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
D = f"{R}/datasets/turntable_carry/seed-005001/x1"

CAM = np.array([1.194, -0.815, 1.3634])
LOOK = np.array([0.4140, 0.1750, 0.8084])
FOCAL_MM, SENSOR_MM = 50.0, 36.0
W, H = 1920, 1080

traj = json.load(open(f"{D}/trajectory.json"))

f = LOOK - CAM; f /= np.linalg.norm(f)
r = np.cross(f, np.array([0.0, 0.0, 1.0])); r /= np.linalg.norm(r)
u = np.cross(r, f)
fx = FOCAL_MM / SENSOR_MM * W
fy = fx
cx, cy = W / 2.0, H / 2.0

ys, xs = np.mgrid[0:H, 0:W]
dx = (xs - cx) / fx
dy = -(ys - cy) / fy
dirs = (dx[..., None] * r + dy[..., None] * u + np.ones_like(dx)[..., None] * f)
dirs /= np.linalg.norm(dirs, axis=-1, keepdims=True)

DISC_TOP = 0.7804
SUPPORT_RECORDED = 0.073659

for fr in [0, 40, 80]:
    depth = np.array(Image.open(f"{D}/depth/depth_{fr:05d}.tiff")).astype(np.float64)
    pts = CAM + dirs * depth[..., None]
    p = np.array(traj[fr]["position"])
    dxy = np.linalg.norm(pts[..., :2] - p[:2], axis=-1)
    # pixels near the actor's XY column
    m = (dxy < 0.06) & (pts[..., 2] > DISC_TOP - 0.02)
    n = int(m.sum())
    print(f"=== frame {fr}: actor pos={np.round(p,4).tolist()}  candidate px={n}")
    if n < 20:
        print("    too few pixels"); continue
    z = pts[..., 2][m]
    # histogram of z to separate disc surface from actor
    hist, edges = np.histogram(z, bins=24)
    print("    z-histogram (top of disc=0.7804):")
    for h, e0, e1 in zip(hist, edges[:-1], edges[1:]):
        if h:
            print(f"      [{e0:.4f},{e1:.4f}) {h}")
    print(f"    z max={z.max():.4f}  -> height above disc top = {z.max()-DISC_TOP:.4f}")
    print(f"    recorded support_height = {SUPPORT_RECORDED:.4f}")
    print(f"    raw-frame predicted top = {p[2] + 0.133787 - DISC_TOP:.4f} (if raw Z up)")
    print(f"    rot-frame predicted top = {p[2] + 0.105461 - DISC_TOP:.4f} (if raw Y up)")
