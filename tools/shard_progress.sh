#!/usr/bin/env bash
# Per-shard render progress: which clip each shard is on and how far into it.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh

for i in 0 1 2 3 4 5; do
  f="$WS/log/real_shard$i.log"
  [ -f "$f" ] || continue
  done_n=$(grep -c 'd=.*actor=' "$f" 2>/dev/null)
  cur=$(grep -oE '\[sample\] [A-Za-z0-9_]+' "$f" 2>/dev/null | tail -1 | cut -d' ' -f2)
  # the frame counter in Blender's progress line tells us how far along we are
  fra=$(grep -oE 'Fra:[0-9]+' "$f" 2>/dev/null | tail -1 | cut -d: -f2)
  printf '  s%s: %s done | current=%-42s frame=%s/96\n' "$i" "$done_n" "${cur:-?}" "${fra:-?}"
done
