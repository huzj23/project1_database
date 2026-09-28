#!/usr/bin/env bash
# V5.5 stage 03 (run INSIDE WSL): render Hidden Alley / Italian Flat baselines UNDER TMUX
# with local Blender 4.2.23.
#
# Two hard-won details:
#   1. blender.exe is a WINDOWS binary, so every path handed to it must be a Windows path
#      (D:\...), not the WSL /mnt/d/... form.  WSL paths in --python silently fail with
#      "could not be opened" while the shell still reports EXIT 0.
#   2. Because of (1), the exit code must be checked explicitly and the PNG must be
#      verified to exist; a zero shell status alone proves nothing here.
set -uo pipefail

WS="/mnt/d/workspace/project1_database"
WS_WIN='D:\workspace\project1_database'
BLENDER="$WS/tools/runtime_local/blender-4.2.23-windows-x64/blender.exe"
SOCK="/tmp/tmux_v55_local.sock"
OUTDIR="$WS/outcomes/v55/bootstrap/20260928T194500/local_baseline"

mkdir -p "$OUTDIR"

run_scene() {
  local scene="$1" w="$2" h="$3" spp="$4"
  local session="p1_v55_local_${scene}"
  # Windows-style paths for the Windows binary; WSL-style for the shell.
  local png_win="${WS_WIN}\\outcomes\\v55\\bootstrap\\20260928T194500\\local_baseline\\${scene}_authored_${w}x${h}_s${spp}.png"
  local png_wsl="$OUTDIR/${scene}_authored_${w}x${h}_s${spp}.png"
  local log="$OUTDIR/${scene}_render.log"
  local rcfile="$OUTDIR/${scene}_render.rc"

  tmux -S "$SOCK" kill-session -t "$session" 2>/dev/null || true

  cat > "/tmp/v55_lr_${scene}.sh" <<EOF
#!/usr/bin/env bash
{
  echo "START \$(date -Is)"
  "$BLENDER" --background --factory-startup \\
    --python "${WS_WIN}\\tools\\v55_local_baseline_render.py" -- \\
    --scene "$scene" --out "$png_win" --width $w --height $h --samples $spp
  rc=\$?
  echo "EXIT \$rc"
  echo "PNG_EXISTS \$([ -f "$png_wsl" ] && echo yes || echo no)"
  echo "END \$(date -Is)"
  echo "\$rc" > "$rcfile"
} > "$log" 2>&1
EOF
  chmod +x "/tmp/v55_lr_${scene}.sh"
  tmux -S "$SOCK" new-session -d -s "$session" "/tmp/v55_lr_${scene}.sh"
  echo "  launched $session"
}

wait_scene() {
  local scene="$1"
  for _ in $(seq 1 400); do
    if grep -qaE '^END ' "$OUTDIR/${scene}_render.log" 2>/dev/null; then return 0; fi
    sleep 5
  done
  echo "  TIMEOUT waiting for $scene"
  return 1
}

echo "=== rendering baselines under tmux (sequentially, one Blender at a time) ==="
for spec in "hidden_alley 960 540 8" "italian_flat 960 540 8"; do
  set -- $spec
  run_scene "$1" "$2" "$3" "$4"
  wait_scene "$1"
  echo "  $1 result:"
  grep -aE 'BASELINE_RECORD|EXIT|PNG_EXISTS|ERROR|OSError|camera=' \
    "$OUTDIR/$1_render.log" 2>/dev/null | sed 's/^/    /'
done

echo
echo "=== produced files ==="
ls -la "$OUTDIR" | sed 's/^/  /'

echo
echo "=== verify PNGs independently (decode the header) ==="
python3 - "$OUTDIR" <<'PY' 2>&1 | sed 's/^/  /'
import os, struct, sys
d = sys.argv[1]
found = 0
for name in sorted(os.listdir(d)):
    if not name.endswith(".png"):
        continue
    p = os.path.join(d, name)
    size = os.path.getsize(p)
    with open(p, "rb") as f:
        head = f.read(33)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        print(f"{name}: NOT a PNG")
        continue
    w, h = struct.unpack(">II", head[16:24])
    found += 1
    print(f"OK {name}: {w}x{h} depth={head[24]} colortype={head[25]} bytes={size}")
if not found:
    print("NO PNG PRODUCED")
PY
