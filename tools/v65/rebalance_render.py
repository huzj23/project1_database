"""V6.5 -- rebalance the render by reading the frames that are ACTUALLY missing, then splitting the longest runs.

WHY A REBALANCER AND NOT MORE WORKERS
------------------------------------
The render is CPU-bound: each worker was measured at ~1200% CPU with GPU utilisation in single digits, so extra workers
only help while the node still has idle cores (104 cores; `uptime` showed load ~49 while 11 workers ran, so there was
real headroom). But the finish time is not set by total work, it is set by the LONGEST SINGLE RUN of consecutive
missing frames held by one worker. `monitor_fleet.py` kept naming x1 as the most-loaded worker even after two offload
workers were added, because those helpers took x1's tail and its middle while x1 still had to walk the rest alone.

So this reads the missing frames from disk, finds the longest consecutive missing runs, and gives each of the longest
runs to a fresh worker on a GPU that has free memory. Consecutive runs matter because a helper that starts at the middle
of a gap and walks forward finishes the whole tail of that gap.

Every launch uses a unique scratch and control path (stamped with the attempt time), because the renderer creates the
control directory with `exist_ok=False` by design -- two workers must not share a lock -- which makes any retry under a
reused path fail with FileExistsError. Nothing is ever deleted.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = "/data/raw/huzijian/project1_database"
OUT = f"{ROOT}/outcomes/v65/radio_scurve_domino/v65_20261007_final"
SCRIPT = f"{ROOT}/tools/v65/render_range_r3.py"
LOCAL_LAUNCHER = "tools/v65/launch_render_block_r4.py"
PY = sys.executable
GEN = os.environ.get("V65_RUN_GEN", "r3")
N_FRAMES = 216

# GPU uuid and a conservative free-memory figure read from the launcher's own snapshot format. Only GPUs 2 and 3 are
# used: GPU 0 and GPU 1 carry other users' processes and were established as off-limits.
GPUS = {
    "2": "GPU-665e9626-9862-7424-fc4a-dc90d61079fa",
    "3": "GPU-245beacc-9dd2-60bb-4538-7e77ee56641f",
}

# how many helpers to add, and how long a run must be before it is worth splitting. The helper takes the SECOND HALF of
# the run, which halves that run's wall time while leaving the original worker the first half. A run shorter than this
# is not worth a worker's cold start (300-450 s).
MAX_NEW = int(os.environ.get("V65_MAX_NEW", "4"))
MIN_RUN = int(os.environ.get("V65_MIN_RUN", "8"))

# THE FRAME LIST MUST COME FROM THE SERVER, NOT FROM A LOCAL PATH
# --------------------------------------------------------------
# The first version of this script read `OUT/frames_meta/*.json` directly. `OUT` is a REMOTE path, but this script runs
# on the workstation -- it drives the remote renderer through the local `remote_run.py` -- so that read silently returned
# nothing, the script concluded that all 216 frames were still missing, and it launched a helper for a 216-frame run.
# A silent empty read is the same family of error as every other one in this project: a complete, plausible, wrong
# answer. The frame list is therefore fetched over SSH, and the script refuses to proceed if it cannot see the render.
import subprocess
PY = sys.executable


def remote_missing():
    """Ask the server which frame sidecars exist, and return the set of frame numbers.

    The sidecar files are named `Scene_00001.json`, not `1.json`. The first version of this parser accepted only tokens
    that were entirely digits, so it discarded every real filename, saw an empty set, and refused to run. Parsing the
    number out of the name instead of requiring the name to BE the number is the fix.
    """
    remote = (f"ls {OUT}/frames_meta/*.json 2>/dev/null | "
              f"sed 's|.*/Scene_||; s|\\.json$||' | tr '\\n' ' '")
    r = subprocess.run([PY, "tools/v64/v65_ssh.py", "--timeout", "120", "--cmd", remote],
                       capture_output=True, text=True)
    if r.returncode != 0 or not (r.stdout or "").strip():
        raise SystemExit(f"could not read the remote frame list (rc={r.returncode}): "
                         f"{(r.stderr or r.stdout).strip()[-300:]}")
    have = set()
    for tok in (r.stdout or "").split():
        tok = tok.strip()
        if tok.isdigit():
            have.add(int(tok))
    return have


have = remote_missing()
if not have:
    raise SystemExit("the server reports NO frame sidecars; refusing to launch helpers against an empty render")
meta = have
missing = [f for f in range(1, N_FRAMES + 1) if f not in meta]

# consecutive runs of missing frames
runs = []
for f in missing:
    if runs and f == runs[-1][1] + 1:
        runs[-1][1] = f
    else:
        runs.append([f, f])
runs = [(a, b) for a, b in runs if b - a + 1 >= MIN_RUN]
runs.sort(key=lambda r: -(r[1] - r[0]))

print(f"frames done {len(meta)}/{N_FRAMES}, missing {len(missing)}")
print(f"longest consecutive missing runs (>= {MIN_RUN} frames):")
for a, b in runs[:8]:
    print(f"    {a}..{b}  ({b - a + 1} frames)")

if not runs:
    print("\nno run long enough to split; nothing to rebalance")
    raise SystemExit(0)

report = Path(__file__).resolve().parents[2] / "log/V6.5_execution/render_rebalance.json"
launched = []
# Names must be unique per invocation. Reusing `rb1`..`rb5` made every later round fail with "refuse overwrite" --
# the launcher scripts of the earlier rounds still existed -- so those rounds silently did nothing while printing a
# failure that looked like a blocker. Stamping the attempt time into the name makes each round independent.
ROUND = time.strftime("%H%M%S")
for i, (a, b) in enumerate(runs[:MAX_NEW]):
    mid = a + (b - a + 1) // 2
    gpu = "2" if i % 2 == 0 else "3"
    name = f"rz{ROUND}_{i + 1}"
    session = f"v65_rnd_{name}"
    scratch = f"{ROOT}/tmp/v65_node12/scratch_{name}"
    control = f"{ROOT}/tmp/v65_node12/control_{name}"
    args = (f"--uuid {GPUS[gpu]} --scene {OUT}/film_scene.blend --out {OUT} --script {SCRIPT} "
            f"--start {mid} --stop {b + 1} --threads 12 --scratch {scratch} --control {control}")
    cmd = [PY, "-u", "tools/v64/remote_run.py", "run", "--account", "chenliang", "--name", session,
           "--script", LOCAL_LAUNCHER, "--interpreter", "python", "--args", args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    txt = r.stdout + r.stderr
    ok = "started session" in txt
    why = "" if ok else (txt.strip().splitlines()[-1][:200] if txt.strip() else "no output")
    launched.append({"worker": name, "gpu": gpu, "start": mid, "stop": b + 1, "covers_run": [a, b],
                     "session": session, "launched": ok, "why": why})
    print(f"  {name} gpu{gpu} takes the second half of {a}..{b}: frames {mid}..{b + 1} -> "
          f"{'STARTED' if ok else 'FAILED: ' + why}")

report.write_text(json.dumps({
    "launched": launched,
    "frames_done_at_launch": len(meta),
    "missing_at_launch": len(missing),
    "runs_split": runs[:MAX_NEW],
    "reason": ("the finish time is set by the longest single run of missing frames held by one worker, so helpers are "
               "placed on the second half of the longest runs rather than anywhere at random"),
}, indent=2), encoding="utf-8")
print(f"\n{sum(1 for r in launched if r['launched'])}/{len(launched)} rebalance workers launched")
