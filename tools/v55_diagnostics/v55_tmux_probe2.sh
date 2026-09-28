#!/usr/bin/env bash
# Diagnose tmux 1.8 on this host: which new-session invocation actually works, and
# whether a newer tmux exists anywhere usable.
WS=/data/raw/huzijian/project1_database
SOCK="$WS/tmp/tmux_v55.sock"
T=/usr/bin/tmux

echo "=== version / binary type ==="
$T -V
file $T 2>/dev/null || true
echo "TMUX env var: '${TMUX:-unset}'"

probe() {
  local label="$1"; shift
  local out rc
  out=$("$@" 2>&1); rc=$?
  printf '%-58s rc=%s  %s\n' "$label" "$rc" "$(echo "$out" | head -1)"
}

echo
echo "=== variant probes (socket=$SOCK) ==="
probe "new-session -d -s x /bin/true"      $T -S "$SOCK" new-session -d -s va /bin/true
probe "new -d -s x /bin/true"              $T -S "$SOCK" new -d -s vb /bin/true
probe "new-session -d -s x (no cmd)"       $T -S "$SOCK" new-session -d -s vc
probe "new-session -s x -d /bin/true"      $T -S "$SOCK" new-session -s vd -d /bin/true
probe "new-session -d -s x -- /bin/true"   $T -S "$SOCK" new-session -d -s ve -- /bin/true
probe "-f /dev/null new-session -d"        $T -S "$SOCK" -f /dev/null new-session -d -s vf /bin/true
probe "default socket new-session -d"      $T new-session -d -s vg /bin/true
probe "-L name new-session -d"             $T -L v55probe new-session -d -s vh /bin/true

echo
echo "=== sessions on our socket ==="
$T -S "$SOCK" ls 2>&1 | head -5
echo "=== sessions on -L v55probe ==="
$T -L v55probe ls 2>&1 | head -5

echo
echo "=== other tmux binaries on the system ==="
for c in /usr/local/bin/tmux /opt/*/bin/tmux "$WS"/tools/runtime/*/bin/tmux; do
  [ -x "$c" ] && echo "  $c -> $($c -V 2>&1)"
done
ls -d "$WS"/tools/runtime/* 2>/dev/null | sed 's/^/  runtime: /'

echo
echo "=== is stdin a tty here? ==="
[ -t 0 ] && echo "  stdin IS a tty" || echo "  stdin is NOT a tty"
tty 2>&1 | sed 's/^/  tty: /'
