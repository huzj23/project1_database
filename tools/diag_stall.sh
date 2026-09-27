#!/usr/bin/env bash
# Diagnose a stalled post-render phase: are the workers busy, blocked, or stuck?
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "=== worker states (pid, state, cpu%, elapsed, cmd tail) ==="
ps -eo pid,stat,pcpu,etime,cmd 2>/dev/null |
  grep '[r]un_single_object' |
  sed -E 's#.*--video_id ([^ ]+).*#  \1#' |
  head -8
echo
ps -eo pid,stat,pcpu,etime 2>/dev/null | grep -E '^\s*[0-9]+' >/dev/null

for p in $(ps -eo pid,cmd 2>/dev/null | awk -v ws="$WS" 'index($0,ws)>0 && index($0,"run_single_object")>0 {print $1}'); do
  st=$(ps -o stat= -p "$p" 2>/dev/null)
  cpu=$(ps -o pcpu= -p "$p" 2>/dev/null)
  et=$(ps -o etime= -p "$p" 2>/dev/null)
  vid=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | sed -E 's/.*--video_id ([^ ]+).*/\1/')
  echo "  pid=$p state=$st cpu=$cpu elapsed=$et  $vid"
done

echo
echo "=== child processes (ffmpeg / cv2 writers) ==="
ps -eo pid,ppid,stat,etime,cmd 2>/dev/null | grep -E '[f]fmpeg' | head -6 || echo "  (no ffmpeg)"

echo
echo "=== scratch: frames vs output ==="
for d in "$WS"/tmp/phyco_scratch_*; do
  [ -d "$d" ] || continue
  n=$(ls -1 "$d/exr" 2>/dev/null | wc -l)
  img=$(ls -1 "$d/images" 2>/dev/null | wc -l)
  echo "  $(basename "$d"): exr=$n images=$img"
done

echo
echo "=== newest log lines from any worker stdout ==="
NEW=$(ls -t "$WS"/log/batch_phase1_*.log 2>/dev/null | head -1)
tail -6 "$NEW" 2>/dev/null | sed 's/^/  | /'

echo
echo "=== output dir contents ==="
for d in "$WS/outcomes/dataset/single_object"/*/; do
  [ -d "$d" ] || continue
  echo "  $(basename "$d"): $(ls -1 "$d" 2>/dev/null | wc -l) files"
done
