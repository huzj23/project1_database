#!/usr/bin/env bash
# ===========================================================================
# Build TWO things the user can inspect, from the SAME scene the pipeline uses:
#
#   (1) a GUI-openable .blend (built by the project's own
#       scripts/blender_preview_scene.py, so it contains the real environment,
#       the real elephant, the real turntable, and the real camera), and
#   (2) a STILL frame rendered at the FINAL production settings
#       (1920x1080, Cycles CPU, 24 spp, denoising, Filmic / Medium High Contrast).
#
# (2) is the decisive quality evidence: it is produced by the exact same renderer
# and settings as the delivered rotation videos, so comparing it to those videos is
# apples-to-apples.  (1) lets the user orbit the scene by hand in Blender.
#
# Both are built on the SERVER with Blender 3.4.1 -- the version the pipeline uses.
# The local Blender is 5.2.2, so a locally built scene would not be the same artifact.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"
mkdir -p "$OUT"

SCEN="turntable_spin"
SEED=5002
ASSET="${1:-gso_sootheze_cold_therapy_elephant}"
SAMPLE="datasets/$SCEN/seed-$(printf '%06d' $SEED)/x1"

echo "=== inputs ==="
echo "  asset       = $ASSET"
echo "  sample root = $SAMPLE"
ls "$SAMPLE" | sed 's/^/    /'
"$WS/tools/conda_env/bin/python" -c "
import json
m=json.load(open('$SAMPLE/metadata.json'))
print('  metadata asset =', m['asset'].get('id') or m['asset'].get('asset_id'))
print('  metadata map   =', m['map'].get('id') or m['map'].get('map_id'))
print('  camera         =', m['camera'].get('position'), '->', m['camera'].get('look_at'))
"

echo
echo "=== (1) build the GUI preview .blend with Blender 3.4.1 ==="
BLEND="$OUT/${SCEN}-seed-${SEED}-preview.blend"
"$BLENDER" --background --factory-startup \
  --python scripts/blender_preview_scene.py -- \
  --config configs/server.yaml \
  --scenario "$SCEN" \
  --seed "$SEED" \
  --save-blend "$BLEND" \
  --sample-root "$SAMPLE" 2>&1 | grep -aE 'PHYSIM_PREVIEW|Error|error|Traceback|Exception' | tail -5 | cut -c1-400 | sed 's/^/  /'
echo "  blend: $([ -f "$BLEND" ] && echo "OK $(du -h "$BLEND" | cut -f1)" || echo MISSING)"

echo
echo "=== (2) render one still at FINAL production settings ==="
cat > /tmp/still_render.py <<'PY'
import sys, json, os
sys.path.insert(0, "src")
import numpy as np
from PIL import Image
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics import SimulationResult, load_simulation_result
from physim.render.blender_backend import PhyCoBlenderBackend

SCEN, SEED = "turntable_spin", 5002
ASSET = sys.argv[sys.argv.index("--") + 1]
SAMPLE = f"datasets/{SCEN}/seed-{SEED:06d}/x1"
OUT = "/data/raw/huzijian/project1_database/outcomes/_hf_preview"

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario=f"{SCEN}_gso")
cfg = dict(cfg); cfg["render"] = dict(cfg["render"])
# FINAL production settings, exactly as the delivered clips
cfg["render"]["samples_per_pixel"] = int(cfg["render"].get("samples_per_pixel", 24))

scen = create_scenario(cfg, asset_manager=am)
v = variants_from_config(cfg)[0]
asset = am.get(ASSET)
smp = scen.sample(seed=SEED, asset=asset, map_spec=ms, variant=v)

# Replay the ALREADY-VALIDATED server trajectory (never re-simulate here).
sim = load_simulation_result(f"{SAMPLE}/trajectory.json", f"{SAMPLE}/collisions.json")
meta = json.load(open(f"{SAMPLE}/metadata.json"))

from physim.camera import CameraSpec
cam = CameraSpec(**meta["camera"])
print("SR asset   =", asset.asset_id, "material=", getattr(asset, "material", None))
print("SR camera  =", cam.position, "->", cam.look_at, "focal", cam.focal_length_mm)
print("SR spp     =", cfg["render"]["samples_per_pixel"], "res=", cfg["render"].get("resolution"))
print("SR frames  =", len(sim.trajectory))

one = SimulationResult(
    trajectory=sim.trajectory[:1],
    collisions=(),
    support_trajectory=sim.support_trajectory[:1] if sim.support_trajectory else None,
)
import tempfile
be = PhyCoBlenderBackend("third_party/phyco-sim", tempfile.mkdtemp(prefix="still_", dir="/data/raw/huzijian/project1_database/tmp"))
out = be.render(smp, one, asset, ms, cam, cfg)
img = np.asarray(out.rgb)[0].astype(np.uint8)
Image.fromarray(img).save(f"{OUT}/STILL_{SCEN}_seed{SEED}_final.png")
print("SR saved   =", f"{OUT}/STILL_{SCEN}_seed{SEED}_final.png", img.shape)
dm = (out.diagnostics or {}).get("declared_materials")
print("SR materials =", dm)
PY
"$WS/tools/conda_env/bin/python" /tmp/still_render.py -- "$ASSET" 2>&1 \
  | grep -aE '^SR |Error|Traceback' | tail -12 | sed 's/^/  /'

echo
echo "=== outputs ==="
ls -la "$OUT" | sed 's/^/  /'
