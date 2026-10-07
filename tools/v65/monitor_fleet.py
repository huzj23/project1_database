"""V6.5 render fleet monitor -- progress, per-worker counts, errors, resources, and a measured ETA.

The ETA is recomputed from the frames actually on disk and the per-frame sidecars' measured wall times, so it reflects
the machine rather than a reference figure. It also reports how many frames each worker has finished, which is what
makes a stalled worker visible: five moving and one frozen is a different situation from six slow ones, and only the
per-worker counts can tell them apart.
"""

import glob
import json
import os
import subprocess
import time

ROOT = "/data/raw/huzijian/project1_database"
OUT = ROOT + "/outcomes/v65/radio_scurve_domino/v65_20261007_final"
LOG = ROOT + "/log/V6.4_execution"
SOCK = ROOT + "/tmp/v64_node12_control.sock"

PLAN = {"w1": (1, 37), "w2": (37, 73), "w3": (73, 109), "w4": (109, 145), "w5": (145, 181), "w6": (181, 217)}

print("=== worker sessions ===")
alive = {}
for w in PLAN:
    r = subprocess.run(["/usr/bin/tmux", "-S", SOCK, "has-session", "-t", f"v65_rnd_{w}"],
                       capture_output=True, text=True)
    alive[w] = (r.returncode == 0)
    print(f"  v65_rnd_{w}  {'ALIVE' if alive[w] else 'done/gone'}   range {PLAN[w][0]}..{PLAN[w][1]}")

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
    # each worker proceeds independently, so the wall time left is the SLOWEST worker's remaining work
    slowest = 0.0
    for w, (a, b) in PLAN.items():
        left = sum(1 for f in range(a, b) if f not in meta)
        slowest = max(slowest, left * (per[w]["mean_s"] or wm))
    print(f"  frames remaining: {remaining}")
    print(f"  projected wall clock for the slowest worker: {slowest / 60:.1f} min "
          f"({slowest / 3600:.2f} h)")
    print(f"  projected render completion: {time.strftime('%H:%M:%S', time.localtime(time.time() + slowest))}")

print("\n=== errors in worker logs ===")
bad = 0
for w in PLAN:
    p = f"{LOG}/v65_rnd_{w}.log"
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
