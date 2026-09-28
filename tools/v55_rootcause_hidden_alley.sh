#!/usr/bin/env bash
# V5.5 stage 03: root-cause why Hidden Alley cannot be opened.
#
# Header bytes show ph_hidden_alley.blend was written by Blender 4.00 while the only
# runnable Blender here is 3.4.1, which cannot read a newer-format file.  Blender 4.2.23
# IS present but needs glibc 2.26/2.27 and the host is glibc 2.17.
#
# So the question is whether ANY way exists INSIDE the workspace to run a Blender >= 4.0.
# READ-ONLY: nothing is installed or modified.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

echo "=== A. decode all three headers precisely (hex, ASCII-safe) ==="
decode() {
  local f="$1" label="$2"
  [ -f "$f" ] || { echo "  ABSENT $label"; return; }
  local first7 ver
  first7=$(head -c 7 "$f" | od -An -tx1 | tr -d ' \n')
  ver=$(head -c 12 "$f" | tail -c 5 | od -An -tx1 | tr -d ' \n')
  echo "  $label"
  echo "    first7_hex : $first7"
  if [ "$first7" = "1f8b0800000000" ] || [ "${first7:0:6}" = "1f8b08" ]; then
    echo "    >>> GZIP-compressed .blend (Blender reads gzip-wrapped blend files)"
    # Decompress a little to reach the real header.
    local inner
    inner=$(gzip -dc "$f" 2>/dev/null | head -c 12 | od -An -tx1 | tr -d ' \n')
    echo "    inner_hdr  : $inner"
    ver=$(echo "$inner" | cut -c15-24)
  elif [ "$first7" = "424c454e444552" ]; then
    echo "    >>> plain BLENDER file"
  else
    echo "    >>> UNRECOGNISED magic"
  fi
  # Bytes 8..11 (1-based) are: ptrsize/endianness char, 'v'|'V', then 3 version digits.
  if [ -n "$ver" ] && [ ${#ver} -ge 10 ]; then
    local p=$(printf "\\x$(echo "$ver" | cut -c1-2)")
    local e=$(printf "\\x$(echo "$ver" | cut -c3-4)")
    local d1 d2 d3
    d1=$(printf '%d' "0x$(echo "$ver" | cut -c5-6)")
    d2=$(printf '%d' "0x$(echo "$ver" | cut -c7-8)")
    d3=$(printf '%d' "0x$(echo "$ver" | cut -c9-10)")
    echo "    ptrsize='$p' endian='$e'  => written by Blender ${d1}.${d2}${d3}"
  fi
}
decode "$WS/models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend" "italian_flat"
decode "$WS/models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend" "hidden_alley"
decode "$WS/models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend" "the_shed"

echo
echo "=== B. what libraries does the project ship in runtime/lib? ==="
ls "$WS/tools/runtime/lib" 2>/dev/null | head -40 | sed 's/^/  /'
echo "  count: $(ls "$WS/tools/runtime/lib" 2>/dev/null | wc -l)"

echo
echo "=== C. is a newer glibc anywhere inside the workspace? ==="
echo "  --- libc.so.6 files ---"
find "$WS/tools" -name 'libc.so.6' -o -name 'libc-2.*.so' 2>/dev/null | head | sed 's/^/    /'
echo "  --- ld-linux loaders ---"
find "$WS/tools" -name 'ld-linux*' -o -name 'ld-2.*.so' 2>/dev/null | head | sed 's/^/    /'
echo "  --- conda sysroot packages ---"
find "$WS/tools/conda_pkgs" -maxdepth 1 -iname '*sysroot*' -o -maxdepth 1 -iname '*libc*' 2>/dev/null | head | sed 's/^/    /'
echo "  --- conda envs present ---"
ls "$WS/tools/conda_envs" 2>/dev/null | head -20 | sed 's/^/    /'

echo
echo "=== D. does the conda env carry its own libc? ==="
find "$WS/tools/conda_env" -maxdepth 3 -name 'libc.so*' 2>/dev/null | head | sed 's/^/  /'
find "$WS/tools/conda_envs" -maxdepth 4 -name 'libc.so*' 2>/dev/null | head | sed 's/^/  /'

echo
echo "=== E. any OTHER blender binary anywhere in the workspace? ==="
find "$WS" -name 'blender' -type f 2>/dev/null | sed 's/^/  /'

echo
echo "=== F. can conda/eula be reached (would a newer libc be installable)? ==="
"$WS/tools/conda_env/bin/conda" --version 2>&1 | head -2 | sed 's/^/  /'
timeout 25 "$WS/tools/conda_env/bin/conda" search -c conda-forge sysroot_linux-64 2>&1 | tail -5 | sed 's/^/  /'

echo
echo "=== G. pip/network reachability (needed if we must fetch a build) ==="
timeout 20 python3 -c "import urllib.request;print(urllib.request.urlopen('https://pypi.org/simple/',timeout=15).status)" 2>&1 | head -3 | sed 's/^/  /'
