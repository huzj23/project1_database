"""V6.5 -- launch a GPU-scoped Blender render block on the server.

What it enforces, and why each step exists:

  * TWO IDLE SNAPSHOTS of exactly one GPU UUID, 5 s apart, before anything starts. The plan says the resource
    snapshot is not a reservation, so the check is repeated at launch time and the launch is refused if the card is
    busy. The snapshots are written as evidence.
  * The physical device is selected through the project's own EGL adapter layer, keyed by UUID, with
    `CUDA_VISIBLE_DEVICES` removed from the environment. Plan section 4 forbids using CUDA ordinal remapping as an
    isolation proof, because the ordinals the application sees need not match the physical order.
  * After startup the RENDERER ITSELF reads back the GPUs that hold a context for its own pid, and the block fails if
    that is not exactly the authorised UUID. A claimed device is not evidence; an observed one is.
  * Output, scratch and caches all land inside the run directory. Nothing global is modified and no other process is
    touched.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path("/data/raw/huzijian/project1_database")
ADAPTER = ROOT / "tools/runtime/v63_egl_uuid_r1/libv63_egl_uuid_r2.so"
VENDOR = ROOT / "tools/runtime/v63_egl_uuid_r1/nvidia_vendor.json"
WRAPPER = ROOT / "tools/v62/blender42_scoped.sh"

ap = argparse.ArgumentParser()
ap.add_argument("--uuid", required=True)
ap.add_argument("--scene", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--script", required=True)
ap.add_argument("--start", type=int, required=True)
ap.add_argument("--stop", type=int, required=True)
ap.add_argument("--threads", type=int, default=16)
ap.add_argument("--scratch", required=True)
ap.add_argument("--probe-only", action="store_true")
ap.add_argument("--control", required=True, help="directory for the evidence of this launch")
args = ap.parse_args()

control = Path(args.control)
control.mkdir(parents=True, exist_ok=False)


def snapshot():
    tree = ET.fromstring(subprocess.check_output(["/usr/bin/nvidia-smi", "-i", args.uuid, "-q", "-x"], text=True))
    card = tree.find("gpu")
    if card is None:
        raise RuntimeError(f"GPU {args.uuid} not present")
    return {"time": time.time(), "uuid": card.findtext("uuid"),
            "memory_mb": int(card.findtext("fb_memory_usage/used").split()[0]),
            "utilization": int(card.findtext("utilization/gpu_util").split()[0]),
            "process_count": len(card.findall(".//process_info"))}


snaps = []
for attempt in range(2):
    s = snapshot()
    snaps.append(s)
    if s["uuid"] != args.uuid or s["memory_mb"] >= 512 or s["utilization"] > 5 or s["process_count"]:
        (control / "refused.json").write_text(json.dumps(snaps, indent=2), encoding="utf-8")
        raise SystemExit(f"GPU {args.uuid} is not idle: {s}")
    if attempt == 0:
        time.sleep(5)
(control / "idle_snapshots.json").write_text(json.dumps(snaps, indent=2), encoding="utf-8")

env = dict(os.environ)
env.pop("CUDA_VISIBLE_DEVICES", None)
env.pop("CUDA_DEVICE_ORDER", None)
# The EGL adapter shim reads `V63_GPU_UUID` -- that name is compiled into the C library
# (`tools/v63/egl_uuid_scope_r2.c`), so it cannot be renamed here. The first launch of this block used `V65_GPU_UUID`
# and Blender exited 87 with `V63_EGL_UUID_MISSING`; the shim refused to guess a device rather than silently using
# whichever GPU happened to be first, which is exactly the intended behaviour. Both names are set so the intent is
# visible at this call site while the library still finds what it requires.
env.update({"V63_GPU_UUID": args.uuid,
            "V65_GPU_UUID": args.uuid,
            "V62_SCRATCH": args.scratch,
            "OMP_NUM_THREADS": str(args.threads),
            "LD_PRELOAD": str(ADAPTER),
            "__EGL_VENDOR_LIBRARY_FILENAMES": str(VENDOR)})

argv = ["/bin/bash", "--noprofile", "--norc", str(WRAPPER),
        "--background", "--factory-startup", "--disable-autoexec",
        "--threads", str(args.threads), "--python-exit-code", "2",
        "--python", args.script, "--",
        "--scene", args.scene, "--out", args.out,
        "--start", str(args.start), "--stop", str(args.stop), "--threads", str(args.threads)]
if args.probe_only:
    argv.append("--probe-only")

log = control / "blender.log"
with log.open("w") as fh:
    result = subprocess.run(argv, env=env, stdout=fh, stderr=subprocess.STDOUT)
print(f"RENDER_BLOCK_EXIT {result.returncode} uuid={args.uuid} frames={args.start}..{args.stop}", flush=True)
raise SystemExit(result.returncode)
