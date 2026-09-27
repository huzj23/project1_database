#!/usr/bin/env bash
# ===========================================================================
# (a) Archive size planning for the share folder (must stay under 50 MB).
# (b) Re-do the upstream diff against the SERVER tree.
#
# Why (b): the V3.7 subagent diffed a STALE LOCAL checkout and concluded that
# setTimeStep does not exist, that physics_fps 560 is rejected, and that
# scenarios/damping.py is missing.  All three are FALSE on the server, which is the
# tree that actually produced our videos.  So the authoritative diff must be taken
# from the server, with the pristine upstream zip as the baseline.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== sizes: what would go in the share archive ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import glob, os, json
REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
tot_v = tot_j = 0
rows = []
for d in sorted(glob.glob(REPO + "/datasets/*/seed-*/x1")):
    if len(glob.glob(d + "/rgb/*.png")) == 0:
        continue
    mp4 = d + "/video.mp4"
    if not os.path.isfile(mp4):
        continue
    sv = os.path.getsize(mp4)
    sj = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)
             if f.endswith(".json"))
    rows.append((d.replace(REPO + "/datasets/", ""), sv, sj))
    tot_v += sv; tot_j += sj
for rel, sv, sj in rows:
    print(f"  {rel:40s} video={sv/1e6:6.2f} MB  json={sj/1e3:7.1f} KB")
print(f"\n  videos total = {tot_v/1e6:.2f} MB   json total = {tot_j/1e3:.1f} KB")
print(f"  => raw ~{(tot_v+tot_j)/1e6:.2f} MB; mp4 is already compressed, so the zip")
print(f"     will be about the same. Budget is 50 MB.")
PY

echo
echo "=== is the pristine upstream zip present? ==="
ls -la "$WS/code/"*.zip 2>/dev/null | sed 's/^/  /'
find "$WS" -maxdepth 3 -name 'physics-video-sim*.zip' 2>/dev/null | sed 's/^/  /'
ls -d "$WS/tmp/upstream_physics_video_sim" 2>/dev/null | sed 's/^/  /' || echo "  no extracted upstream in tmp/"

echo
echo "=== SERVER truth: the three disputed items ==="
echo "  setTimeStep calls: $(grep -c 'setTimeStep' src/physim/physics/pybullet_backend.py) occurrence(s)"
grep -n 'setTimeStep' src/physim/physics/pybullet_backend.py | sed 's/^/    /'
echo "  physics_fps guard:"
grep -n 'physics_fps < 240\|physics_fps != 240' src/physim/physics/pybullet_backend.py | sed 's/^/    /'
echo "  damping.py: $([ -f src/physim/scenarios/damping.py ] && echo EXISTS || echo MISSING)"
echo "  projectile_gso.yaml: $([ -f configs/scenarios/projectile_gso.yaml ] && echo EXISTS || echo MISSING)"
