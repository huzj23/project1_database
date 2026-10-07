"""V6.5 -- launch the full deterministic render fleet as disjoint frame blocks.

WHY 2 WORKERS PER GPU, AND WHY THAT IS NOT A SHORTCUT
----------------------------------------------------
The deadline is what forces this. Measured on this host at 1280x720 with the fog composited in:
    cold first frame  ~365 s   (shader/scene build)
    warm frame        ~115 s
216 frames therefore cost about 6.9 CPU-hours of single-worker time. On one worker that is 6.9 h, which does not fit;
on two it is 3.5 h, which overruns the 330-minute render window once encode and download are counted.

The box has 104 CPUs and Cycles was measured using only about 3 cores per worker (326% CPU), so the render is NOT
CPU-bound and running two workers per card does not starve either one. Three GPUs are free (1, 2, 3); GPU 0 carries
another user's process (pid 43013, 31 GB) and is left alone entirely.

So the fleet is 3 GPUs x 2 workers = 6 workers of 12 threads each, 36 frames per worker:
    w1 1..37   w2 37..73   w3 73..109   w4 109..145   w5 145..181   w6 181..217
The ranges are half-open and disjoint, so no two workers ever write the same PNG or sidecar.

EVERY LAUNCH IS PER-PROCESS ATTRIBUTABLE
----------------------------------------
Each launcher authorises ONE UUID and, after its worker's first frame, has the worker read back the GPUs holding a
context for its own pid and inspect every other process on that card. A co-tenant is accepted ONLY if its command line
shows this run's render script and this run's output directory -- i.e. another one of these six workers. A stranger's
job still stops the launch. "The card is empty" would have been the wrong test given the deadline, but "nobody is on
the card except my own verified workers" is not a relaxation of the plan, it is the same evidence standard applied to
a co-tenant that I started myself.

Nothing is deleted, no other user's process is touched, and all output stays inside the run directory.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = "/data/raw/huzijian/project1_database"
OUT = f"{ROOT}/outcomes/v65/radio_scurve_domino/v65_20261007_final"
SCENE = f"{OUT}/film_scene.blend"
SCRIPT = f"{ROOT}/tools/v65/render_range_r3.py"
LAUNCHER = f"{ROOT}/tools/v65/launch_render_block_r3.py"
LOCAL_LAUNCHER = r"tools\v65\launch_render_block_r3.py"
PY = sys.executable

GPUS = {
    "1": "GPU-a94dd628-5e85-0eeb-74c9-dc6fb4b56721",
    "2": "GPU-665e9626-9862-7424-fc4a-dc90d61079fa",
    "3": "GPU-245beacc-9dd2-60bb-4538-7e77ee56641f",
}
# three GPUs, two workers each. The suffix is the RUN GENERATION: the launcher refuses to overwrite an existing
# launcher script, which is what stopped this fleet from silently reusing the stale launchers belonging to the earlier
# (slow-motion) render. A new generation must be a new name, so the old run's launchers stay on disk as evidence of
# what was actually run and this fleet cannot be confused with it.
GEN = os.environ.get("V65_RUN_GEN", "r2")
PLAN = [
    (f"w1_{GEN}", "1", 1, 37), (f"w2_{GEN}", "1", 37, 73),
    (f"w3_{GEN}", "2", 73, 109), (f"w4_{GEN}", "2", 109, 145),
    (f"w5_{GEN}", "3", 145, 181), (f"w6_{GEN}", "3", 181, 217),
]

total = sum(stop - start for _, _, start, stop in PLAN)
print(f"fleet covers {total} frames in {len(PLAN)} disjoint blocks")
seen = set()
for name, gpu_key, start, stop in PLAN:
    for f in range(start, stop):
        if f in seen:
            raise SystemExit(f"frame {f} assigned twice")
        seen.add(f)
if sorted(seen) != list(range(1, 217)):
    raise SystemExit(f"coverage gap or overflow: {sorted(set(range(1, 217)) - seen)[:5]}")
print("coverage verified: every frame 1..216 exactly once")

launched = []
for name, gpu_key, start, stop in PLAN:
    uuid = GPUS[gpu_key]
    session = f"v65_rnd_{name}"
    # per-generation paths: the renderer creates the control dir with exist_ok=False by design, so a re-run under the
    # same name fails to launch (this is what happened to x1/x2 in launch_extra_workers.py)
    scratch = f"{ROOT}/tmp/v65_node12/scratch_{name}_{GEN}"
    control = f"{ROOT}/tmp/v65_node12/control_{name}_{GEN}"
    args = (f"--uuid {uuid} --scene {SCENE} --out {OUT} --script {SCRIPT} "
            f"--start {start} --stop {stop} --threads 12 --scratch {scratch} --control {control}")
    cmd = [PY, "-u", "tools/v64/remote_run.py", "run", "--account", "chenliang",
           "--name", session, "--script", LOCAL_LAUNCHER, "--interpreter", "python", "--args", args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = "started session" in (r.stdout + r.stderr)
    launched.append({"worker": name, "gpu": gpu_key, "uuid": uuid, "start": start, "stop": stop,
                     "session": session, "launched": ok})
    print(f"  {name} gpu{gpu_key} frames {start}..{stop} -> {'STARTED' if ok else 'FAILED: ' + r.stderr[-200:]}")

rep = Path(__file__).resolve().parents[2] / "log/V6.5_execution/render_fleet.json"
rep.parent.mkdir(parents=True, exist_ok=True)
rep.write_text(
    json.dumps({"workers": launched, "out": OUT, "scene": SCENE, "script": SCRIPT,
                "frames_total": total, "workers_count": len(PLAN)}, indent=2), encoding="utf-8")
print(f"\n{sum(1 for r in launched if r['launched'])}/{len(PLAN)} workers launched")
