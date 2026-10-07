"""V6.5 render fleet monitor -- progress, per-worker counts, errors, resources, and a measured ETA.

The ETA is recomputed from the frames actually on disk and the per-frame sidecars' measured wall times, so it reflects
the machine rather than a reference figure. It also reports how many frames each worker has finished, which is what
makes a stalled worker visible: five moving and one frozen is a different situation from six slow ones, and only the
per-worker counts can tell them apart.
"""

import glob
import heapq
import json
import os
import subprocess
import time

ROOT = "/data/raw/huzijian/project1_database"
OUT = ROOT + "/outcomes/v65/radio_scurve_domino/v65_20261007_final"
LOG = ROOT + "/log/V6.4_execution"
SOCK = ROOT + "/tmp/v64_node12_control.sock"

# The fleet is not the originally planned w1..w6. GPU 1 turned out to carry another user's process, so the two blocks
# it was to cover went to x1/x2 on GPUs 2 and 3; and because the render is CPU-bound, two further OFFLOAD workers
# (o1/o2) race the tail of the two late blocks to compress the critical path. The overlapping ranges are intentional:
# the renderer skips frames whose sidecar already exists, so a race is harmless and neither worker wastes the frame.
PLAN = {"w3": (73, 109), "w4": (109, 145), "x1": (1, 37),
        "w5": (145, 181), "w6": (181, 217), "x2": (37, 73),
        "o1": (25, 37), "o2": (61, 73)}
# The run generation. The launcher refuses to overwrite an existing launcher script, so a re-run needs new session
# names; the generation keeps this monitor, the watcher and the fleet pointed at the SAME run rather than at three
# different ones. Default matches launch_fleet.py.
GEN = os.environ.get("V65_RUN_GEN", "r2")


def sess(w):
    return f"v65_rnd_{w}_{GEN}"


print(f"=== worker sessions (generation {GEN}) ===")
alive = {}
for w in PLAN:
    r = subprocess.run(["/usr/bin/tmux", "-S", SOCK, "has-session", "-t", sess(w)],
                       capture_output=True, text=True)
    alive[w] = (r.returncode == 0)
    print(f"  {sess(w)}  {'ALIVE' if alive[w] else 'done/gone'}   range {PLAN[w][0]}..{PLAN[w][1]}")

meta = {}
for p in glob.glob(OUT + "/frames_meta/*.json"):
    try:
        m = json.load(open(p))
        meta[m["frame"]] = m
    except Exception:
        pass

print(f"\n=== frames ===")
print(f"  sidecars: {len(meta)}/216    PNGs: {len(glob.glob(OUT + '/frames/*.png'))}/216")
per = {}
for w, (a, b) in PLAN.items():
    n = sum(1 for f in meta if a <= f < b)
    done = n
    total = b - a
    times = [meta[f]["seconds"] for f in meta if a <= f < b]
    mean = sum(times) / len(times) if times else 0.0
    per[w] = {"done": done, "total": total, "mean_s": mean}
    bar = "#" * int(20 * done / total) + "." * (20 - int(20 * done / total))
    print(f"  {w}: [{bar}] {done:3d}/{total}  mean {mean:7.2f} s")
    print(f"       files: {sorted(f for f in meta if a <= f < b)[:14]}")

if meta:
    alltimes = sorted((f, meta[f]["seconds"]) for f in meta)
    warm = [s for f, s in alltimes if s < 300]
    cold = [s for f, s in alltimes if s >= 300]
    wm = sum(warm) / len(warm) if warm else 0.0
    print(f"\n=== timing ===")
    print(f"  cold frames (>=300 s): {len(cold)}  mean {sum(cold) / len(cold) if cold else 0:.1f} s")
    print(f"  warm frames:           {len(warm)}  mean {wm:.2f} s  min {min(warm) if warm else 0:.1f} "
          f"max {max(warm) if warm else 0:.1f}")
    remaining = 216 - len(meta)
    # ETA BY SIMULATION, NOT BY "REMAINING x MEAN"
    # -------------------------------------------
    # The previous estimate multiplied each worker's remaining frames by its own mean. That is wrong twice over:
    #
    #   1. Each worker's mean is contaminated by its COLD START -- the first frame after loading the 500 MB scene
    #      takes 300-430 s against a warm 140 s -- so every worker's mean overstated its steady rate.
    #   2. Once offload workers race the tail of the late blocks, a frame is finished by whichever worker reaches it
    #      first, so "worker X still has 35 frames" no longer means 35 frames of wall time. The offload workers exist
    #      precisely to shorten that, and a per-worker product cannot see it.
    #
    # So simulate the fleet instead: every worker walks its own range in order at the measured WARM rate, skipping
    # frames another worker already finished, and the finish time is when the last frame falls. That is the quantity
    # the deadline compares against.
    rate = wm if warm else 0.0
    pending = {w: [f for f in range(a, b) if f not in meta] for w, (a, b) in PLAN.items()}
    print(f"  frames remaining: {remaining}")
    if rate > 0 and any(pending.values()):
        # discrete-event simulation: each worker's next frame completes `rate` seconds from now
        now = 0.0
        heap = [(rate, w) for w in pending if pending[w]]
        heapq.heapify(heap)
        done = set(meta)
        while heap:
            t, w = heapq.heappop(heap)
            now = max(now, t)
            while pending[w] and pending[w][0] in done:
                pending[w].pop(0)
            if not pending[w]:
                continue
            f = pending[w].pop(0)
            done.add(f)
            if pending[w]:
                heapq.heappush(heap, (now + rate, w))
        print(f"  projected wall clock to finish all frames: {now / 60:.1f} min ({now / 3600:.2f} h)")
        print(f"  projected render completion: {time.strftime('%H:%M:%S', time.localtime(time.time() + now))}")
        per_worker = {w: len([f for f in range(a, b) if f not in meta]) for w, (a, b) in PLAN.items()}
        slow = max(per_worker.items(), key=lambda kv: kv[1])
        print(f"  most-loaded worker: {slow[0]} with {slow[1]} frames left "
              f"(naive estimate {slow[1] * rate / 60:.1f} min, shortened by the offload workers)")
    else:
        print("  not enough timing data yet for an ETA")

print("\n=== errors in worker logs ===")
bad = 0
for w in PLAN:
    p = f"{LOG}/v65_rnd_{w}_{GEN}.log"
    if os.path.exists(p):
        txt = open(p, errors="replace").read()
        for line in txt.splitlines():
            if any(k in line for k in ("Traceback", "Error", "refus", "FOREIGN", "RuntimeError", "EXIT_CODE")):
                print(f"  {w}: {line.strip()[:160]}")
                bad += 1
print(f"  ({bad} matching lines)")

print("\n=== resources ===")
print(subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu",
                      "--format=csv,noheader"], capture_output=True, text=True).stdout.strip())
print(subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip())
print(subprocess.run(["free", "-g"], capture_output=True, text=True).stdout.strip().splitlines()[1])
print(f"\nnow {time.strftime('%Y-%m-%d %H:%M:%S')}   (T0 14:33:33, deadline 20:33)")
