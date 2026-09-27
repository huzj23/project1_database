#!/usr/bin/env bash
# ===========================================================================
# DIAGNOSE + FIX: `--scenario X` makes load_run_config REPLACE the configured
# scenario file with configs/scenarios/X.yaml -- the mentor's default, which
# selects HIS maps (basketball_court / classroom / street).  Those have no visual
# assets on disk, hence FileNotFoundError.
#
# Our configs live in *_gso.yaml and are referenced from server.yaml's
# `project.scenario_config`.  So the correct invocation OMITS --scenario.
#
# This was already learned once (recorded in the ledger); the T1 script repeated
# the mistake.  Fix: point server.yaml at the scenario we want, and call
# generate.py WITHOUT --scenario.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== load_run_config: how does --scenario behave? ==="
grep -n 'def load_run_config' -A40 "$REPO/src/physim/config.py" | sed 's/^/  /'
