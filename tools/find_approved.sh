#!/usr/bin/env bash
# ===========================================================================
# Is the new disc material the SAME look the user approved before?
#
# The probe now measures R/B 4.04-4.22 on the disc, but V3.2 recorded R/B 1.83 for
# the approved render.  Those were measured under different lighting/view-transform
# and over different regions, so the numbers are not directly comparable.  Settle it
# by finding the APPROVED turntable render and measuring its disc with the SAME
# method used on the new probe.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
WS=/data/raw/huzijian/project1_database

echo "=== old turntable / wood outcomes still present? ==="
for d in "$WS"/outcomes/*tt* "$WS"/outcomes/*wood* "$WS"/outcomes/*转盘*; do
  [ -e "$d" ] || continue
  echo "  $d"
  ls -la "$d" 2>/dev/null | head -8 | sed 's/^/    /'
done

echo
echo "=== any prior on-table / approved renders ==="
ls -la "$WS/outcomes/" 2>/dev/null | head -40 | sed 's/^/  /'

echo
echo "=== render status ==="
echo "  --- camC rolling ---"
cat "$WS/tmp/camC_stdout.log" 2>/dev/null | tr -d '\r' | tail -5 | sed 's/^/    /'
echo "  running: $(pgrep -af 'scripts/generate.py' | grep -v 'bash -c' | head -1)"
