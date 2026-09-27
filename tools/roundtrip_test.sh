#!/usr/bin/env bash
# ===========================================================================
# DECISIVE ROUND-TRIP TEST (corrected).
#
# Build a pristine project tree containing ONLY what the HF download provides, plus a
# minimal registry, and confirm every asset loads AND the turntable's PBR material
# resolves with no shared texture library anywhere. This is exactly a teammate's
# situation after `git clone` + `sync_hf_assets.py download`.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
D="$WS/tmp/fresh_dl"

echo "=== 1. the registry the pipeline actually uses ==="
cat configs/assets.yaml | sed 's/^/  /'

echo
echo "=== 2. plant that registry in the fresh tree ==="
mkdir -p "$D/configs"
cp configs/assets.yaml "$D/configs/assets.yaml"
echo "  copied registry -> $D/configs/assets.yaml"

echo
echo "=== 3. the shared texture library must NOT be reachable from the fresh tree ==="
echo "  fresh tree is: $D"
echo "  default PBR root would be: $(dirname $(dirname $(dirname $D)))/models/pbr_textures"
ls -d "$(dirname $(dirname $(dirname $D)))/models/pbr_textures" 2>/dev/null \
  && echo "  ^ EXISTS (so also test with it hidden)" || echo "  does not exist"

echo
echo "=== 4. load every downloaded asset (shared library HIDDEN) ==="
SHARED="$WS/models/pbr_textures"; HIDDEN="$WS/tmp/pbr_hidden3"
rm -rf "$HIDDEN"; mv "$SHARED" "$HIDDEN"; echo "  shared library hidden"
"$PY" - <<PY 2>&1 | grep -aE '^FL|Error' | sed 's/^/  /'
import sys, os
sys.path.insert(0, "$REPO/src")
from physim.assets import AssetManager
from physim.render.materials import find_texture_dir, resolve_pbr_root
D = "$D"
am = AssetManager(f"{D}/configs/assets.yaml", f"{D}/assets")
print("FL discovered:", len(am.ids), "assets:", sorted(am.ids))
for aid in ("special_plush_elephant", "replicad_apartment", "turntable"):
    try:
        a = am.get(aid)
        print(f"FL {aid}: OK category={a.category} visual={os.path.basename(str(a.visual_path))}")
        print(f"FL    collision={a.collision.collision_type} support_height={a.support_height}")
        if a.material:
            print(f"FL    material pbr={a.material.pbr} textures={a.material.textures}")
    except Exception as e:
        print(f"FL {aid}: {type(e).__name__}: {e}")
print("FL shared pbr root exists:", resolve_pbr_root(f"{D}/configs").is_dir())
t = am.get("turntable")
d = find_texture_dir(f"{D}/configs", "dark_wood", "wood_textures", t.material)
print("FL turntable texture_dir ->", d)
if d: print("FL files:", sorted(os.listdir(d)))
PY
mv "$HIDDEN" "$SHARED"; echo "  shared library restored"

echo
echo "=== 5. RENDER the downloaded elephant+apartment, shared library still hidden ==="
SHARED="$WS/models/pbr_textures"; HIDDEN="$WS/tmp/pbr_hidden4"
rm -rf "$HIDDEN"; mv "$SHARED" "$HIDDEN"
cat > /tmp/fresh_render.py <<PY
import sys, os, json, tempfile
sys.path.insert(0, "$REPO/src")
import numpy as np
from PIL import Image
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios.turntable import TurntableScenario
from physim.physics import SimulationResult, BodyState
from physim.camera import CameraSpec
from physim.render.blender_backend import PhyCoBlenderBackend
from physim.config import load_run_config

D = "$D"
S = "$REPO/datasets/turntable_spin/seed-005002/x1"
def st(p):
    return tuple(BodyState(frame=int(i["frame"]), time_seconds=float(i["time_seconds"]),
        position=tuple(float(v) for v in i["position"]),
        quaternion=tuple(float(v) for v in i["quaternion"]),
        linear_velocity=tuple(float(v) for v in i["linear_velocity"]),
        angular_velocity=tuple(float(v) for v in i["angular_velocity"]))
        for i in json.load(open(p)))
am = AssetManager(f"{D}/configs/assets.yaml", f"{D}/assets")
mm = MapManager("$REPO/configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("$REPO/configs/server.yaml", scenario="turntable_spin_gso")
cfg = dict(cfg); cfg["render"] = dict(cfg["render"]); cfg["render"]["samples_per_pixel"] = 24
scen = TurntableScenario(cfg, asset_manager=am)
from physim.scenarios import variants_from_config
v = variants_from_config(cfg)[0]
a = am.get("special_plush_elephant")
smp = scen.sample(seed=5002, asset=a, map_spec=ms, variant=v)
cam = CameraSpec(**json.load(open(f"{S}/metadata.json"))["camera"])
one = SimulationResult(trajectory=st(f"{S}/trajectory.json")[:1], collisions=(),
                       support_trajectory=st(f"{S}/support_trajectory.json")[:1])
be = PhyCoBlenderBackend("$REPO/third_party/phyco-sim",
        tempfile.mkdtemp(prefix="fr_", dir="$WS/tmp"))
out = be.render(smp, one, a, ms, cam, cfg)
img = np.asarray(out.rgb)[0].astype(np.uint8)
Image.fromarray(img).save("$WS/outcomes/_hf_preview/STILL_fresh_download.png")
print("FR materials =", (out.diagnostics or {}).get("declared_materials"))
seg = np.asarray(out.segmentation)[0]
if seg.ndim == 3: seg = seg[..., 0]
for L in np.unique(seg).tolist():
    m = (seg == L)
    if m.sum() < 200: continue
    px = img[m].astype(np.float32)
    print(f"FR  L{L}: {100*m.mean():5.1f}% R/B={px[:,0].mean()/max(px[:,2].mean(),1e-6):5.2f} "
          f"R/G={px[:,0].mean()/max(px[:,1].mean(),1e-6):5.2f}")
d = np.asarray(Image.open(f"{S}/rgb/rgb_00000.png").convert("RGB"), dtype=np.float32)
diff = np.abs(img.astype(np.float32) - d)
print(f"FR vs delivered: mean={diff.mean():.3f} max={diff.max():.0f} px>6={100*(diff.max(axis=2)>6).mean():.3f}%")
PY
"$PY" /tmp/fresh_render.py 2>&1 | grep -aE '^FR|Error|Traceback|FileNotFound' | sed 's/^/  /'
mv "$HIDDEN" "$SHARED"; echo "  shared library restored: $([ -d "$SHARED" ] && echo YES || echo NO)"
