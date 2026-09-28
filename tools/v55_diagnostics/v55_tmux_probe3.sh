#!/usr/bin/env bash
# Confirm the tmux 1.8 limitation and validate the final launch form.
WS=/data/raw/huzijian/project1_database
SOCK="$WS/tmp/tmux_v55.sock"
T=/usr/bin/tmux

echo "=== A. multi-argument command (what failed earlier) ==="
$T -S "$SOCK" new-session -d -s m1 /bin/bash /bin/true 2>&1 | head -2
echo "rc=$?"

echo
echo "=== B. single-argument command that is itself a script ==="
cat > "$WS/tmp/probe_single.sh" <<'EOF'
#!/usr/bin/env bash
echo "single-arg launcher ran at $(date -Is)" > /data/raw/huzijian/project1_database/tmp/probe_single.out
EOF
chmod +x "$WS/tmp/probe_single.sh"
$T -S "$SOCK" new-session -d -s m2 "$WS/tmp/probe_single.sh" 2>&1 | head -2
echo "rc=$?"
sleep 3
echo "--- output of single-arg launcher ---"
cat "$WS/tmp/probe_single.out" 2>&1

echo
echo "=== C. does tmux 1.8 propagate an env var into the session? ==="
cat > "$WS/tmp/probe_env.sh" <<'EOF'
#!/usr/bin/env bash
echo "V55_PROBE='${V55_PROBE:-UNSET}'" > /data/raw/huzijian/project1_database/tmp/probe_env.out
EOF
chmod +x "$WS/tmp/probe_env.sh"
V55_PROBE=hello_from_parent $T -S "$SOCK" new-session -d -s m3 "$WS/tmp/probe_env.sh" 2>&1 | head -2
sleep 3
cat "$WS/tmp/probe_env.out" 2>&1

echo
echo "=== D. sessions ==="
$T -S "$SOCK" ls 2>&1
