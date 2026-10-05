#!/bin/bash
set -eu
cd /data/raw/huzijian/project1_database
{
  /usr/bin/date -u
  /usr/bin/nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader,nounits
  /usr/bin/nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader
  /usr/bin/free -m
} > /data/raw/huzijian/project1_database/tmp/v62_node12/render_resource_snapshot.txt
