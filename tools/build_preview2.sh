#!/usr/bin/env bash
# ===========================================================================
# Build the preview .blend AND a final-quality still, CORRECTLY.
#
# ROOT CAUSE of the earlier failures: src/physim/physics/__init__.py's
# load_simulation_result() reads only trajectory.json + collisions.json.  It never
# reads support_trajectory.json, so SimulationResult.support_trajectory stays empty.
# Consequences:
#   * scripts/blender_preview_scene.py fails the turntable with
#     "disc_did_not_rotate, not_carried_by_contact" (it re-validates a disc that
#     never turns), and
#   * my first still built NO disc at all, so the pixels I measured as "the disc"
#     were really the table/floor (neutral R/B 1.03).
#
# This harness loads the support trajectory explicitly, replays the ALREADY-VALIDATED
# server trajectory (never re-simulating), saves an openable .blend, and renders a
# still WITH segmentation so the disc can be measured by its own label.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"
mkdir -p "$OUT"
ASSET="${1:-gso_sootheze_cold_therapy_elephant}"

cat > /tmp/prev2.py <<'PY'
import sys, os, json, tempfile
sys.path.insert(0, "src")
import numpy as np
from PIL import Image
import bpy

from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics import SimulationResult, BodyState
from physim.physics.pybullet_backend import PyBulletBackend
from physim.camera import CameraSpec
from physim.render.blender_backend import PhyCoBlenderBackend

argv = sys.argv[sys.argv.index("--") + 1:]
ASSET, SCEN, SEED = argv[0], argv[1], int(argv[2])
OUT = "/data/raw/huzijian/project1_database/outcomes/_hf_preview"
SAMPLE = f"datasets/{SCEN}/seed-{SEED:06d}/x1"

def load_states(path):
    return tuple(BodyState(
        frame=int(i["frame"]), time_seconds=float(i["time_seconds"]),
        position=tuple(float(v) for v in i["position"]),
        quaternion=tuple(float(v) for v in i["quaternion"]),
        linear_velocity=tuple(float(v) for v in i["linear_velocity"]),
        angular_velocity=tuple(float(v) for v in i["angular_velocity"]),
    ) for i in json.load(open(path)))

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario=f"{SCEN}_gso")
cfg = dict(cfg); cfg["render"] = dict(cfg["render"])
cfg["render"]["samples_per_pixel"] = 24          # FINAL production setting

scen = create_scenario(cfg, asset_manager=am)
v = variants_from_config(cfg)[0]
asset = am.get(ASSET)
smp = scen.sample(seed=SEED, asset=asset, map_spec=ms, variant=v)
meta = json.load(open(f"{SAMPLE}/metadata.json"))
cam = CameraSpec(**meta["camera"])

# Replay the validated server trajectory, INCLUDING the support body.
traj = load_states(f"{SAMPLE}/trajectory.json")
supp = load_states(f"{SAMPLE}/support_trajectory.json") if os.path.isfile(f"{SAMPLE}/support_trajectory.json") else ()
print("PV frames =", len(traj), "support =", len(supp))
print("PV asset  =", asset.asset_id, "material =", getattr(asset, "material", None))
print("PV sample support_material =", getattr(smp, "support_material", None))
print("PV camera =", cam.position, "->", cam.look_at, "focal", cam.focal_length_mm)
print("PV spp    =", cfg["render"]["samples_per_pixel"])

one = SimulationResult(trajectory=traj[:1], collisions=(), support_trajectory=supp[:1])
be = PhyCoBlenderBackend("third_party/phyco-sim",
                         tempfile.mkdtemp(prefix="pv2_", dir="/data/raw/huzijian/project1_database/tmp"))
built = be.build_scene(smp, one, asset, ms, cam, cfg)
print("PV built  =", type(built).__name__)

# Save an openable .blend BEFORE rendering, so the GUI artifact is the real scene.
blend = f"{OUT}/{SCEN}-seed-{SEED}-preview.blend"
bpy.ops.wm.save_as_mainfile(filepath=blend)
print("PV blend  =", blend, os.path.getsize(blend))

out = be.render(smp, one, asset, ms, cam, cfg)
img = np.asarray(out.rgb)[0].astype(np.uint8)
Image.fromarray(img).save(f"{OUT}/STILL_{SCEN}_seed{SEED}_final.png")
seg = np.asarray(out.segmentation)[0]
if seg.ndim == 3: seg = seg[..., 0]
print("PV materials =", (out.diagnostics or {}).get("declared_materials"))
print("PV labels    =", np.unique(seg).tolist())
for L in np.unique(seg).tolist():
    m = (seg == L)
    if m.sum() < 200: continue
    px = img[m].astype(np.float32)
    r,g,b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
    ys,xs = np.nonzero(m)
    print(f"PV  L{L}: {100*m.mean():5.1f}% w={xs.max()-xs.min():4d} "
          f"R/B={r/max(b,1e-6):5.2f} R/G={r/max(g,1e-6):5.2f}")
PY

"$WS/tools/conda_env/bin/python" /tmp/prev2.py -- "$ASSET" turntable_spin 5002 2>&1 \
  | grep -aE '^PV|Error|Traceback|RuntimeError' | tail -20 | sed 's/^/  /'

echo
echo "=== outputs ==="
ls -la "$OUT" | sed 's/^/  /'
