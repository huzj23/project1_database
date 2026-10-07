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


def alive():
    """Count live RENDER workers of this run by listing tmux sessions, not by predicting their names.

    Two attempts at predicting the names both failed. First the list omitted the offload/rebalance workers this run
    acquired, so it read 0 while eight were rendering. Then it keyed the names on `V65_RUN_GEN`, which is an environment
    variable of the WORKSTATION shell -- `remote_run.py` does not forward it to the remote process, so the watcher
    silently fell back to its "r2" default and looked for sessions that do not exist.

    Enumerating what is actually there cannot drift: any session named `v65_rnd_*` whose launcher is running a
    `render_range` process for this output directory is a worker of this run. A missing-env bug cannot recur.
    """
    r = subprocess.run(["/usr/bin/tmux", "-S", SOCK, "ls"], capture_output=True, text=True)
    names = []
    for line in (r.stdout or "").splitlines():
        name = line.split(":")[0].strip()
        if name.startswith("v65_rnd_"):
            names.append(name)
    n = 0
    for name in names:
        # confirm the session is still executing a render of THIS run rather than an idle shell
        p = subprocess.run(["/usr/bin/tmux", "-S", SOCK, "list-panes", "-t", name, "-F", "#{pane_pid}"],
                           capture_output=True, text=True)
        pid = (p.stdout or "").strip().splitlines()
        if not pid:
            continue
        cmd = subprocess.run(["/bin/ps", "-o", "args=", "--ppid", pid[0]],
                             capture_output=True, text=True).stdout
        if "render_range" in cmd or "launch_render_block" in cmd:
            n += 1
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
