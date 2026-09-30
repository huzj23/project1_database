#!/bin/bash
# V5.7 arc-solve launcher, run ON THE SERVER inside tmux.
#
# Resumable: the solver writes arc_result.json and its log incrementally, so re-running this script after a
# disconnect continues from the same run directory rather than starting over.
set -u

WS=/data/raw/huzijian/project1_database
RUN=$WS/outcomes/v57/domino_arc/arc01
PREV=$WS/outcomes/v56/mixed_box_domino/20260929T142714

# The interpreter that actually has pybullet. `python3` on PATH resolves to a conda base WITHOUT it, and
# `python3 -c "import pybullet"` fails there -- which is why two earlier attempts died at import. The
# workspace's own conda_env has pybullet 3.2.7, so it is used explicitly rather than relying on PATH.
PY=$WS/tools/conda_env/bin/python
if [ ! -x "$PY" ]; then
    echo "FATAL: no interpreter at $PY"
    exit 2
fi

mkdir -p "$RUN" "$RUN/logs"

echo "=== env ==="
$PY -c "import pybullet, sys; print('pybullet', pybullet.getAPIVersion()); print(sys.version)"

# The GSO proxies and the proxy report are reused verbatim from the verified straight-chain round: they are
# the same four real assets, and re-deriving them would throw away a solved, size-checked artefact.
# The solver is staged INSIDE the run directory rather than the shared tools tree, so this job cannot be
# broken by someone else editing tools/ concurrently, and the exact code that produced a result travels
# with that result.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

$PY "$SELF_DIR/arc_solve.py" \
    --site "$RUN/site.json" \
    --out "$RUN" \
    --proxies "$PREV/proxies" \
    --proxy-report "$PREV/proxy_report.json" \
    --n 9 --arc-r 2.0 \
    --gap-frac 0.25 --density 200 --margin-mm 1.0 \
    2>&1 | tee "$RUN/logs/arc_solve.log"

echo "ARC_SOLVE_EXIT=$?"
