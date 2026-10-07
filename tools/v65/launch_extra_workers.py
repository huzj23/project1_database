"""V6.5 -- add the two workers needed because GPU 1 belongs to someone else.

WHAT HAPPENED
-------------
`launch_fleet.py` planned 3 GPUs x 2 workers. On the corrected re-run, GPU 1 was refused:

    GPU GPU-a94dd628-... carries processes that are not workers of this run:
      [{'pid': '110202', 'memory': '634 MiB', 'mine': False,
        'cmdline': '.../minimax-h3/bin/python main.py --listen 127.0.0.1 --port 8198 --cuda-device 1 ...'}]

That refusal is the launcher working correctly: an unrelated user's server is on GPU 1, and the rule for this run is
that a co-tenant must be provably one of my own workers. So GPU 1 is simply not available, and the remaining four
workers (two each on GPUs 2 and 3) would need 54 frames each -- about 2.5 h, which would finish after the deadline.

The fix is to keep the four workers that are already running and making progress, and add two more, one on each of the
free GPUs, covering the two blocks that GPU 1 was going to take (frames 1..73). That restores the six-way split
(3 workers per GPU, 36 frames each) without discarding the frames already rendered, because the renderer is resumable
and skips frames whose sidecar already exists.

This script launches ONLY the two missing workers. It does not stop, restart or reconfigure the four that are already
running, and it never touches GPU 1.
"""

import json
import os
import subprocess
from pathlib import Path

ROOT = "/data/raw/huzijian/project1_database"
OUT = f"{ROOT}/outcomes/v65/radio_scurve_domino/v65_20261007_final"
# This script runs on the WORKSTATION, not the node: it drives remote_run.py, which is the local launcher. The node
# has no remote_run.py. So the interpreter here is the local one, discovered from sys.executable rather than
# hard-coding either machine's python.
import sys as _sys
PY = _sys.executable
LOCAL_LAUNCHER = "tools/v65/launch_render_block_r3.py"
SCRIPT = f"{ROOT}/tools/v65/render_range_r3.py"
SCENE = f"{OUT}/film_scene.blend"

# GPU 1 is excluded on purpose: an unrelated process is on it.
GPUS = {
    "2": "GPU-665e9626-9862-7424-fc4a-dc90d61079fa",
    "3": "GPU-245beacc-9dd2-60bb-4538-7e77ee56641f",
}
# the two blocks the unavailable GPU was to have covered. The suffix is the run generation, and it MUST be changed
# together with launch_fleet.py's V65_RUN_GEN: the launcher refuses to overwrite an existing launcher script, so a
# re-run with the old suffix silently fails to start (as it did here, twice, with the r2 launchers).
GEN = os.environ.get("V65_RUN_GEN", "r2")
PLAN = [
    (f"x1", "2", 1, 37),
    (f"x2", "3", 37, 73),
]

here = Path(__file__).resolve().parents[2]
report = here / "log/V6.5_execution/render_fleet_x.json"
launched = []
for name, gpu, start, stop in PLAN:
    session = f"v65_rnd_{name}_{GEN}"
    # scratch and control directories MUST be per-generation. The renderer creates the control dir with exist_ok=False
    # so that two workers on one GPU cannot silently share a lock; reusing the previous generation's path therefore
    # fails the launch with FileExistsError, which is exactly what happened to x1 and x2 on this re-run.
    scratch = f"{ROOT}/tmp/v65_node12/scratch_{name}_{GEN}"
    control = f"{ROOT}/tmp/v65_node12/control_{name}_{GEN}"
    args = (f"--uuid {GPUS[gpu]} --scene {SCENE} --out {OUT} --script {SCRIPT} "
            f"--start {start} --stop {stop} --threads 12 --scratch {scratch} --control {control}")
    cmd = [PY, "-u", "tools/v64/remote_run.py", "run", "--account", "chenliang",
           "--name", session, "--script", LOCAL_LAUNCHER, "--interpreter", "python", "--args", args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = "started session" in (r.stdout + r.stderr)
    launched.append({"worker": name, "gpu": gpu, "start": start, "stop": stop, "session": session, "launched": ok})
    print(f"  {name} gpu{gpu} frames {start}..{stop} -> {'STARTED' if ok else 'FAILED: ' + (r.stderr or r.stdout)[-300:]}")

report.write_text(json.dumps({"extra_workers": launched, "reason": "GPU 1 occupied by another user's process",
                              "out": OUT}, indent=2), encoding="utf-8")
print(f"\n{sum(1 for r in launched if r['launched'])}/{len(PLAN)} extra workers launched")
print("fleet is now 6 workers: w3,w4,x1 on GPU2 and w5,w6,x2 on GPU3, 36 frames each")
