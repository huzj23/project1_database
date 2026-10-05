#!/bin/bash
set -eu
umask 022
cd /data/raw/huzijian/project1_database
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/data/raw/huzijian/project1_database/tools/v62/git_no_global.conf
export TMPDIR=/data/raw/huzijian/project1_database/tmp/v62_node11
export OMP_NUM_THREADS=2
if [ -e /data/raw/huzijian/project1_database/code_snapshots/v62_20261005 ]; then
  exit 90
fi
/usr/bin/mkdir -p /data/raw/huzijian/project1_database/code_snapshots
{
  /usr/bin/git clone --no-hardlinks --branch main /data/raw/huzijian/project1_database/tmp/v62_code_20261005.bundle /data/raw/huzijian/project1_database/code_snapshots/v62_20261005
  cd /data/raw/huzijian/project1_database/code_snapshots/v62_20261005
  /usr/bin/git remote set-url origin https://github.com/huzj23/project1_database.git
  /usr/bin/git rev-parse HEAD
  /usr/bin/git status --short
} > /data/raw/huzijian/project1_database/log/V6.2_execution/code_snapshot.log 2>&1
