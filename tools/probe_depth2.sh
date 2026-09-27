#!/usr/bin/env bash
# Reproduce the depth crash with the runner's EXACT settings, then step through
# the conversion so the failing operation is unambiguous.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -X faulthandler - <<'PY' 2>&1 | grep -E '^STEP|^Fatal|phyco_common|run_single|Segmentation'
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, "/data/raw/huzijian/project1_database/code/scenarios")
import numpy as np
import kubric as kb
import phyco_common as pc
from kubric.simulator import PyBullet
from kubric.renderer import Blender

def s(*a): print("STEP", *a, flush=True)

# --- exactly the runner's scene recipe -------------------------------------
res_w, res_h = 320, 180
n = 4
scratch = pc.tempfile.mkdtemp(prefix="probe_")
scene = kb.Scene(resolution=(res_w, res_h), frame_start=0, frame_end=n - 1,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=8, use_denoising=True,
                   verbose=True)
sim = PyBullet(scene, scratch)
s("views ok")
pc.add_ground(kb, scene, size=3.5)
a = pc.get_asset("ball")
obj = kb.FileBasedObject(name="ball", simulation_filename=a.urdf_path,
                         render_filename=a.obj_path, scale=0.3,
                         position=(0.0, 0.0, 0.9), segmentation_id=2)
scene += obj
lo, hi = pc.mesh_bounds(a.obj_path)
com = pc.read_urdf_inertia(a.urdf_path).get("origin") or [0, 0, 0]
s("mesh bounds", lo, hi, "com", com)
pc.add_lighting(kb, scene)
pc.set_background(renderer, scene)
s("lighting ok")

import phyco_motions as pm
spec = pm.CircularSpec(radius=1.2, period_s=2.0, center=(0, 0, 0.9), axis="z")
states = pm.apply_circular(kb, obj, spec, n, 24.0, [0.3 * v for v in com])
s("keyframes ok")
traj = []
for f in range(n):
    p = states[f]["position"]
    for dx, dy, dz in ((0.3*(hi[0]-com[0]),0,0), (-0.3*(hi[0]-com[0]),0,0)):
        traj.append([p[0]+dx, p[1]+dy, p[2]+dz])
d, rep = pc.auto_frame_camera(kb, scene, traj, (0, 0, 0.9),
                              elevation_deg=24.0, azimuth_deg=-62.0,
                              margin=0.12, start_distance=5.0)
s("camera framed d=", round(d, 3))

out = renderer.render(list(range(n)), return_layers=("rgba", "segmentation", "depth"))
s("render ok, keys", sorted(out.keys()))

dpt = out["depth"]
s("depth shape", dpt.shape, dpt.dtype,
  "C", dpt.flags["C_CONTIGUOUS"], "OWN", dpt.flags["OWNDATA"],
  "WRITE", dpt.flags["WRITEABLE"])
s("depth strides", dpt.strides, "base is None:", dpt.base is None)

c1 = np.array(dpt, copy=True)
s("copy ok", c1.shape, c1.flags["OWNDATA"])
del out, dpt
s("dropped originals")

f64 = np.array(c1, dtype=np.float64, copy=True)
s("float64 ok")
sq = f64[..., 0].copy()
s("squeeze ok", sq.shape)
fin = np.isfinite(sq)
s("isfinite ok, count", int(fin.sum()), "of", sq.size)
gt = sq > 0
s("gt ok")
lt = sq < 100.0
s("lt ok")
valid = fin & gt & lt
s("and ok, valid", int(valid.sum()))
mm = np.zeros(sq.shape, dtype=np.uint16)
s("zeros ok")
sel = sq[valid]
s("boolean index ok", sel.shape)
sc = sel * 1000.0
s("mul ok")
r = np.round(sc)
s("round ok")
cl = np.clip(r, 1, 65535)
s("clip ok")
u = cl.astype(np.uint16)
s("astype ok")
mm[valid] = u
s("MASK ASSIGN OK")
s("ALL STEPS PASSED")
PY
