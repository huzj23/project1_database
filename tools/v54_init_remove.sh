#!/usr/bin/env bash
set -euo pipefail

export CUDA_VISIBLE_DEVICES=""
export KUBRIC_USE_GPU="false"

/usr/bin/mkdir -p /data/raw/huzijian/project1_database/remove
/usr/bin/stat --format='%F:%a:%n' \
  /data/raw/huzijian/project1_database/remove \
  > /data/raw/huzijian/project1_database/tmp/v54_remove_init.log
