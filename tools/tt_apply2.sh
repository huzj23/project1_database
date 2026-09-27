#!/usr/bin/env bash
# ===========================================================================
# Apply the two requested changes with PRECISE line-range surgery.
#
# My previous attempt used a regex that swallowed the wrong span and corrupted the
# file; the .pre_eleph backups restored it.  This version replaces the exact
# [camera block] and [asset_ids list] line ranges, then re-parses the YAML to
# prove the structure survived.
#
# (a) CAMERA = the pose the user already approved (tools/tt_on_table.sh):
#       cam  = table_top + (0.52, -0.66, +0.42)
#       look = table_top + (0, 0, +0.05), focal 50 mm
#     table_top = (0.414, 0.175, 0.7584)  [V3.2 freeze record]
#     => cam = (0.934, -0.485, 1.1784), look = (0.414, 0.175, 0.8084)
#     Uses the new `fixed` policy: `trajectory_side` derives the pose from each
#     clip's motion, so it cannot reproduce an approved framing.
#
# (b) ACTOR = the elephant ("小熊"), as requested.  It is a plush toy and is
#     excluded from the impulsive motions (constant_force / free_fall /
#     projectile) because we have no soft-body adaptation, but a turntable ride
#     is quasi-static and was already validated on the disc (slip 1.00,
#     r_max 0.107 m), so it is a legitimate actor here.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY'
import re, yaml

CAMERA = """camera:
  # ---------------------------------------------------------------------
  # APPROVED POSE -- copied from tools/tt_on_table.sh, the turntable render
  # the user accepted.  Written relative to the frozen table top
  # (0.414, 0.175, 0.7584):
  #     cam  = top + (0.52, -0.66, +0.42) = (0.9340, -0.4850, 1.1784)
  #     look = top + (0.00,  0.00, +0.05) = (0.4140,  0.1750, 0.8084)
  #     focal 50 mm, sensor 36 mm
  # `fixed` is required: the previous `trajectory_side` policy DERIVES the pose
  # from each clip's own motion, so it cannot reproduce a pose that was reviewed
  # and signed off.  `fixed` uses this pose verbatim and injects no azimuth or
  # side randomness (see fixed_camera in src/physim/camera/__init__.py).
  # ---------------------------------------------------------------------
  policy: fixed
  position: [0.9340, -0.4850, 1.1784]
  look_at: [0.4140, 0.1750, 0.8084]
  focal_length_mm: 50.0
  framing:
    sensor_width_mm: 36.0
"""

def replace_block(lines, start_key, next_key, new_text):
    """Replace lines from `start_key:` up to (not incl.) `next_key:`."""
    s = e = None
    for i, ln in enumerate(lines):
        if ln.rstrip("\n") == start_key:
            s = i
        elif s is not None and ln.rstrip("\n") == next_key:
            e = i
            break
    assert s is not None and e is not None, f"{start_key} block not found"
    return lines[:s] + [new_text] + lines[e:]

for name in ("turntable_carry_gso", "turntable_spin_gso"):
    path = f"configs/scenarios/{name}.yaml"
    lines = open(path).readlines()

    # (a) camera block
    lines = replace_block(lines, "camera:", "output:", CAMERA)

    # (b) actor list: drop every entry under `asset_ids:` and write the elephant
    out, i, done = [], 0, False
    while i < len(lines):
        ln = lines[i]
        if ln.rstrip("\n") == "  asset_ids:":
            out.append(ln)
            out.append("    - gso_sootheze_cold_therapy_elephant\n")
            i += 1
            while i < len(lines) and re.match(r"^\s+-\s", lines[i]):
                i += 1
            done = True
            continue
        out.append(ln)
        i += 1
    assert done, f"asset_ids not found in {path}"
    lines = out
    open(path, "w").writelines(lines)

    d = yaml.safe_load(open(path))
    assert d["camera"]["policy"] == "fixed", path
    assert d["camera"]["position"] == [0.9340, -0.4850, 1.1784], path
    assert d["selection"]["asset_ids"] == ["gso_sootheze_cold_therapy_elephant"], path
    print(f"  {name}: OK  keys={list(d.keys())}")
    print(f"    camera={d['camera']['policy']} pos={d['camera']['position']} "
          f"look={d['camera']['look_at']} focal={d['camera']['focal_length_mm']}")
    print(f"    actor={d['selection']['asset_ids']}")
PY

echo
echo "=== config loads through the real loader ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import sys
sys.path.insert(0, "src")
from physim.config import load_run_config
for n in ("turntable_carry_gso", "turntable_spin_gso"):
    c = load_run_config("configs/server.yaml", scenario=n)
    print(f"  {n}: scenario={c.get('scenario')} camera_policy={c['camera']['policy']}")
PY
