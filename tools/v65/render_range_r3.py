"""V6.5 -- render a deterministic frame RANGE of the film scene, one Blender process per block.

WHY BLOCKS RATHER THAN A SINGLE `bpy.ops.render.render(animation=True)`
----------------------------------------------------------------------
V6.5 plan section 2 (125-330 min) requires the full animation to be rendered in parallel, split into mutually exclusive
frame blocks by frame number, with a per-frame hash and a resumable checkpoint, so a failure costs one frame rather
than the whole render. A single Blender animation render is one process with one camera and one scene, which cannot be
parallelised, and if it dies at frame 200 the work is gone.

Frames are therefore addressed as explicit indices. Several workers may share one output directory as long as their
frame ranges are DISJOINT -- each writes its own `frames/Scene_%05d.png` and `frames_meta/Scene_%05d.json`, so no path
is ever written twice. A worker SKIPS frames whose PNG and sidecar already exist and verify, so a resumed or restarted
worker re-does only what is missing.

EVERY FRAME IS RENDERED ONCE, THROUGH THE MAIN SCENE'S COMPOSITOR
-----------------------------------------------------------------
The author's file has two scenes: `Scene` (Cycles, the main render) and `Fog` (EEVEE Next). It is tempting to render
both and combine them, and an earlier revision of this file did exactly that -- which would have been wrong twice
over: it doubles the cost, and `Fog` has ZERO compositor nodes, so its own output is a raw uncomposited layer that
would silently REPLACE the finished frame on disk.

`probe_fog_topology.py` settled it by reading the node bindings from the file: the main `Scene`'s compositor contains
`Render Layers.001` bound to scene `Fog`, so compositing `Scene` pulls the fog in automatically. Only `Scene` is
rendered, and the fog arrives inside the same frame. (That probe also caught its own predecessor's bug: it tested
`node.type == "RLAYER"` when Blender's identifier is `"R_LAYERS"`, so nothing matched and it printed `scene=None` for
every render-layer node -- a silent wrong answer of exactly the kind this project keeps finding.)

GPU POLICY (plan section 4)
---------------------------
Cycles runs on CPU; the `Fog` layer is EEVEE and needs a GPU, and it is evaluated as part of the `Scene` render, so
the graphics context belongs to this same process. The plan forbids using `CUDA_VISIBLE_DEVICES` as an isolation proof
and requires the actual device to be read back, so this script:
  * refuses to start if `CUDA_VISIBLE_DEVICES` is set (that would remap ordinals and make the readback ambiguous);
  * refuses to start without an authorised UUID;
  * after the first frame, reads back from the driver exactly which GPUs hold a context for THIS pid, and requires
    that set to be exactly the authorised UUID;
  * for every OTHER process on that GPU, reads `/proc/<pid>/cmdline` and requires it to be another worker of THIS run
    (same script, same output directory). The deadline makes it necessary for several of my own workers to share one
    card, so "the GPU is empty" is no longer the right test; "the GPU contains nobody but my own workers" is, and it
    is checked by inspecting each process rather than by trusting a count.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import bpy
import gpu

ROOT = Path("/data/raw/huzijian/project1_database")
ap = argparse.ArgumentParser()
ap.add_argument("--scene", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--start", type=int, required=True)
ap.add_argument("--stop", type=int, required=True, help="exclusive")
ap.add_argument("--threads", type=int, default=16)
ap.add_argument("--probe-only", action="store_true")
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])

OUT = Path(args.out).resolve()
if ROOT not in OUT.parents:
    raise ValueError("out outside workspace")
frames_dir = OUT / "frames"
frames_dir.mkdir(parents=True, exist_ok=True)
meta_dir = OUT / "frames_meta"
meta_dir.mkdir(parents=True, exist_ok=True)

expected_gpu = os.environ.get("V63_GPU_UUID") or os.environ.get("V65_GPU_UUID")
if expected_gpu and "CUDA_VISIBLE_DEVICES" in os.environ:
    raise RuntimeError("refuse CUDA ordinal remapping: the device readback would be ambiguous")
if not expected_gpu:
    raise RuntimeError("no authorised GPU UUID was passed; refusing to render without a device readback")


def _cmdline(pid):
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def actual_contexts():
    """Which GPUs hold a context for THIS pid, and who else is on the authorised one.

    A co-tenant is acceptable only if its own command line proves it is another worker of this same run: same render
    script and same output directory. Anything else -- a stranger's job, or a differently configured render -- stops
    this worker, because the plan requires the selected device to be attributable.
    """
    tree = ET.fromstring(subprocess.check_output(["/usr/bin/nvidia-smi", "-q", "-x"], text=True))
    mine, foreign = [], []
    for card in tree.findall("gpu"):
        for proc in card.findall(".//process_info"):
            pid = proc.findtext("pid")
            if pid == str(os.getpid()):
                mine.append(card.findtext("uuid"))
            elif card.findtext("uuid") == expected_gpu:
                cmd = _cmdline(pid)
                mine_worker = ("render_range" in cmd) and (str(OUT) in cmd)
                if mine_worker:
                    foreign.append({"pid": pid, "verdict": "own worker", "cmdline": cmd[:200]})
                else:
                    foreign.append({"pid": pid, "verdict": "FOREIGN", "cmdline": cmd[:200]})
    return mine, foreign


bpy.ops.wm.open_mainfile(filepath=str(Path(args.scene).resolve()))
main = bpy.data.scenes["Scene"]
bpy.context.window.scene = main
# ONLY the main scene is rendered: its compositor pulls the Fog scene through a bound Render Layers node, so the fog is
# composited into this same frame. `Fog` has no compositor nodes of its own and must never be rendered to disk.
scenes = [main]
main.render.threads_mode = "FIXED"
main.render.threads = args.threads
main.cycles.device = "CPU"
fog_bound = [n.scene.name for n in (main.node_tree.nodes if main.use_nodes else [])
             if n.type == "R_LAYERS" and getattr(n, "scene", None) is not None and n.scene.name != main.name]
if not fog_bound:
    raise RuntimeError("the main scene's compositor no longer pulls the Fog scene; the render topology changed")
print(f"RENDER_TOPOLOGY pid={os.getpid()} main={main.name} engine={main.render.engine} "
      f"fog_pulled_from={fog_bound} resolution={main.render.resolution_x}x{main.render.resolution_y} "
      f"fps={main.render.fps} range={args.start}..{args.stop}", flush=True)

rows = []
first = True
for frame in range(args.start, args.stop):
    p = frames_dir / f"{main.name}_{frame:05d}.png"
    m = meta_dir / f"{main.name}_{frame:05d}.json"
    if p.exists() and m.exists():
        try:
            prev = json.loads(m.read_text())
            if p.stat().st_size == prev["bytes"]:
                rows.append({"frame": frame, "reused": True, "seconds": prev["seconds"]})
                continue
        except Exception:
            pass

    t0 = time.time()
    bpy.context.window.scene = main
    main.camera = bpy.data.objects["v65_cam"]
    main.frame_set(frame)
    main.render.filepath = str(p)
    bpy.ops.render.render(write_still=True, scene=main.name)
    wall = time.time() - t0
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    m.write_text(json.dumps(
        {"scene": main.name, "frame": frame, "path": str(p), "sha256": h,
         "bytes": p.stat().st_size, "seconds": wall, "engine": main.render.engine,
         "samples": main.cycles.samples, "pid": os.getpid()}, indent=2), encoding="utf-8")

    device = {"renderer": gpu.platform.renderer_get(), "vendor": gpu.platform.vendor_get(),
              "egl_gpu_uuid": expected_gpu, "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES")}
    if first:
        mine, others = actual_contexts()
        device["observed_contexts_for_this_pid"] = mine
        device["other_processes_on_target_gpu"] = others
        if mine != [expected_gpu]:
            raise RuntimeError(f"graphics context is on {mine}, not the authorised {expected_gpu}")
        bad = [o for o in others if o["verdict"] == "FOREIGN"]
        if bad:
            raise RuntimeError(f"a process that is not a worker of this run is on the target GPU: {bad}")
        print(f"DEVICE_SCOPE pid={os.getpid()} on {mine} with {len(others)} co-tenant worker(s), all verified as "
              f"this run's own", flush=True)
        first = False

    rows.append({"frame": frame, "seconds": round(wall, 3), "device": device})
    print(f"FRAME {frame} {wall:.2f}s pid={os.getpid()}", flush=True)

(OUT / f"render_block_{args.start:05d}_{args.stop:05d}.json").write_text(
    json.dumps({"start": args.start, "stop": args.stop, "rows": rows,
                "device": {"renderer": gpu.platform.renderer_get(), "vendor": gpu.platform.vendor_get(),
                           "version": gpu.platform.version_get(), "egl_gpu_uuid": expected_gpu},
                "pid": os.getpid()}, indent=2, ensure_ascii=False), encoding="utf-8")
fresh = [r for r in rows if not r.get("reused")]
total = sum(r.get("seconds", 0) for r in fresh)
print(f"BLOCK_DONE {args.start}..{args.stop} pid={os.getpid()} rendered={len(fresh)} reused={len(rows) - len(fresh)} "
      f"total={total:.1f}s mean={total / max(1, len(fresh)):.2f}s", flush=True)
