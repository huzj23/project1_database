#!/usr/bin/env bash
# Point the environment manifest at the .blend (which carries materials AND the
# 7 authored ceiling lights) instead of the GLB, then re-run.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml
repo = pathlib.Path(sys.argv[1])
p = repo / "assets/environments/replicad_apartment/asset.yaml"
t = p.read_text()
t = re.sub(r"mesh:\s*visual/scene\.glb", "mesh: visual/scene.blend", t)
if "object_name" not in t:
    t = re.sub(r"(mesh: visual/scene\.blend)", r"\1\n  object_name: environment", t)
# declare that lighting comes from the authored config inside the blend
if "lighting_source" not in t:
    t = t.replace("allowed_scenarios:",
                  "render:\n  lighting_source: authored_blend\n  authored_lights: 7\n"
                  "  note: lights are baked into scene.blend; add none in scripts\n\n"
                  "allowed_scenarios:", 1)
p.write_text(t)
c = yaml.safe_load(open(p))
print("  visual      :", c.get("visual"))
print("  render      :", c.get("render"))
print("  collision   :", {k: v for k, v in (c.get("collision") or {}).items()
                          if k in ("type", "center", "half_extents")})
PY

echo
echo "=== run ==="
bash "$WS/tools/p1_smoke_final.sh" 2>&1 | tail -28
