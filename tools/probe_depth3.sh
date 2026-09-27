#!/usr/bin/env bash
# The standalone depth probe passes; the runner fails. The remaining difference
# is ORDER -- the runner prepares rgba and segmentation before depth. Test that.
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -X faulthandler - <<'PY' 2>&1 | grep -E '^STEP|^Fatal|phyco_common|Segmentation'
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

scratch = pc.tempfile.mkdtemp(prefix="probe3_")
n = 4
scene = kb.Scene(resolution=(320, 180), frame_start=0, frame_end=n-1,
                 frame_rate=24, step_rate=240, gravity=(0, 0, 0))
renderer = Blender(scene, scratch, samples_per_pixel=8, use_denoising=True, verbose=True)
sim = PyBullet(scene, scratch)
pc.add_ground(kb, scene, size=3.5)
a = pc.get_asset("ball")
obj = kb.FileBasedObject(name="ball", simulation_filename=a.urdf_path,
                         render_filename=a.obj_path, scale=0.3,
                         position=(0.0, 0.0, 0.9), segmentation_id=2)
scene += obj
pc.add_lighting(kb, scene)
pc.set_background(renderer, scene)
import phyco_motions as pm
pm.apply_circular(kb, obj, pm.CircularSpec(radius=1.2, period_s=2.0,
                  center=(0, 0, 0.9), axis="z"), n, 24.0, [0.0, 0.0, 0.3])
pc.auto_frame_camera(kb, scene, [[1.2, 0, 0.9 + dz] for dz in (-0.06, 0.06)],
                     (0, 0, 0.9), margin=0.12, start_distance=5.0)
s("scene ok")

out = renderer.render(list(range(n)), return_layers=("rgba", "segmentation", "depth"))
out = {k: np.array(v, copy=True) for k, v in out.items()}
s("render + copy ok", sorted(out.keys()))

# --- mimic the runner's exact ordering ---
s("preparing rgba ...")
pr = pc.prepare_rgba(out["rgba"])
s("  rgba ok", pr.shape, pr.dtype)
s("preparing segmentation ...")
ps = pc.prepare_segmentation(out["segmentation"])
s("  seg ok", ps.shape, ps.dtype)
s("preparing depth ...")
pd = pc.prepare_depth_mm(out["depth"])
s("  depth ok", pd.shape, pd.dtype)
s("ALL PREPARED")
PY
