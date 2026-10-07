"""V6.5 -- render a deterministic frame RANGE of the film scene, one Blender process per block.

WHY BLOCKS RATHER THAN A SINGLE `bpy.ops.render.render(animation=True)`
----------------------------------------------------------------------
V6.5 plan section 2 (125-330 min) requires the full animation to be rendered in parallel, split into mutually exclusive
frame blocks by frame number, with a per-frame hash and a resumable checkpoint, so a failure costs one frame rather
than the whole render. A single Blender animation render is one process with one camera and one scene, which cannot be
parallelised, and if it dies at frame 200 the work is gone.

Frames are therefore addressed as explicit indices. Each worker is given a disjoint half-open range, writes each frame
as its own PNG plus a sidecar JSON with the frame's hash and wall time, and SKIPS frames whose PNG and sidecar already
exist and verify -- so a resumed worker re-does only what is missing. Two workers never write the same path.

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
Cycles runs on CPU. The `Fog` layer is EEVEE and needs a GPU, and it is evaluated as part of the `Scene` render, so
the graphics context belongs to this same process. The plan forbids using `CUDA_VISIBLE_DEVICES` as an isolation
proof and requires the actual device to be read back, so this script:
  * refuses to start if `CUDA_VISIBLE_DEVICES` is set (that would remap ordinals and make the readback ambiguous);
  * records the renderer string and, after the first frame, the set of GPUs that actually have a context for THIS pid;
  * raises if that set is not exactly the one UUID the operator authorised.
It does not invent a device; the launcher passes `V65_GPU_UUID`.
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
ap.add_argument("--probe-only", action="store_true", help="render only the first frame, for the ETA trial")
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


def actual_contexts():
    """Which GPUs actually hold a context for THIS process, read back from the driver."""
    tree = ET.fromstring(subprocess.check_output(["/usr/bin/nvidia-smi", "-q", "-x"], text=True))
    mine, others = [], []
    for card in tree.findall("gpu"):
        for proc in card.findall(".//process_info"):
            if proc.findtext("pid") == str(os.getpid()):
                mine.append(card.findtext("uuid"))
            elif card.findtext("uuid") == expected_gpu:
                others.append(proc.findtext("pid"))
    return mine, others


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
print(f"RENDER_TOPOLOGY main={main.name} engine={main.render.engine} fog_pulled_from={fog_bound} "
      f"resolution={main.render.resolution_x}x{main.render.resolution_y} fps={main.render.fps}", flush=True)

rows = []
first = True
for frame in range(args.start, args.stop):
    pngs = {}
    ok_all = True
    for s in scenes:
        p = frames_dir / f"{s.name}_{frame:05d}.png"
        m = meta_dir / f"{s.name}_{frame:05d}.json"
        if p.exists() and m.exists():
            try:
                prev = json.loads(m.read_text())
                if p.stat().st_size == prev["bytes"]:
                    pngs[s.name] = {"path": str(p), "seconds": prev["seconds"], "resumed": True}
                    continue
            except Exception:
                pass
        pngs[s.name] = {"path": str(p), "resumed": False}
        ok_all = False
    if ok_all:
        rows.append({"frame": frame, "reused": True, "pieces": pngs})
        continue

    t0 = time.time()
    for s in scenes:
        if pngs[s.name].get("resumed"):
            continue
        bpy.context.window.scene = s
        s.camera = bpy.data.objects["v65_cam"]
        s.frame_set(frame)
        p = Path(pngs[s.name]["path"])
        s.render.filepath = str(p)
        bpy.ops.render.render(write_still=True, scene=s.name)
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        (meta_dir / f"{s.name}_{frame:05d}.json").write_text(json.dumps(
            {"scene": s.name, "frame": frame, "path": str(p), "sha256": h,
             "bytes": p.stat().st_size, "seconds": time.time() - t0,
             "engine": s.render.engine, "samples": (s.cycles.samples if s.render.engine == "CYCLES"
                                                    else getattr(s.eevee, "taa_render_samples", None))},
            indent=2), encoding="utf-8")
    wall = time.time() - t0

    device = {"renderer": gpu.platform.renderer_get(), "vendor": gpu.platform.vendor_get(),
              "egl_gpu_uuid": expected_gpu, "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES")}
    if expected_gpu and first:
        mine, others = actual_contexts()
        device["observed_contexts_for_this_pid"] = mine
        device["other_pids_on_target_gpu"] = others
        if mine != [expected_gpu]:
            raise RuntimeError(f"graphics context is on {mine}, not the authorised {expected_gpu}")
        if others:
            raise RuntimeError(f"another process appeared on the target GPU: {others}")
        first = False

    row = {"frame": frame, "seconds": round(wall, 3), "pieces": pngs, "device": device,
           "scene_names": [s.name for s in scenes]}
    rows.append(row)
    print(f"FRAME {frame} {wall:.2f}s " + " ".join(f"{s.name}={pngs[s.name].get('seconds', 0):.1f}s"
                                                  for s in scenes), flush=True)

(OUT / f"render_block_{args.start:05d}_{args.stop:05d}.json").write_text(
    json.dumps({"start": args.start, "stop": args.stop, "rows": rows,
                "device": {"renderer": gpu.platform.renderer_get(), "vendor": gpu.platform.vendor_get(),
                           "version": gpu.platform.version_get(), "egl_gpu_uuid": expected_gpu}},
               indent=2, ensure_ascii=False), encoding="utf-8")
total = sum(r.get("seconds", 0) for r in rows)
print(f"BLOCK_DONE {args.start}..{args.stop} frames={len(rows)} total={total:.1f}s "
      f"mean={total / max(1, len([r for r in rows if not r.get('reused')])):.2f}s", flush=True)
