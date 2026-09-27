#!/usr/bin/env bash
# Status for BOTH tracks: A (warehouse HDRI) and D (ReplicaCAD interior).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh

report() {
  local label="$1" dir="$2" want="$3"
  local n
  n=$(find "$dir" -name sample.json 2>/dev/null | wc -l)
  printf '%-28s %2s / %-3s   %s\n' "$label" "$n" "$want" \
    "$(du -sh "$dir" 2>/dev/null | cut -f1)"
}

echo "================= both tracks $(date '+%F %T') ================="
report "A  warehouse (dataset_real)"     "$WS/outcomes/dataset_real"     36
report "D  interior  (dataset_interior)" "$WS/outcomes/dataset_interior" 9

echo
echo "running render procs: $(ps -eo cmd 2>/dev/null | grep -c '[m]ake_local_samples')"
ps -eo etime,pcpu,cmd 2>/dev/null | grep '[m]ake_local_samples' |
  sed -E 's#.*--preset ([a-z_]+).*--only ([^ ]+).*#  \1  \2#' |
  sed -E 's#.*--preset ([a-z_]+).*#  \1  (full shard)#' | head -12

echo
echo "--- D clips finished ---"
for d in "$WS/outcomes/dataset_interior"/*/; do
  [ -f "$d/sample.json" ] || continue
  printf '  %-46s %s\n' "$(basename "$d")" "$(du -sh "$d" 2>/dev/null | cut -f1)"
done

echo
echo "--- node ---"
uptime | sed 's/^/  /'
echo "============================================================="
