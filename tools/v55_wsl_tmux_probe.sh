#!/usr/bin/env bash
# V5.5 stage 03 (run INSIDE WSL): verify that a local tmux can drive the validated local
# Windows Blender 4.2.23.
#
# Why this matters
# ----------------
# 01 section 21 says: "Windows 不保证有原生 tmux ... Hidden Alley 若需本地渲染，先检查是否
# 已有可合法使用的本地 tmux 环境。没有时单独报告这一执行方式冲突；不要悄悄把所有计算用
# tmux 改成直接本地后台运行。"
#
# Windows has no native tmux, but WSL ships tmux 3.4, and WSL interop can launch a
# Windows .exe.  If that works, local replay of the Hidden Alley scene runs UNDER TMUX as
# required -- no silent substitution of a plain background process.
#
# This script is read-only with respect to the project: it starts a tmux session that
# invokes Blender with --version and a scene probe, then reports.
set -uo pipefail

WS_WIN="/mnt/d/workspace/project1_database"
BLENDER="$WS_WIN/tools/runtime_local/blender-4.2.23-windows-x64/blender.exe"
SOCK="/tmp/tmux_v55_local.sock"
SESSION="p1_v55_local_probe"

echo "=== A. environment ==="
echo "  tmux : $(tmux -V 2>&1)"
echo "  shell: $BASH_VERSION"
echo "  workspace visible: $([ -d "$WS_WIN" ] && echo yes || echo NO)"
echo "  blender exe     : $([ -f "$BLENDER" ] && echo present || echo MISSING)"

echo
echo "=== B. can WSL launch the Windows blender.exe at all? ==="
"$BLENDER" --version 2>&1 | head -3 | sed 's/^/  /'

echo
echo "=== C. tmux available at a project-local socket? ==="
tmux -S "$SOCK" ls 2>&1 | head -3 | sed 's/^/  /' || echo "  (no sessions yet, expected)"

echo
echo "=== D. start a tmux session that runs Blender and writes a log ==="
OUT="/mnt/d/workspace/project1_database/tmp/v55_local_tmux_probe.log"
mkdir -p /mnt/d/workspace/project1_database/tmp
tmux -S "$SOCK" kill-session -t "$SESSION" 2>/dev/null || true

# A single-command launch, matching the server's tmux-1.8 idiom so the same pattern works
# in both places.
cat > /tmp/v55_local_run.sh <<EOF
#!/usr/bin/env bash
{
  echo "START \$(date -Is)"
  echo "PWD \$(pwd)"
  "$BLENDER" --version
  echo "--- exit \$? ---"
  echo "END \$(date -Is)"
} > "$OUT" 2>&1
EOF
chmod +x /tmp/v55_local_run.sh

tmux -S "$SOCK" new-session -d -s "$SESSION" /tmp/v55_local_run.sh
echo "  launched; sessions:"
tmux -S "$SOCK" ls 2>&1 | sed 's/^/    /'

sleep 25
echo
echo "=== E. result written by the tmux job ==="
cat "$OUT" 2>/dev/null | sed 's/^/  /' || echo "  (no log yet)"
echo
echo "  sessions still alive:"
tmux -S "$SOCK" ls 2>&1 | sed 's/^/    /'
