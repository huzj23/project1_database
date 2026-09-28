#!/usr/bin/env bash
# Wrapper that redirects its own stdout/stderr to a log inside the workspace, so the
# tmux pane never needs shell redirection on the tmux command itself.
#
# NOTE: this server's tmux is old and has no ``new-session -c``, so the working
# directory is set here instead of on the tmux command line.
LOG="${V55_LOG:-/data/raw/huzijian/project1_database/tmp/v55_stage01.out}"
exec >"$LOG" 2>&1
echo "V55 wrapper start: $(date -Is)"
echo "cmd: $0 $*"
cd /data/raw/huzijian/project1_database || exit 1
echo "cwd: $(pwd)"
bash "$@"
rc=$?
echo "V55 wrapper exit rc=$rc at $(date -Is)"
exit $rc
