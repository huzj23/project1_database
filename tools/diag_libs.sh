#!/usr/bin/env bash
# List shared libraries that Blender's binary needs but cannot resolve.
source /data/raw/huzijian/project1_database/tools/server_env.sh

B="$WS/tools/runtime/blender-3.4.1-linux-x64"
echo "=== blender binary: $B/blender ==="
ls -la "$B/blender"

echo
echo "=== ldd: unresolved entries ==="
ldd "$B/blender" 2>&1 | grep -i "not found" | sort -u

echo
echo "=== ldd: total entries ==="
ldd "$B/blender" 2>&1 | wc -l

echo
echo "=== bundled python ldd unresolved ==="
ldd "$BLENDER_PY" 2>&1 | grep -i "not found" | sort -u

echo
echo "=== direct run ==="
"$B/blender" --version 2>&1 | head -3

echo
echo "=== does the loader find libxkbcommon anywhere? ==="
ldconfig -p 2>/dev/null | grep -i xkbcommon || echo "(not in ldconfig cache)"

echo
echo "=== a few candidate system dirs (read-only listing) ==="
for d in /usr/lib64 /usr/lib /lib64; do
  n=$(ls "$d" 2>/dev/null | wc -l)
  echo "  $d : $n entries"
done

echo
echo "=== OS ==="
cat /etc/redhat-release 2>/dev/null
uname -r
