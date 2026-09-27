"""Back-project the rendered depth frame to world points and locate the actor.

Decisive for the frame question: the actor's world-Z extent above the disc top
(z=0.7804) tells us its rendered orientation and support height.
"""
import numpy as np
from PIL import Image
import json

R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
D = f"{R}/datasets/turntable_carry/seed-005001/x1"

CAM = np.array([1.194, -0.815, 1.3634])
LOOK = np.array([0.4140, 0.1750, 0.8084])
FOCAL_MM, SENSOR_MM = 50.0, 36.0
W, H = 1920, 1080

depth = np.array(Image.open(f"{D}/depth/depth_00000.tiff")).astype(np.float64)
print("depth shape:", depth.shape, "dtype", depth.dtype)
print("depth min/max/mean:", depth.min(), depth.max(), depth.mean())

# Blender depth pass = distance along the camera view axis (Z depth).
# Build camera basis: forward f, right r, up u.
f = LOOK - CAM; f /= np.linalg.norm(f)
world_up = np.array([0.0, 0.0, 1.0])
r = np.cross(f, world_up); r /= np.linalg.norm(r)
u = np.cross(r, f)

# pinhole: sensor width 36 mm over the larger dimension (1920) -> AUTO fit
fx = FOCAL_MM / SENSOR_MM * W
fy = fx
cx, cy = W / 2.0, H / 2.0

ys, xs = np.mgrid[0:H, 0:W]
# direction in camera space (x right, y up, z forward)
dx = (xs - cx) / fx
dy = -(ys - cy) / fy
dz = np.ones_like(dx)
dirs = (dx[..., None] * r + dy[..., None] * u + dz[..., None] * f)
dirs /= np.linalg.norm(dirs, axis=-1, keepdims=True)

pts = CAM + dirs * depth[..., None]
print("world z range of all pixels:", pts[..., 2].min(), pts[..., 2].max())

# Disc top is z = 0.7804.  Anything meaningfully above it is the actor.
for thr in [0.7820, 0.7850, 0.7900]:
    m = pts[..., 2] > thr
    n = int(m.sum())
    print(f"--- pixels with world z > {thr}: {n}")
    if n:
        yy, xx = np.nonzero(m)
        print(f"    screen bbox x[{xx.min()},{xx.max()}] y[{yy.min()},{yy.max()}] "
              f"w={xx.max()-xx.min()+1} h={yy.max()-yy.min()+1}")
        zz = pts[..., 2][m]
        print(f"    world z: min={zz.min():.4f} max={zz.max():.4f}")
        px = pts[..., 0][m]; py = pts[..., 1][m]
        print(f"    world x: [{px.min():.4f},{px.max():.4f}]  y: [{py.min():.4f},{py.max():.4f}]")

# Also: the disc surface, for calibration -- take a pixel clearly on the disc.
print("\n=== disc calibration ===")
# disc centre (0.2,0.2,0.7804) projected:
pc = np.array([0.2, 0.2, 0.7804])
v = pc - CAM
zc = v @ f
xc = (v @ r) / zc * fx + cx
yc = -(v @ u) / zc * fy + cy
print(f"disc centre projects to pixel ({xc:.1f},{yc:.1f}); depth there = "
      f"{depth[int(round(yc)), int(round(xc))]:.4f}; expected z-depth = {zc:.4f}")
