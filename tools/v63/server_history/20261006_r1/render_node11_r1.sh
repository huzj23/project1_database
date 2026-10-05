#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
export V63_SCRATCH=/data/raw/huzijian/project1_database/tmp/v63_node11/render_trial_r1
export CUDA_VISIBLE_DEVICES=-1
export OMP_NUM_THREADS=16
/bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v63/blender42_cpu_gl_r3.sh --background --factory-startup --disable-autoexec --threads 16 --python-exit-code 2 --python /data/raw/huzijian/project1_database/tools/v63/render_static_r1.py -- --scene-dir /data/raw/huzijian/project1_database/tmp/v63_node11/static_scene_r2 --out /data/raw/huzijian/project1_database/tmp/v63_node11/static_render_r1 --ids 04_drop_bridge,03_radio_receiver_side,07_tape_bridge,09_finish,10_follow_camera_sample > /data/raw/huzijian/project1_database/tmp/v63_node11/static_render_r1.log 2>&1
