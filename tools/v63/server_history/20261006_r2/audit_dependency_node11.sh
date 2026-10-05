#!/bin/bash
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database
export V62_SCRATCH=/data/raw/huzijian/project1_database/tmp/v63_node11/dependency_audit_r1_scratch
export CUDA_VISIBLE_DEVICES=-1
/bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v62/blender42_scoped.sh --background --factory-startup --disable-autoexec --threads 8 --python-exit-code 2 --python /data/raw/huzijian/project1_database/tools/v63/audit_image_dependency.py > /data/raw/huzijian/project1_database/tmp/v63_node11/dependency_audit_r1.log 2>&1
if [ -x /usr/bin/rg ]; then
  /usr/bin/rg --files /data/raw/huzijian/project1_database/models/backgrounds | /usr/bin/rg 'modular_urban_apartments_facade_trim_01_rough' >> /data/raw/huzijian/project1_database/tmp/v63_node11/dependency_audit_r1.log || true
else
  /usr/bin/find /data/raw/huzijian/project1_database/models/backgrounds -type f -name 'modular_urban_apartments_facade_trim_01_rough*' >> /data/raw/huzijian/project1_database/tmp/v63_node11/dependency_audit_r1.log
fi
