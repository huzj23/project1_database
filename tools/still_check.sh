#!/usr/bin/env bash
# ===========================================================================
# (a) MEASURE the still I just rendered, to see whether the disc carries the
#     dark_wood material.  `declared_materials` printed {} which is suspicious: the
#     delivered clips measured R/B 1.94 (wood), so if this still is grey then my
#     still harness differs from generate.py in how support_material is attached.
#     Measure rather than guess.
# (b) Fix the preview .blend build: prepare_sample() resolves
#     configs/scenarios/<scenario>.yaml, and our turntable configs are named
#     turntable_spin_gso / turntable_carry_gso, not turntable_spin.  Pass the real
#     scenario name.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"

echo "=== (a) still vs delivered frame: disc colour ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -12
import glob
import numpy as np
from PIL import Image
OUT = "/data/raw/huzijian/project1_database/outcomes/_hf_preview"
CLIP = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/datasets/turntable_spin/seed-005002/x1"

def disc(img, seg):
    s = np.asarray(Image.open(seg))
    if s.ndim == 3: s = s[..., 0]
    lab = [int(L) for L in np.unique(s) if L != 0]
    if not lab: return None
    L = max(lab, key=lambda l: (s == l).sum()); m = (s == L)
    px = np.asarray(Image.open(img).convert("RGB"), dtype=np.float32)[m]
    r,g,b = px[:,0].mean(), px[:,1].mean(), px[:,2].mean()
    ys,xs = np.nonzero(m)
    return 100*m.mean(), xs.max()-xs.min(), r/max(b,1e-6), r/max(g,1e-6)

# the still has no segmentation layer (single render), so use the clip's seg as a mask proxy
st = disc(f"{OUT}/STILL_turntable_spin_seed5002_final.png", f"{CLIP}/segmentation/0001.png")
print(f"  STILL (my harness)     : area={st[0]:5.1f}% w={st[1]:4.0f}px R/B={st[2]:5.2f} R/G={st[3]:5.2f}")
for i in (1, 41, 81):
    c = disc(f"{CLIP}/rgb/{i:04d}.png", f"{CLIP}/segmentation/{i:04d}.png")
    print(f"  DELIVERED frame {i:3d}   : area={c[0]:5.1f}% w={c[1]:4.0f}px R/B={c[2]:5.2f} R/G={c[3]:5.2f}")
print("  target dark_wood: R/B 1.99 | grey would be R/B 0.99")
PY

echo
echo "=== (b) rebuild the preview .blend with the CORRECT scenario name ==="
SCEN="turntable_spin_gso"
SEED=5002
SAMPLE="datasets/turntable_spin/seed-005002/x1"
BLEND="$OUT/turntable_spin-seed-5002-preview.blend"
"$BLENDER" --background --factory-startup \
  --python scripts/blender_preview_scene.py -- \
  --config configs/server.yaml \
  --scenario "$SCEN" \
  --seed "$SEED" \
  --save-blend "$BLEND" \
  --sample-root "$SAMPLE" 2>&1 | grep -aE 'PHYSIM_PREVIEW|Error|Traceback|FileNotFound|RuntimeError' | tail -6 | cut -c1-400 | sed 's/^/  /'
echo "  blend: $([ -f "$BLEND" ] && echo "OK $(du -h "$BLEND" | cut -f1)" || echo MISSING)"
ls -la "$OUT" | sed 's/^/  /'
