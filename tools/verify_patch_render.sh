#!/usr/bin/env bash
# ===========================================================================
# PROVE the material patch did not change the rendered look.
#
# The turntable now resolves dark_wood from the ASSET-LOCAL copy instead of the
# shared library.  The files are byte-identical, but confirm by rendering the same
# frame and measuring the disc, and comparing against the delivered clip.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"

echo "=== 1. are the asset-local maps byte-identical to the shared originals? ==="
SRC="$WS/models/pbr_textures/wood_textures/dark_wood.blend/textures"
DST="$REPO/assets/objects/turntable/visual/textures/dark_wood"
for f in dark_wood_diff_4k.jpg dark_wood_rough_4k.jpg dark_wood_nor_gl_4k.jpg; do
  a=$(sha256sum "$SRC/$f" | cut -d' ' -f1)
  b=$(sha256sum "$DST/$f" | cut -d' ' -f1)
  [ "$a" = "$b" ] && echo "  IDENTICAL $f" || echo "  DIFFERENT $f"
done

echo
echo "=== 2. re-render the same frame and measure the disc ==="
cat > /tmp/recheck.py <<'PY'
import sys, os, json, tempfile
sys.path.insert(0, "src")
import numpy as np
from PIL import Image
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics import SimulationResult, BodyState
from physim.camera import CameraSpec
from physim.render.blender_backend import PhyCoBlenderBackend

OUT = "/data/raw/huzijian/project1_database/outcomes/_hf_preview"
S = "datasets/turntable_spin/seed-005002/x1"
def st(p):
    return tuple(BodyState(frame=int(i["frame"]), time_seconds=float(i["time_seconds"]),
        position=tuple(float(v) for v in i["position"]),
        quaternion=tuple(float(v) for v in i["quaternion"]),
        linear_velocity=tuple(float(v) for v in i["linear_velocity"]),
        angular_velocity=tuple(float(v) for v in i["angular_velocity"]))
        for i in json.load(open(p)))
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario="turntable_spin_gso")
cfg = dict(cfg); cfg["render"] = dict(cfg["render"]); cfg["render"]["samples_per_pixel"] = 24
scen = create_scenario(cfg, asset_manager=am)
v = variants_from_config(cfg)[0]
asset = am.get("special_plush_elephant")
smp = scen.sample(seed=5002, asset=asset, map_spec=ms, variant=v)
cam = CameraSpec(**json.load(open(f"{S}/metadata.json"))["camera"])
one = SimulationResult(trajectory=st(f"{S}/trajectory.json")[:1], collisions=(),
                       support_trajectory=st(f"{S}/support_trajectory.json")[:1])
be = PhyCoBlenderBackend("third_party/phyco-sim",
        tempfile.mkdtemp(prefix="rc_", dir="/data/raw/huzijian/project1_database/tmp"))
out = be.render(smp, one, asset, ms, cam, cfg)
img = np.asarray(out.rgb)[0].astype(np.uint8)
Image.fromarray(img).save(f"{OUT}/STILL_wide_after_patch.png")
print("RC materials =", (out.diagnostics or {}).get("declared_materials"))
seg = np.asarray(out.segmentation)[0]
if seg.ndim == 3: seg = seg[..., 0]
for L in np.unique(seg).tolist():
    m = (seg == L)
    if m.sum() < 200: continue
    px = img[m].astype(np.float32)
    r,g,b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
    print(f"RC  L{L}: {100*m.mean():5.1f}% w={np.nonzero(m)[1].max()-np.nonzero(m)[1].min():4d} "
          f"R/B={r/max(b,1e-6):5.2f} R/G={r/max(g,1e-6):5.2f}")
# compare to the delivered clip frame 0
d = np.asarray(Image.open(f"{S}/rgb/rgb_00000.png").convert("RGB"), dtype=np.float32)
diff = np.abs(img.astype(np.float32) - d)
print(f"RC vs delivered frame0: mean={diff.mean():.3f} max={diff.max():.0f} "
      f"px>6={100*(diff.max(axis=2)>6).mean():.3f}%")
PY
"$WS/tools/conda_env/bin/python" /tmp/recheck.py 2>&1 \
  | grep -aE '^RC|Error|Traceback' | sed 's/^/  /'
