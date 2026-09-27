#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Vendor missing system shared libraries into the project workspace.
#
# Blender 3.4.1's Linux build needs libxkbcommon.so.0, which is absent from
# this CentOS 7 host.  Installing it system-wide would modify the shared
# machine, so instead we download the CentOS 7 RPM and extract ONLY the library
# into  <workspace>/tools/runtime/lib/ , then point LD_LIBRARY_PATH at it.
#
# Nothing outside the workspace is created or modified.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh

LIBDIR="$WS/tools/runtime/lib"
RPMDIR="$WS/tools/runtime/rpms"
mkdir -p "$LIBDIR" "$RPMDIR"

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'

# CentOS 7.9 vault, x86_64 base
MIRRORS=(
  "https://vault.centos.org/7.9.2009/os/x86_64/Packages"
  "https://mirrors.tuna.tsinghua.edu.cn/centos-vault/7.9.2009/os/x86_64/Packages"
  "https://mirrors.aliyun.com/centos-vault/7.9.2009/os/x86_64/Packages"
)

# package : library it provides
PKGS=(
  "libxkbcommon-0.7.1-3.el7"
  "libxkbcommon-x11-0.7.1-3.el7"
)

extract_rpm() {
  local rpm="$1" dest="$2"
  # Try, in order: rpm2cpio+cpio, bsdtar, rpm2archive
  if command -v rpm2cpio >/dev/null 2>&1 && command -v cpio >/dev/null 2>&1; then
    ( cd "$dest" && rpm2cpio "$rpm" | cpio -idm --quiet ) && return 0
  fi
  if command -v bsdtar >/dev/null 2>&1; then
    bsdtar -xf "$rpm" -C "$dest" && return 0
  fi
  if command -v rpm2archive >/dev/null 2>&1; then
    rpm2archive -n "$rpm" > "$dest/payload.tgz" && tar -xzf "$dest/payload.tgz" -C "$dest" && return 0
  fi
  return 1
}

echo "=== tool availability ==="
for t in rpm2cpio cpio bsdtar rpm2archive rpm; do
  printf '  %-12s %s\n' "$t" "$(command -v $t || echo MISSING)"
done

echo
echo "=== fetching + extracting packages ==="
for pkg in "${PKGS[@]}"; do
  rpm="$RPMDIR/${pkg}.x86_64.rpm"
  if [ ! -f "$rpm" ]; then
    ok=0
    for m in "${MIRRORS[@]}"; do
      url="$m/${pkg}.x86_64.rpm"
      echo "  trying $url"
      if curl -fL -A "$UA" --retry 2 --max-time 300 -o "$rpm" "$url"; then ok=1; break; fi
    done
    if [ "$ok" -ne 1 ]; then echo "  FAILED to fetch $pkg"; rm -f "$rpm"; continue; fi
  fi
  echo "  extracting $pkg"
  tmp="$RPMDIR/_x_$pkg"; rm -rf "$tmp"; mkdir -p "$tmp"
  if extract_rpm "$rpm" "$tmp"; then
    find "$tmp" -name 'lib*.so*' -type f -exec cp -av {} "$LIBDIR/" \; 2>/dev/null | sed 's/^/    /'
  else
    echo "    ERROR: no extraction tool available"
  fi
  rm -rf "$tmp"
done

echo
echo "=== workspace lib dir ==="
ls -la "$LIBDIR" 2>/dev/null

# RPMs ship only the fully-versioned file; the dynamic linker resolves the
# SONAME (e.g. libfoo.so.0), so read the SONAME straight out of the ELF header
# and create exactly that symlink.
echo
echo "=== creating SONAME symlinks ==="
soname_of() {
  local f="$1"
  if command -v readelf >/dev/null 2>&1; then
    readelf -d "$f" 2>/dev/null | sed -n 's/.*SONAME.*\[\(.*\)\].*/\1/p' | head -1
  elif command -v objdump >/dev/null 2>&1; then
    objdump -p "$f" 2>/dev/null | sed -n 's/.*SONAME\s\+\(.*\)/\1/p' | head -1
  fi
}
for so in "$LIBDIR"/lib*.so*; do
  [ -f "$so" ] || continue
  case "$so" in *.so.[0-9]*) ;; *) continue ;; esac   # only versioned payloads
  sn="$(soname_of "$so")"
  if [ -n "$sn" ] && [ ! -e "$LIBDIR/$sn" ]; then
    ln -sf "$(basename "$so")" "$LIBDIR/$sn"
    echo "  $sn -> $(basename "$so")"
  fi
done
ls -la "$LIBDIR"

echo
echo "=== resolve remaining deps of the vendored libs ==="
for so in "$LIBDIR"/*.so*; do
  [ -e "$so" ] || continue
  echo "  -- $(basename "$so")"
  LD_LIBRARY_PATH="$LIBDIR" ldd "$so" 2>/dev/null | grep -i 'not found' | sed 's/^/     /' || true
done

echo
echo "=== blender --version WITH vendored libs ==="
LD_LIBRARY_PATH="$LIBDIR:$WS/tools/runtime/blender-3.4.1-linux-x64/lib" \
  "$BLENDER" --version 2>&1 | head -3

# ---------------------------------------------------------------------------
# CA trust store: Blender's bundled CPython has none, so HTTPS (pip, curl via
# python) fails with CERTIFICATE_VERIFY_FAILED.  Keep a copy in the workspace.
# ---------------------------------------------------------------------------
echo
echo "=== CA bundle ==="
CA="$WS/tools/runtime/ca-bundle.crt"
if [ -f "$CA" ]; then
  echo "  already present: $CA ($(wc -l < "$CA") lines)"
elif [ -f /etc/pki/tls/certs/ca-bundle.crt ]; then
  cp /etc/pki/tls/certs/ca-bundle.crt "$CA" && echo "  copied system bundle -> $CA"
else
  echo "  WARNING: no system CA bundle found at /etc/pki/tls/certs/ca-bundle.crt"
fi
