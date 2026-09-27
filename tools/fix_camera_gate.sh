#!/usr/bin/env bash
# ===========================================================================
# Fix the camera gate and build a preflight that INCLUDES the camera solver.
#
# The mentor's own three configs all use min_object_frame_fraction: 0.03; I had
# set 0.10, three times stricter, so a long trajectory (which inflates
# content_width) pushed the projected fraction to 0.0907 and raised
#     "A static camera cannot fit the complete trajectory while keeping the
#      largest object visible: projected fraction 0.0907, minimum 0.1000"
#
# IMPORTANT: from camera/__init__.py the chosen distance is
#     distance = max(fit_distance, min_size_distance, min_distance)
# and min_object_frame_fraction only appears in the CHECK (max_size_distance) --
# it does NOT move the camera.  So relaxing the gate cannot change the framing of
# a clip that already passed, and the clip currently rendering stays valid.
#
# Relax to the mentor's validated 0.03 and add the camera step to the preflight.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== relax min_object_frame_fraction to the mentor's 0.03 ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import re, glob
for p in sorted(glob.glob("configs/scenarios/*_gso.yaml")):
    s = open(p).read()
    if "min_object_frame_fraction" not in s:
        print(f"  {p}: no gate, skipped"); continue
    old = re.search(r"(\n\s+min_object_frame_fraction: )([0-9.]+)", s)
    new_s = re.sub(r"(\n\s+min_object_frame_fraction: )[0-9.]+",
                   r"\g<1>0.03", s)
    if new_s != s:
        open(p, "w").write(new_s)
        print(f"  {p}: {old.group(2)} -> 0.03")
    else:
        print(f"  {p}: already 0.03")
PY

echo
echo "=== resulting gates ==="
for f in configs/scenarios/*_gso.yaml; do
  echo "--- $(basename $f) ---"
  sed -n '/^camera:/,/^output:/p' "$f" | grep -E 'focal_length|min_object_frame_fraction|max_object_frame_fraction|trajectory_frame_fraction' | sed 's/^/    /'
done
