"""Read the ETA-trial sidecars and report per-frame cost, plus a projection against the deadline.

This is the number the V6.5 plan section 2 turns on: at 125 minutes the ETA must be compared against the T0+6h budget
and a real blockage reported if it does not fit. It is computed from MEASURED per-frame wall times and the number of
mutually non-competing workers, never from a reference figure.
"""

import glob
import json
import os
import subprocess
import sys
import time

ROOT = "/data/raw/huzijian/project1_database"
OUT = ROOT + "/outcomes/v65/radio_scurve_domino/v65_20261007_final"
LOG = ROOT + "/log/V6.4_execution"
T0 = "2026-10-07T14:33:33+08:00"

print("=== sessions ===")
sock = ROOT + "/tmp/v64_node12_control.sock"
for n in ("v65_eta_gpu1b", "v65_eta_gpu2b", "v65_gselftest_r4"):
    r = subprocess.run(["/usr/bin/tmux", "-S", sock, "has-session", "-t", n], capture_output=True, text=True)
    print(f"  {n:18s} {'ALIVE' if r.returncode == 0 else 'gone'}")

times = {}
for tag in ("trial_gpu1", "trial_gpu2"):
    d = f"{OUT}/{tag}"
    t = []
    if os.path.isdir(d):
        for p in sorted(glob.glob(d + "/frames_meta/*.json")):
            m = json.load(open(p))
            t.append((m["frame"], m["seconds"]))
        print(f"\n=== {tag}: {len(t)} frames rendered ===")
        for f, s in t:
            print(f"    frame {f:5d}  {s:8.3f} s")
        pngs = sorted(glob.glob(d + "/frames/*.png"))
        if pngs:
            print(f"    PNGs: {len(pngs)}, sizes {min(os.path.getsize(x) for x in pngs)}.."
                  f"{max(os.path.getsize(x) for x in pngs)} bytes")
        times[tag] = t

print("\n=== log tails ===")
for n in ("v65_eta_gpu1b", "v65_eta_gpu2b", "v65_gselftest_r4"):
    p = f"{LOG}/{n}.log"
    if os.path.exists(p):
        txt = open(p, errors="replace").read()
        print(f"--- {n} (finished={'EXIT_CODE=' in txt}) ---")
        print("\n".join(txt.splitlines()[-12:]))

allt = [s for v in times.values() for (_, s) in v]
if allt:
    warm = allt[1:] if len(allt) > 1 else allt
    mean_warm = sum(warm) / len(warm)
    print(f"\n=== ETA ===")
    print(f"  frames timed: {len(allt)}; first {allt[0]:.1f} s; warm mean {mean_warm:.2f} s")
    print(f"  cold-start overhead above warm: {allt[0] - mean_warm:.1f} s")
    total_216 = sum(allt) + mean_warm * (216 - len(allt))
    for workers in (2, 3, 4):
        h = total_216 / workers / 3600.0
        print(f"  {workers} workers (each its own GPU + 16 threads): "
              f"{total_216:.0f} core-seconds -> {h:.2f} h wall")
    print(f"  (216 frames at {mean_warm:.2f} s warm = {216 * mean_warm / 3600:.2f} core-hours)")

print("\n=== now ===")
print(" ", time.strftime("%Y-%m-%d %H:%M:%S"))
print("  T0 14:33:33, deadline 20:33")
