#!/bin/bash
# V6.5: run one Blender python script on the server, project-scoped, via the SAME wrapper the
# proven V6.3 pipeline used. Nothing global is touched: scratch, caches, and user resources all
# live under the project tmp tree, and the compat loader stays in the project runtime dir.
set -euC
ulimit -c 0
cd /data/raw/huzijian/project1_database

SCRIPT="$1"; shift
SCRATCH="${V65_SCRATCH:-/data/raw/huzijian/project1_database/tmp/v65_node12/blender}"
THREADS="${V65_THREADS:-16}"
case "$SCRATCH" in /data/raw/huzijian/project1_database/*) ;; *) echo "scratch outside workspace"; exit 91 ;; esac
export V62_SCRATCH="$SCRATCH"
export OMP_NUM_THREADS="$THREADS"

exec /bin/bash --noprofile --norc /data/raw/huzijian/project1_database/tools/v62/blender42_scoped.sh \
  --background --factory-startup --disable-autoexec --threads "$THREADS" \
  --python-exit-code 2 --python "$SCRIPT" -- "$@"
