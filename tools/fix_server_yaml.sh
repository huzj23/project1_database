#!/usr/bin/env bash
# server.yaml ended up with TWO samples_per_pixel keys (the repair inserted one
# at the top of the render block while the emptied original remained below it).
# YAML keeps the LAST occurrence, so the effective value was still None.
# Rewrite the render block cleanly.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

SPP="${1:-24}"
"$PY" - "$REPO" "$SPP" <<'PY'
import sys, pathlib, yaml
repo, spp = pathlib.Path(sys.argv[1]), sys.argv[2]

p = repo / "configs/server.yaml"
t = p.read_text()

# drop every samples_per_pixel line, then insert exactly one inside `render:`
lines = [l for l in t.splitlines() if not l.strip().startswith("samples_per_pixel:")]
out, done = [], False
for l in lines:
    out.append(l)
    if l.strip() == "render:" and not done:
        out.append(f"  samples_per_pixel: {spp}")
        done = True
p.write_text("\n".join(out) + "\n")

c = yaml.safe_load(open(p))
print("  samples_per_pixel:", c["render"]["samples_per_pixel"])
print("  device           :", c["render"].get("device"))
print("  compute_backend  :", c["render"].get("compute_backend"))
print("  use_denoising    :", c["render"].get("use_denoising"))
print("  use_adaptive     :", c["render"].get("use_adaptive_sampling"))
print("  blender          :", c["paths"].get("blender_executable"))
print("  phyco_sim_root   :", c["paths"].get("phyco_sim_root"))
PY
