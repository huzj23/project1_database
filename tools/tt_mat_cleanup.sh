#!/usr/bin/env bash
# Tidy up: close only the tmux sessions this task created.  Never touch any
# other user's session.
for s in ttmatprobe ttmatpreflight ttmatmain ttmatfinal; do
  if tmux kill-session -t "$s" 2>/dev/null; then
    echo "killed $s"
  else
    echo "$s already gone"
  fi
done
echo "--- remaining ttmat sessions (want none) ---"
tmux ls 2>/dev/null | grep -E 'ttmat' || echo "none"
echo "--- other sessions still alive (untouched) ---"
tmux ls 2>/dev/null | wc -l
