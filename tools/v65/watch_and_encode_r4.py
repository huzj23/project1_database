"""V6.5 -- wait for the render fleet to finish, then QA, assemble and verify the video.

WHY A WATCHER RATHER THAN A MANUAL STEP
---------------------------------------
The fleet finishes at an unpredictable moment, and the encode plus download must follow immediately to stay inside the
delivery window. A watcher that polls the frame count and then runs the encode removes the risk of the last frames
sitting idle because nobody was watching at the right minute.

It refuses to proceed on an incomplete render: the video is only encoded once all 216 frames exist AND every one of
them passes the frame QA (no missing, black, flat, pink or duplicated frames). If the QA fails, it stops and leaves
the frames in place rather than encoding a defective sequence -- a wrong video that looks finished is the failure mode
this whole pipeline is built to avoid.

Nothing is deleted and no other process is touched.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
OUT = ROOT / "outcomes/v65/radio_scurve_domino/v65_20261007_final"
PY = str(ROOT / "tools/conda_env/bin/python")
FRAMES = 216
SOCK = str(ROOT / "tmp/v64_node12_control.sock")
GEN = os.environ.get("V65_RUN_GEN", "r2")
# The fleet grew as the run went on: w1/w2 never started (GPU 1 carried another user's process, so the renderer
# correctly refused to co-tenant), their blocks went to x1/x2, and CPU headroom then allowed offload workers o1..o5
# plus rebalance workers rb1..rb5. Listing only the original six made `alive()` return 0 while eight workers were
# rendering, and this watcher then exited with "no workers alive but only 0/216 frames" -- it would have given up
# exactly when the render was healthy. So the check is now: any tmux session of THIS run generation.
WORKERS = [f"v65_rnd_{w}_{GEN}" for w in ("w3", "w4", "w5", "w6", "x1", "x2",
                                          "o1", "o2", "o3", "o4", "o5",
                                          "rb1", "rb2", "rb3", "rb4", "rb5")]


def alive():
    n = 0
    for w in WORKERS:
        r = subprocess.run(["/usr/bin/tmux", "-S", SOCK, "has-session", "-t", w],
                           capture_output=True, text=True)
        n += (r.returncode == 0)
    return n


def count():
    return len(list((OUT / "frames").glob("Scene_*.png")))


deadline = time.time() + 6 * 3600
print(f"watcher start {time.strftime('%H:%M:%S')}: {count()}/{FRAMES} frames, {alive()} workers alive", flush=True)
last = -1
idle_polls = 0
while time.time() < deadline:
    n = count()
    a = alive()
    if n != last:
        print(f"  {time.strftime('%H:%M:%S')}  {n}/{FRAMES} frames   workers alive {a}", flush=True)
        last = n
    if n >= FRAMES:
        print(f"all {FRAMES} frames present", flush=True)
        break
    if a == 0:
        idle_polls += 1
    else:
        idle_polls = 0
    # Require several consecutive empty polls before giving up. Workers finish at different times, and a single
    # momentary zero reading -- e.g. the instant one worker exits before the next `tmux` probe -- would otherwise be
    # read as "the fleet died", which is how this watcher stopped itself at startup while eight workers were running.
    if idle_polls >= 4:
        print(f"STOPPED: no workers alive after {idle_polls} consecutive checks, {n}/{FRAMES} frames", flush=True)
        raise SystemExit(2)
    time.sleep(30)

if count() < FRAMES:
    raise SystemExit("watcher timed out")

# brief settle so the last worker's sidecar is flushed
time.sleep(20)

print("running frame QA + encode...", flush=True)
r = subprocess.run([PY, str(ROOT / "tools/v65/assemble_video.py"),
                    "--out", str(OUT), "--frames", str(FRAMES), "--first-frame", "1",
                    "--fps", "24", "--scene", "Scene", "--crf", "16", "--preset", "slow"],
                   capture_output=True, text=True)
print(r.stdout[-4000:], flush=True)
if r.returncode != 0:
    print(r.stderr[-4000:], flush=True)
    raise SystemExit(f"encode failed with {r.returncode}")

print("building manifest and final report...", flush=True)
for script in ("build_manifest_r2.py", "write_final_report.py"):
    r = subprocess.run([PY, str(ROOT / "tools/v65" / script)], capture_output=True, text=True)
    print(f"  {script}: exit {r.returncode}", flush=True)
    print(r.stdout[-1500:], flush=True)

print("WATCHER_DONE", flush=True)
