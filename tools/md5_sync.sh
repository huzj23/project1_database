#!/usr/bin/env bash
# The turntable subagent edited source files DIRECTLY ON THE SERVER, so the server
# is now ahead of my local checkout.  Report md5s for the files I am about to touch
# so I can sync before editing and never clobber their work.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
for f in src/physim/pipeline.py src/physim/camera/__init__.py \
         src/physim/scenarios/__init__.py src/physim/scenarios/turntable.py \
         src/physim/physics/__init__.py src/physim/physics/pybullet_backend.py \
         src/physim/render/blender_backend.py src/physim/validation/__init__.py \
         src/physim/io/__init__.py src/physim/assets/__init__.py \
         configs/scenarios/turntable_carry_gso.yaml configs/scenarios/turntable_spin_gso.yaml; do
  if [ -f "$f" ]; then
    printf "MD5 %s  %s\n" "$(md5sum "$f" | cut -c1-12)" "$f"
  else
    printf "MD5 MISSING      %s\n" "$f"
  fi
done

echo
echo "=== turntable configs: actor + omega + surface ==="
for f in configs/scenarios/turntable_carry_gso.yaml configs/scenarios/turntable_spin_gso.yaml; do
  echo "--- $f ---"
  grep -nE 'scenario|map_ids|allowed_types|surface|actor|asset|omega|mass|frame_count|video_fps|duration' "$f" | sed 's/^/  /'
done

echo
echo "=== server configs for turntable ==="
for f in configs/server_turntable_carry.yaml configs/server_turntable_spin.yaml; do
  echo "--- $f ---"
  grep -nE 'scenario_config|seed|asset_id|resolution|samples_per_pixel|modalities|write_video' "$f" | sed 's/^/  /'
done
