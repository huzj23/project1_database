#!/usr/bin/env bash
# Pinpoint which operation on the depth layer segfaults under GPU rendering.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -X faulthandler - <<'PY' 2>&1 | grep -E '^PROBE|^Fatal|File "|Segmentation' 
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
import numpy as np
import kubric as kb
import phyco_common as pc
from kubric.simulator import PyBullet
from kubric.renderer import Blender

def p(*a):
    print("PROBE", *a, flush=True)

scratch = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
scene = kb.Scene(resolution=(160, 96), frame_start=0, frame_end=1,
                 frame_rate=10, step_rate=100, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=4, use_denoising=False, verbose=True)
sim = PyBullet(scene, scratch)
pc.add_ground(kb, scene, size=3.0)
a = pc.get_asset("ball")
obj = kb.FileBasedObject(name="ball", simulation_filename=a.urdf_path,
                         render_filename=a.obj_path, scale=0.3,
                         position=(0.0, 0.0, 0.3), segmentation_id=2)
scene += obj
scene.camera = kb.PerspectiveCamera(focal_length=42, sensor_width=36)
scene.camera.position = (2.5, -3.0, 2.0)
scene.camera.look_at((0, 0, 0.3))
for f in range(2):
    obj.position = (0.05 * f, 0.0, 0.3)
    obj.keyframe_insert("position", f)
p("scene ready")

out = renderer.render([0, 1], return_layers=("rgba", "segmentation", "depth"))
p("render returned keys:", sorted(out.keys()))

d = out["depth"]
p("type", type(d))
p("shape", getattr(d, "shape", None), "dtype", getattr(d, "dtype", None))
p("flags C", d.flags["C_CONTIGUOUS"], "OWNDATA", d.flags["OWNDATA"],
  "WRITEABLE", d.flags["WRITEABLE"])
p("strides", d.strides, "nbytes", d.nbytes)

c = np.array(d, copy=True)
p("copied ok:", c.shape, c.dtype, c.flags["OWNDATA"], c.flags["C_CONTIGUOUS"])

f64 = np.array(c, dtype=np.float64, copy=True)
p("float64 ok; finite count", int(np.isfinite(f64).sum()), "of", f64.size)
p("min/max", float(np.nanmin(f64)), float(np.nanmax(f64)))

if f64.ndim == 3:
    f64 = f64[..., 0].copy()
    p("squeezed", f64.shape)

valid = np.isfinite(f64) & (f64 > 0) & (f64 < 100.0)
p("valid count", int(valid.sum()))
mm = np.zeros(f64.shape, dtype=np.uint16)
p("zeros ok")
sel = f64[valid]
p("boolean index ok", sel.shape)
r = np.round(sel * 1000.0)
p("round ok")
cl = np.clip(r, 1, 65535)
p("clip ok")
u = cl.astype(np.uint16)
p("astype ok")
mm[valid] = u
p("mask assign ok")
import cv2
ok = cv2.imwrite(os.path.join(os.environ["TMPDIR"], "probe_depth.png"),
                 np.ascontiguousarray(mm))
p("cv2.imwrite ok:", ok)
p("ALL PROBES PASSED")
PY
