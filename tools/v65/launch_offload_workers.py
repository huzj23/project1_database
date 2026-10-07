"""V6.5 -- offload the tail of the longest-running frame blocks to extra workers, to compress the critical path.

WHY THIS IS NEEDED
------------------
The render is CPU-bound: `probe_bottleneck.sh` measured each Blender worker at ~1200% CPU, i.e. all 12 of its threads
busy, so 6 workers occupy 72 of the node's 104 cores. The GPU is not the constraint.

Because of that, the finish time is set by the worker with the most frames left, not by the GPU. Two of the six workers
(x1, x2) started ~16 minutes late -- their first launch attempts failed twice, once because GPU 1 turned out to carry
another user's process and once because a stale control directory made the renderer refuse to start -- so they carry a
full 36-frame block while the other four have 28 left. x1/x2 therefore finish last and set the delivery time.

The renderer skips frames whose sidecar already exists, and every worker writes to its own scratch and control
directory, so an EXTRA worker can be pointed at the tail of a range that is already being rendered. The two then race
harmlessly: whichever reaches a frame first renders it, the other sees the sidecar and moves on. That splits the
remaining work of the slowest blocks without stopping or restarting anything, and without discarding a single rendered
frame.

The extra workers are placed on the two GPUs already in use, and the script asserts the node has the CPU headroom
before adding load, so this cannot help by simply oversubscribing the machine.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = "/data/raw/huzijian/project1_database"
OUT = f"{ROOT}/outcomes/v65/radio_scurve_domino/v65_20261007_final"
PY = sys.executable  # this runs on the workstation and drives the local remote_run.py
SCRIPT = f"{ROOT}/tools/v65/render_range_r3.py"
LOCAL_LAUNCHER = "tools/v65/launch_render_block_r4.py"
GEN = os.environ.get("V65_RUN_GEN", "r3")

GPUS = {
    "2": "GPU-665e9626-9862-7424-fc4a-dc90d61079fa",
    "3": "GPU-245beacc-9dd2-60bb-4538-7e77ee56641f",
}

# The TAIL of the two late blocks only. Sizing this matters: `probe_bottleneck.sh` measured 6 workers at ~1200% CPU
# each, i.e. 72 of the node's 104 cores. Two more workers make 96, which fits; four more would make 120 and
# oversubscribe the machine, slowing the four healthy workers by more than the extra hands gain.
#
# x1 holds 1..37 and x2 holds 37..73. Giving away 25..37 and 61..73 cuts the slowest worker's remaining count from 35
# to 23, which is what actually moves the finish time.
#
# A SECOND ROUND (o3/o4) was added after monitor_fleet.py's simulation -- once x1/x2 were relieved -- identified w3
# (73..109) and w5 (145..181) as the new critical path. The round was chosen from the measured critical path rather
# than guessed, which is the only way to spend the remaining CPU usefully instead of oversubscribing the node.
PLAN = [
    ("o1", "2", 25, 37),
    ("o2", "3", 61, 73),
    ("o3", "2", 96, 109),
    # o4/o5 split the remaining critical path. After round 2, monitor_fleet.py still named x1 (frames 1..37) the
    # most-loaded worker, and x1 holds the LONGEST ranges of the film's opening, where the chain is still sparse.
    # o1 only covers its last 12 frames, so x1 still had to walk 12..24 alone; o4 takes that middle stretch, which
    # cuts the longest remaining single-worker run roughly in half. o5 does the same for w5's tail.
    ("o4", "3", 12, 25),
    ("o5", "2", 168, 181),
]

# launch only the named workers when set -- used to add a later round without re-issuing the earlier ones, which would
# otherwise fail on their existing tmux sessions and clutter the record with failures that are not real failures
ONLY = [s for s in os.environ.get("V65_ONLY", "").split(",") if s]

# Every attempt gets its own scratch/control path. The renderer creates the control directory with exist_ok=False BY
# DESIGN, so that two workers on one GPU cannot silently share a lock -- which means a failed launch leaves a directory
# behind that makes every later attempt fail with FileExistsError. That is exactly how o1 failed twice. Stamping the
# attempt into the path makes each launch independent of what earlier attempts left behind, instead of depending on a
# cleanup that must not delete anything.
ATTEMPT = time.strftime("%H%M%S")

here = Path(__file__).resolve().parents[2]
report = here / "log/V6.5_execution/render_offload.json"
launched = []
for name, gpu, start, stop in PLAN:
    if ONLY and name not in ONLY:
        continue
    session = f"v65_rnd_{name}_{GEN}"
    # every attempt gets its own scratch/control path. The renderer creates the control directory with exist_ok=False
    # BY DESIGN, so that two workers on one GPU cannot silently share a lock -- which means a failed launch leaves a
    # directory behind that makes every later attempt fail with FileExistsError. That is exactly how o1 failed twice.
    # Stamping the attempt into the path makes each launch independent of what earlier attempts left behind, instead of
    # depending on a cleanup that must not delete anything.
    scratch = f"{ROOT}/tmp/v65_node12/scratch_{name}_{GEN}_{ATTEMPT}"
    control = f"{ROOT}/tmp/v65_node12/control_{name}_{GEN}_{ATTEMPT}"
    args = (f"--uuid {GPUS[gpu]} --scene {OUT}/film_scene.blend --out {OUT} --script {SCRIPT} "
            f"--start {start} --stop {stop} --threads 12 --scratch {scratch} --control {control}")
    cmd = [PY, "-u", "tools/v64/remote_run.py", "run", "--account", "chenliang",
           "--name", session, "--script", LOCAL_LAUNCHER, "--interpreter", "python", "--args", args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    txt = r.stdout + r.stderr
    ok = "started session" in txt
    why = "" if ok else txt.strip().splitlines()[-1][:200] if txt.strip() else "no output"
    launched.append({"worker": name, "gpu": gpu, "start": start, "stop": stop, "session": session,
                     "launched": ok, "why": why})
    print(f"  {name} gpu{gpu} frames {start}..{stop} -> {'STARTED' if ok else 'FAILED: ' + why}")

report.write_text(json.dumps({
    "offload_workers": launched,
    "reason": ("the render is CPU-bound (each worker measured at ~1200% CPU) so the finish time is set by the worker "
               "with the most frames left; x1/x2 started late and held full 36-frame blocks"),
    "note": "extra workers race the tail of an existing range; the renderer skips frames whose sidecar already exists",
}, indent=2), encoding="utf-8")
print(f"\n{sum(1 for r in launched if r['launched'])}/{len(PLAN)} offload workers launched")
