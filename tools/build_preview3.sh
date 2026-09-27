#!/usr/bin/env bash
# ===========================================================================
# Rebuild the preview .blend and stills with the FINAL asset id
# (special_plush_elephant) and pack all textures so the file opens standalone.
#
# The earlier build used the pre-rename id and failed to pack
# assets/objects/gso_sootheze_cold_therapy_elephant/visual/texture.png because that
# directory no longer exists.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"
rm -rf "$OUT"; mkdir -p "$OUT"
ASSET="special_plush_elephant"

cat > /tmp/prev3.py <<'PY'
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
from physim.camera import CameraSpec
from physim.render.blender_backend import PhyCoBlenderBackend

argv = sys.argv[sys.argv.index("--") + 1:]
ASSET, SCEN, SEED = argv[0], argv[1], int(argv[2])
OUT = "/data/raw/huzijian/project1_database/outcomes/_hf_preview"
SAMPLE = f"datasets/{SCEN}/seed-{SEED:06d}/x1"

def states(p):
    return tuple(BodyState(frame=int(i["frame"]), time_seconds=float(i["time_seconds"]),
        position=tuple(float(v) for v in i["position"]),
        quaternion=tuple(float(v) for v in i["quaternion"]),
        linear_velocity=tuple(float(v) for v in i["linear_velocity"]),
        angular_velocity=tuple(float(v) for v in i["angular_velocity"]))
        for i in json.load(open(p)))

am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)
cfg = load_run_config("configs/server.yaml", scenario=f"{SCEN}_gso")
cfg = dict(cfg); cfg["render"] = dict(cfg["render"]); cfg["render"]["samples_per_pixel"] = 24
scen = create_scenario(cfg, asset_manager=am)
v = variants_from_config(cfg)[0]
asset = am.get(ASSET)
smp = scen.sample(seed=SEED, asset=asset, map_spec=ms, variant=v)
cam = CameraSpec(**json.load(open(f"{SAMPLE}/metadata.json"))["camera"])
traj, supp = states(f"{SAMPLE}/trajectory.json"), states(f"{SAMPLE}/support_trajectory.json")
print("PV asset =", asset.asset_id, "category =", asset.category)
print("PV support_material =", getattr(smp, "support_material", None))
print("PV camera =", cam.position, "->", cam.look_at)
one = SimulationResult(trajectory=traj[:1], collisions=(), support_trajectory=supp[:1])
be = PhyCoBlenderBackend("third_party/phyco-sim",
        tempfile.mkdtemp(prefix="pv3_", dir="/data/raw/huzijian/project1_database/tmp"))

# ---- (1) production still + openable blend -------------------------------
built = be.build_scene(smp, one, asset, ms, cam, cfg)
out = be.render(smp, one, asset, ms, cam, cfg)
img = np.asarray(out.rgb)[0].astype(np.uint8)
Image.fromarray(img).save(f"{OUT}/STILL_wide_final.png")
print("PV materials =", (out.diagnostics or {}).get("declared_materials"))
print("PV saved wide still")

# ---- (2) close-up of the actor (quality inspection) ----------------------
p = np.array(traj[0].position, dtype=float)
cam2 = CameraSpec(position=tuple(p + np.array([0.42, -0.50, 0.26])), look_at=tuple(p),
                  focal_length_mm=50.0, framing={"mode": "quality_closeup"})
built2 = be.build_scene(smp, one, asset, ms, cam2, cfg)
out2 = be.render(smp, one, asset, ms, cam2, cfg)
img2 = np.asarray(out2.rgb)[0].astype(np.uint8)
Image.fromarray(img2).save(f"{OUT}/STILL_closeup_final.png")
seg2 = np.asarray(out2.segmentation)[0]
if seg2.ndim == 3: seg2 = seg2[..., 0]
for L in np.unique(seg2).tolist():
    m = (seg2 == L)
    if m.sum() < 200: continue
    px = img2[m].astype(np.float32)
    print(f"PV  closeup L{L}: {100*m.mean():5.1f}% "
          f"R/B={px[:,0].mean()/max(px[:,2].mean(),1e-6):5.2f} "
          f"R/G={px[:,0].mean()/max(px[:,1].mean(),1e-6):5.2f}")
print("PV saved closeup still")

# ---- (3) save + pack the .blend so it opens standalone -------------------
blend = f"{OUT}/replicad_apartment-{ASSET}-preview.blend"
bpy.ops.wm.save_as_mainfile(filepath=blend)
bpy.ops.file.pack_all()
left = [i.filepath for i in bpy.data.images if i.filepath and not i.packed_file]
print(f"PV images={len(bpy.data.images)} still_unpacked={len(left)}")
for x in left[:5]: print("PV   unpacked:", x)
print("PV objects =", [o.name for o in bpy.data.objects])
print("PV lights  =", len([o for o in bpy.data.objects if o.type == 'LIGHT']),
      "worlds =", [w.name for w in bpy.data.worlds])
bpy.ops.wm.save_as_mainfile(filepath=blend)
print("PV blend =", blend, os.path.getsize(blend))
PY

"$WS/tools/conda_env/bin/python" /tmp/prev3.py -- "$ASSET" turntable_spin 5002 2>&1 \
  | grep -aE '^PV|Error|Traceback|RuntimeError' | tail -20 | sed 's/^/  /'

echo
echo "=== outputs ==="
ls -la "$OUT" | sed 's/^/  /'
