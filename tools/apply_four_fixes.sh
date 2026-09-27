#!/usr/bin/env bash
# Apply the four agreed fixes and produce one free_fall sample:
#   1. bigger drop        -> more of the clip actually shows motion
#   2. open support region -> camera has room, no wall occlusion
#   3. 1920x1080
#   4. frame count matched to the motion instead of a fixed 81
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== 1. swap in the open support region ==="
"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml
repo = pathlib.Path(sys.argv[1])
maps = repo / "configs/maps.yaml"
t = maps.read_text()
snippet = (repo / "configs/_map_replicad_snippet.yaml").read_text()
# replace the whole replicad_apartment block
t = re.sub(r"\n  replicad_apartment:\n(?:    .*\n|      .*\n|        .*\n|          .*\n|            .*\n)+",
           "\n" + snippet.strip("\n") + "\n", t)
maps.write_text(t)
d = yaml.safe_load(open(maps))
reg = d["maps"]["replicad_apartment"]["surface_groups"][0]["regions"][0]
print("  region :", reg["region_id"])
print("  position:", reg["position"])
print("  bounds  :", reg["bounds_xy"])
PY

echo
echo "=== 2. physics + output settings ==="
"$PY" - "$REPO" <<'PY'
import sys, re, pathlib, yaml
repo = pathlib.Path(sys.argv[1])

# --- scenario: bigger drop, frame count matched to the motion ---------------
p = repo / "configs/scenarios/free_fall_gso.yaml"
t = p.read_text()
subs = [
    (r"drop_height_absolute_range:\s*\[[^\]]*\]",
     "drop_height_absolute_range: [1.20, 1.80]"),      # table-height drop
    (r"drop_height_object_extent_range:\s*\[[^\]]*\]",
     "drop_height_object_extent_range: [5.0, 8.0]"),
    (r"min_drop_height:\s*[0-9.]+", "min_drop_height: 0.90"),
    (r"min_drop_distance:\s*[0-9.]+", "min_drop_distance: 1.00"),
    # slow motion: physics stays 240 Hz, video fps halves so the fall spans
    # about twice as many rendered frames
    (r"video_fps:\s*\d+", "video_fps: 8"),
    # clip length matched to the motion rather than a fixed 81
    (r"frame_count:\s*\d+", "frame_count: 48"),
    (r"duration_seconds:\s*[0-9.]+", "duration_seconds: 6.0"),
    (r"max_distance:\s*[0-9.]+", "max_distance: 6.00"),
    (r"trajectory_frame_fraction:\s*[0-9.]+", "trajectory_frame_fraction: 0.70"),
]
for pat, rep in subs:
    t = re.sub(pat, rep, t)
p.write_text(t)

# --- run config: resolution -------------------------------------------------
q = repo / "configs/server.yaml"
s = q.read_text()
s = re.sub(r"^(\s*)resolution:.*$", r"\g<1>resolution: [1920, 1080]", s, flags=re.M)
q.write_text(s)

# --- output resolution lives in the scenario file for this pipeline ---------
o = repo / "configs/scenarios/free_fall_gso.yaml"
t2 = o.read_text()
t2 = re.sub(r"resolution:\s*\[[^\]]*\]", "resolution: [1920, 1080]", t2)
o.write_text(t2)

c = yaml.safe_load(open(p))
print("  drop range   :", c["physics"]["drop_height_absolute_range"])
print("  video_fps    :", c["timing"]["video_fps"], " physics_fps:", c["timing"]["physics_fps"])
print("  frame_count  :", c["timing"]["frame_count"],
      f"({c['timing']['frame_count']/c['timing']['video_fps']:.1f} s)")
print("  resolution   :", c["output"]["resolution"])
print("  modalities   :", c["output"]["modalities"])

import math
d = 1.5
print(f"  expected fall time for {d} m: {math.sqrt(2*d/9.81):.2f} s "
      f"= {math.sqrt(2*d/9.81)*c['timing']['video_fps']:.0f} frames at "
      f"{c['timing']['video_fps']} fps")
PY

echo
echo "=== 3. run ==="
bash "$WS/tools/p1_smoke_final.sh" 2>&1 | tail -26
