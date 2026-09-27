#!/usr/bin/env bash
# Minimal turntable probe: load both bodies, print their PyBullet ids, step a few
# frames, and report exactly where it dies.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
cd "$WS/code/vendor/phyco-sim" || exit 1

"$PY" -u - "$WS" <<'PY' 2>&1
import sys, os, json, tempfile, traceback
WS = sys.argv[1]
sys.path.insert(0, os.path.join(os.getcwd(), "kubric"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
sys.path.insert(0, os.path.join(WS, "code/scenarios"))
import numpy as np
import kubric as kb
import phyco_common as pc
pc.patch_numpy_legacy_aliases()
from kubric.simulator import PyBullet
from kubric.renderer import Blender
import pybullet as pbc

GSO = os.path.join(WS, "models/gso/Sootheze_Cold_Therapy_Elephant")
TT = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/objects/turntable")

try:
    scratch = tempfile.mkdtemp(prefix="ttm_")
    scene = kb.Scene(resolution=(64, 64), frame_start=0, frame_end=10,
                     frame_rate=24, step_rate=240, gravity=(0, 0, -9.81))
    renderer = Blender(scene, scratch, samples_per_pixel=1, use_denoising=False, verbose=True)
    sim = PyBullet(scene, scratch)
    print("STEP renderer ok")

    ground = kb.Cube(name="ground", scale=(4, 4, 0.1), position=(0, 0, -0.1), static=True)
    scene += ground
    print("STEP ground ok")

    disc = kb.FileBasedObject(
        name="turntable", asset_id="turntable",
        simulation_filename=os.path.join(TT, "collision/model.urdf"),
        render_filename=os.path.join(TT, "visual/model.obj"),
        scale=(1.0, 1.0, 1.0), static=True, position=(0, 0, 0.035),
        segmentation_id=3)
    scene += disc
    print("STEP disc ok")

    meta = json.load(open(os.path.join(GSO, "data.json")))
    b = meta["kwargs"]["bounds"]; rest = -b[0][2]
    obj = kb.FileBasedObject(
        name="actor", simulation_filename=os.path.join(GSO, "object.urdf"),
        render_filename=os.path.join(GSO, "visual_geometry.obj"),
        bounds=tuple(tuple(v) for v in b), mass=meta["kwargs"]["mass"],
        scale=1.0, position=(0.30, 0.0, 0.05 + rest), segmentation_id=2)
    scene += obj
    print("STEP actor ok")

    print("  disc.linked_objects =", disc.linked_objects)
    print("  obj.linked_objects  =", obj.linked_objects)
    did = disc.linked_objects.get(sim)
    oid = obj.linked_objects.get(sim)
    print(f"  did={did!r}  oid={oid!r}")

    if did is None or oid is None:
        print("STEP a body id is None -- cannot proceed")
        raise SystemExit(1)

    print("  disc dynamics:", pbc.getDynamicsInfo(did, -1))
    print("  actor dynamics:", pbc.getDynamicsInfo(oid, -1))

    pbc.changeDynamics(did, -1, mass=0, lateralFriction=1.2)
    print("STEP changeDynamics ok")

    for f in range(24):
        pbc.resetBaseVelocity(did, [0, 0, 0], [0, 0, 1.2])
        sim.step()
    print("STEP stepping ok")

    p, q = pbc.getBasePositionAndOrientation(oid)
    print(f"  after 24 steps actor at {tuple(round(v,3) for v in p)}")
    print("STEP ALL OK")
except SystemExit:
    raise
except BaseException:
    traceback.print_exc()
    print("STEP FAILED")
PY
