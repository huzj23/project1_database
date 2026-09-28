#!/usr/bin/env bash
# V5.5 stage 03: the Hidden Alley scene segfaults Blender 3.4.1 during
# open_mainfile, and Blender 4.2.23 cannot start on this host (needs glibc 2.26/2.27;
# the host is CentOS 7 / glibc 2.17).  A .blend header declares the version that WROTE
# it, and is readable without Blender, so read the headers first.
#
# READ-ONLY.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh
cd "$WS" || exit 1

echo "=== A. host glibc ==="
ldd --version 2>&1 | head -2 | sed 's/^/  /'
echo "  --- highest glibc symbols the dynamic linker knows ---"
strings /lib64/libc.so.6 2>/dev/null | grep -aE '^GLIBC_2\.[0-9]+$' | sort -uV | tail -5 | sed 's/^/    /'

echo
echo "=== B. .blend headers (which Blender wrote each file?) ==="
hdr() {
  local f="$1"
  [ -f "$f" ] || { echo "  ABSENT: $f"; return; }
  # Format: "BLENDER" (7 bytes) + 3-char version + pointer size + endianness.
  # Read as HEX, never as raw text: the header bytes are not valid UTF-8 and emitting
  # them raw corrupts the SSH capture channel.
  local magic ver
  magic=$(head -c 7 "$f" | od -An -tx1 | tr -d ' \n')
  ver=$(head -c 12 "$f" | tail -c 5 | od -An -tx1 | tr -d ' \n')
  echo "  $(basename "$f")"
  echo "      magic_hex = ${magic}"
  echo "      ver_hex   = ${ver}"
  # 0x32 0x2e 0x39 0x33 == "2.93", etc. Decode the 3 version bytes as ASCII.
  local b1 b2 b3
  b1=$(printf '%d' "0x$(echo "$ver" | cut -c1-2)")
  b2=$(printf '%d' "0x$(echo "$ver" | cut -c3-4)")
  b3=$(printf '%d' "0x$(echo "$ver" | cut -c5-6)")
  printf '      version   = %d.%d.%d  (ptr=%s endian=%s)\n' \
    "$b1" "$b2" "$b3" "$(echo "$ver" | cut -c7-8)" "$(echo "$ver" | cut -c9-10)"
}
hdr "$WS/models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend"
hdr "$WS/models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend"
hdr "$WS/models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend"

echo
echo "=== C. every Blender build in the project runtime ==="
ls -d "$WS/tools/runtime/"blender-* 2>/dev/null | sed 's/^/  /'
echo "  --- for each: can it start? ---"
for b in "$WS/tools/runtime/"blender-*/blender; do
  [ -x "$b" ] || continue
  name=$(basename "$(dirname "$b")")
  out=$(LD_LIBRARY_PATH="$WS/tools/runtime/lib:${LD_LIBRARY_PATH:-}" "$b" --version 2>&1 | head -2 | tr '\n' ' ')
  echo "  ${name}: ${out}"
done

echo
echo "=== D. is a NEWER libc available anywhere INSIDE the workspace (no OS changes)? ==="
find "$WS/tools/runtime" -name 'libc.so.6' -o -name 'libc-2.*.so' 2>/dev/null | head -10 | sed 's/^/  /'
echo "  --- conda envs that might carry a newer sysroot ---"
ls -d "$WS"/tools/*env* "$WS"/tools/conda* 2>/dev/null | sed 's/^/  /'

echo
echo "=== E. was the Hidden Alley scene EVER rendered? find outputs ==="
find "$WS" -path '*hidden_alley*' \( -name '*.png' -o -name '*.jpg' -o -name '*.exr' -o -name '*.mp4' \) 2>/dev/null | head -20 | sed 's/^/  /'
echo "  --- render/frames dirs named for it ---"
find "$WS/outcomes" -maxdepth 4 -type d -iname '*hidden*' 2>/dev/null | head -10 | sed 's/^/  /'

echo
echo "=== F. blender -b direct load (bypasses the Python API path) ==="
B41="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
S="$WS/models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend"
LD_LIBRARY_PATH="$WS/tools/runtime/lib:${LD_LIBRARY_PATH:-}" timeout 300 \
  "$B41" -b "$S" --python-expr "print('LOADED_OK objects=', len(bpy.data.objects), flush=True)" 2>&1 \
  | grep -aE 'LOADED_OK|Error|Segmentation|Blender quit' | head -6 | sed 's/^/  /'
echo "  rc=$?"
