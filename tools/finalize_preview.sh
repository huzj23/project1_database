#!/usr/bin/env bash
# ===========================================================================
# Make the preview .blend usable on the user's own machine, and PROVE the still is
# the same render as the delivered video.
#
# (1) PIXEL PROOF: the still was rendered at production settings (1920x1080, Cycles
#     CPU, 24 spp, denoising) from frame 0 of the same validated trajectory and the
#     same camera as the delivered clip, so it should be near-identical to the
#     delivered rgb_00000.png.  Measure the difference instead of asserting it.
# (2) The .blend references the elephant's texture.png externally; pack everything so
#     the file opens standalone in the user's Blender (their local build is 5.2.2, the
#     scene was authored in 3.4.1 -- older files open fine, but missing textures would
#     not).
# (3) Also render a CLOSE-UP of the elephant, because at ~15% of frame the actor is
#     small and render quality is hard to judge from the wide shot.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"
SAMPLE="datasets/turntable_spin/seed-005002/x1"

echo "=== (1) PIXEL PROOF: my still vs the delivered video's frame 0 ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -14
import numpy as np
from PIL import Image
OUT = "/data/raw/huzijian/project1_database/outcomes/_hf_preview"
CLIP = ("/data/raw/huzijian/project1_database/code/physics-video-sim/"
        "physics-video-sim-main/datasets/turntable_spin/seed-005002/x1")
a = np.asarray(Image.open(f"{OUT}/STILL_turntable_spin_seed5002_final.png").convert("RGB"), dtype=np.float32)
b = np.asarray(Image.open(f"{CLIP}/rgb/rgb_00000.png").convert("RGB"), dtype=np.float32)
print(f"  shapes: still={a.shape} delivered={b.shape}")
d = np.abs(a - b)
print(f"  mean abs diff   = {d.mean():.3f} / 255")
print(f"  max  abs diff   = {d.max():.0f}")
print(f"  pixels >6/255   = {100*(d.max(axis=2) > 6).mean():.3f}%")
print(f"  pixels >16/255  = {100*(d.max(axis=2) > 16).mean():.3f}%")
# where do they differ, if at all?
if (d.max(axis=2) > 16).sum() > 0:
    ys, xs = np.nonzero(d.max(axis=2) > 16)
    print(f"  differing region: x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}]")
PY

echo
echo "=== (2) pack the .blend so it opens standalone ==="
cat > /tmp/pack.py <<'PY'
import bpy, sys, os
blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=blend)
print("PK objects:", [(o.name, o.type) for o in bpy.data.objects][:12])
print("PK collections:", [c.name for c in bpy.data.collections])
ext = [i.filepath for i in bpy.data.images if i.filepath and not i.packed_file]
print(f"PK images={len(bpy.data.images)} unpacked_before={len(ext)}")
for p in ext[:6]:
    print("PK   external:", p)
bpy.ops.file.pack_all()
still = [i.filepath for i in bpy.data.images if i.filepath and not i.packed_file]
print(f"PK unpacked_after={len(still)}")
# sanity: lights + world survived
lights = [o.name for o in bpy.data.objects if o.type == "LIGHT"]
print(f"PK lights={len(lights)} worlds={[w.name for w in bpy.data.worlds]}")
print(f"PK meshes={len([o for o in bpy.data.objects if o.type=='MESH'])}")
bpy.ops.wm.save_as_mainfile(filepath=blend)
print("PK saved:", blend, os.path.getsize(blend))
PY
"$BLENDER" --background --factory-startup --python /tmp/pack.py -- "$OUT/turntable_spin-seed-5002-preview.blend" 2>&1 \
  | grep -aE '^PK|Error|Traceback' | sed 's/^/  /'

echo
echo "=== (3) close-up still of the elephant (quality inspection) ==="
cat > /tmp/closeup.py <<'PY'
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
SAMPLE = "datasets/turntable_spin/seed-005002/x1"
def load_states(p):
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
asset = am.get("gso_sootheze_cold_therapy_elephant")
smp = scen.sample(seed=5002, asset=asset, map_spec=ms, variant=v)
traj = load_states(f"{SAMPLE}/trajectory.json")
supp = load_states(f"{SAMPLE}/support_trajectory.json")
one = SimulationResult(trajectory=traj[:1], collisions=(), support_trajectory=supp[:1])

# Close-up: orbit in toward the actor's own position.
p = np.array(traj[0].position, dtype=float)
cam_pos = p + np.array([0.55, -0.62, 0.34])
cam = CameraSpec(position=tuple(cam_pos), look_at=tuple(p), focal_length_mm=50.0,
                 framing={"mode": "quality_closeup"})
print("CU actor pos =", p.round(4).tolist())
print("CU camera    =", cam_pos.round(4).tolist(), "dist", round(float(np.linalg.norm(cam_pos-p)), 4))
be = PhyCoBlenderBackend("third_party/phyco-sim",
        tempfile.mkdtemp(prefix="cu_", dir="/data/raw/huzijian/project1_database/tmp"))
out = be.render(smp, one, asset, ms, cam, cfg)
img = np.asarray(out.rgb)[0].astype(np.uint8)
Image.fromarray(img).save(f"{OUT}/CLOSEUP_elephant_final.png")
seg = np.asarray(out.segmentation)[0]
if seg.ndim == 3: seg = seg[..., 0]
for L in np.unique(seg).tolist():
    m = (seg == L)
    if m.sum() < 200: continue
    px = img[m].astype(np.float32)
    r,g,b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
    print(f"CU  L{L}: {100*m.mean():5.1f}% R/B={r/max(b,1e-6):5.2f} R/G={r/max(g,1e-6):5.2f}")
print("CU saved")
PY
"$WS/tools/conda_env/bin/python" /tmp/closeup.py 2>&1 | grep -aE '^CU|Error|Traceback' | sed 's/^/  /'

echo
echo "=== outputs ==="
ls -la "$OUT" | sed 's/^/  /'
