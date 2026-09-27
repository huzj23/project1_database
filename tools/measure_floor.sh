#!/usr/bin/env bash
# Measure a ReplicaCAD stage's floor height exactly, by unprojecting the depth
# buffer at a pixel that is known to be floor.
#
# Rendering is the only reliable probe here: the imported GLB geometry is
# invisible to scene.ray_cast, and vertex bounds are inflated by outlier
# geometry to hundreds of metres.
#
# Math: Kubric's depth layer is camera-space Z (metres).  With the intrinsics K
# and the camera world matrix we can turn (pixel, depth) back into a world point.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" - "$WS" <<'PY' 2>&1 | grep -E '^MEAS|^  '
import sys, os, tempfile
WS = sys.argv[1]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
import phyco_backdrops as pb
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender

W, H = 640, 360
for stage in ("frl_apartment_stage", "Stage_v3_sc0_staging"):
    scratch = tempfile.mkdtemp(prefix="meas_")
    scene = kb.Scene(resolution=(W, H), frame_start=0, frame_end=0,
                     frame_rate=24, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=8, use_denoising=False, verbose=True)
    sim = PyBullet(scene, scratch)
    glb = os.path.join(WS, "models/backgrounds/replicad/stages", f"{stage}.glb")
    scene += kb.FileBasedObject(name="stage", simulation_filename=None,
                                render_filename=glb, static=True,
                                background=True, segmentation_id=1)
    cam = kb.PerspectiveCamera(focal_length=50.0, sensor_width=36.0)
    cam.position = (0.0, -3.2, 0.55)
    cam.look_at((0.0, 0.0, -0.15))
    scene.camera = cam

    out = renderer.render([0], return_layers=("depth",))
    depth = np.array(out["depth"], copy=True)[0]
    if depth.ndim == 3:
        depth = depth[..., 0]
    print(f"MEAS stage={stage}  depth shape={depth.shape} "
          f"range {np.nanmin(depth):.3f}..{np.nanmax(depth):.3f}")

    info = kb.get_camera_info(scene.camera)
    K = np.asarray(info["K"], dtype=np.float64)          # 3x3
    M = np.asarray(info["R"], dtype=np.float64)          # 4x4 world matrix
    Kinv = np.linalg.inv(K)
    Minv = np.linalg.inv(M)

    # sample a column of pixels up the image and report the world Z of each
    for frac in (0.99, 0.90, 0.82, 0.76, 0.70, 0.62, 0.55):
        py = int(frac * (H - 1))
        px = W // 2
        d = float(depth[py, px])
        if not np.isfinite(d) or d <= 0 or d > 1e6:
            print(f"  pixel x={px} y={py:3d}  depth={d:12.3f}  (invalid)")
            continue
        # normalized image coords in the convention project_point uses
        u = (px + 0.5) / W - 0.5
        v = 0.5 - (py + 0.5) / H
        ray_cam = Kinv @ np.array([u, v, 1.0])
        ray_cam /= ray_cam[2]                 # camera-space Z == 1
        pt_cam = ray_cam * d                  # metres along camera Z
        pt_world = (Minv @ np.append(pt_cam, 1.0))[:3]
        print(f"  pixel x={px} y={py:3d}  depth={d:7.3f} m  ->  world "
              f"({pt_world[0]:7.2f}, {pt_world[1]:7.2f}, {pt_world[2]:7.2f})")

    import bpy
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()
    print()
PY
