#!/usr/bin/env bash
# Is the code/vendor/phyco-sim difference real, or just CRLF vs LF?
WS=/data/raw/huzijian/project1_database
V="$WS/code/vendor/phyco-sim"
echo "=== sample a differing vendor file on the SERVER ==="
F="$V/src/run_ball_drop_v2.py"
if [ -f "$F" ]; then
  echo "  $F"
  echo "  size   : $(stat -c%s "$F")"
  echo "  sha256 : $(sha256sum "$F" | cut -d' ' -f1)"
  echo "  CRLF count: $(grep -c $'\r' "$F" 2>/dev/null || echo 0)"
  echo "  first line: $(head -1 "$F" | cat -A | head -c 120)"
else
  echo "  missing: $F"
fi
echo
echo "=== git availability on the server ==="
git --version 2>&1 | sed 's/^/  /'
echo "  is there a .git anywhere in the workspace?"
find "$WS" -maxdepth 4 -name '.git' -type d 2>/dev/null | head -5 | sed 's/^/    /'
echo "  (nothing above = the server is not a Git checkout; Git lives locally)"
echo
echo "=== vendor size and origin ==="
du -sh "$V" 2>/dev/null | sed 's/^/  /'
cat "$V/VENDOR_INFO.txt" 2>/dev/null | head -10 | sed 's/^/  /' || true
ls "$V" | head -12 | sed 's/^/  /'
