"""V5.6 section 8.2: measure the real per-frame cost of a scene before fixing the delivery tier.

The plan requires the cost of the first frame, the collision frame and the last frame to be measured
per scene BEFORE choosing a resolution and sample count, and it names a fallback tier of
1280x720 at 16-24 spp. Guessing from another scene's numbers is not acceptable, and neither is
quoting a single averaged figure: the first frame of a Cycles render carries one-time costs (texture
decode, BVH build, light importance maps) that later frames do not, so an average over a short run
misstates the marginal cost and therefore the whole delivery schedule.

This measures both separately and reports:

  * `first_frame_seconds`         -- setup + sampling for the first frame
  * `marginal_seconds_per_frame`  -- the mean of the frames after the first, which is what the
                                     remaining N-1 frames of a clip actually cost
  * `estimated_clip_seconds`      -- first + (frames-1) * marginal, for the frame counts the two
                                     videos need
  * peak process memory, since the local machine has 15.7 GB and this scene already peaked near
    9 GB, so memory can bind before time does

All tiers run inside ONE Blender session so the scene is opened and its textures decoded once; that
is the realistic pattern for a render job and it keeps the comparison between tiers fair.

    blender.exe --background --factory-startup --python tools\\v56\\measure_cost.py -- \
        --blend <runtime.blend> --out <dir> --tiers 960x540:16,1280x720:16 --frames 1,48,96
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import bpy

argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []
A = {"blend": "", "out": "", "tiers": "960x540:16", "frames": "1,2", "threads": "8",
     "scene_frames": "2", "camera": "", "threshold": "0.01", "denoise": "1", "bounces": "6"}
i = 0
while i < len(argv):
    if argv[i].startswith("--"):
        k = argv[i][2:]
        v = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else "1"
        A[k] = v
        i += 2
    else:
        i += 1

TARGET_BLEND = Path(A["blend"])
OUT = Path(A["out"])
OUT.mkdir(parents=True, exist_ok=True)
THREADS = int(A["threads"])
FRAMES = [int(v) for v in A["frames"].split(",") if v.strip()]
TIERS = []
for t in A["tiers"].split(","):
    t = t.strip()
    if not t:
        continue
    r, s = t.split(":")
    x, y = r.lower().split("x")
    TIERS.append((int(x), int(y), int(s)))

print("=" * 100)
print(f"cost measurement (plan section 8.2)")
print(f"  blend  {TARGET_BLEND}  ({TARGET_BLEND.stat().st_size / 1048576:.1f} MiB)")
print(f"  tiers  {TIERS}")
print(f"  frames {FRAMES}   threads {THREADS}   logical cpus {os.cpu_count()}")

t_open = time.time()
bpy.ops.wm.open_mainfile(filepath=str(TARGET_BLEND))
scene = bpy.context.scene
open_s = time.time() - t_open
print(f"  opened in {open_s:.2f} s: {len(scene.objects)} objects, "
      f"camera {scene.camera.name if scene.camera else None}")

if A["camera"]:
    c = bpy.data.objects.get(A["camera"])
    if c is None:
        raise SystemExit(f"FATAL: camera '{A['camera']}' not found")
    scene.camera = c
    print(f"  active camera forced to {c.name}")
if scene.camera is None:
    raise SystemExit("FATAL: no active camera; the cost is meaningless without one")

# Fixed render settings. Only the tier varies, so a tier difference cannot be a settings difference.
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = False
# THE COMPOSITOR MUST BE DISABLED, and this is not a preference.
#
# The Hidden Alley source scene's compositor renders a SECOND volumetric Fog scene. Measured on
# 2026-09-28 it exceeded 25 GiB of private memory without ever writing a file, and the same blowup
# recurred in this very script at 15:34 on 2026-09-29: the process reached 25,793 MB private and
# 26,469 MB of pagefile on a 15.7 GB machine, leaving 0.45 GB free, and then made no progress at all
# for 50 minutes while it thrashed. Disabling compositing is what the accepted asset-review render
# already does (`tools/v5_audit_render_hidden_alley_local.ps1` passes `--disable-compositing`, with
# the comment that the compositor "renders a second volumetric Fog scene and exceeded 25 GiB").
#
# The scene's geometry, 7 author lights, World and materials are all untouched by this: only the
# compositing step is skipped. `tools/v56/render.py` disables it too, so a cost measured here is
# representative of a delivered frame.
scene.render.use_compositing = False
print(f"  compositing DISABLED (the authored compositor renders a second volumetric Fog scene and "
      f"exceeded 25 GiB private memory without writing a file)")
scene.cycles.use_denoising = True
scene.cycles.max_bounces = int(A["bounces"])
scene.cycles.diffuse_bounces = min(2, int(A["bounces"]))
scene.cycles.glossy_bounces = min(3, int(A["bounces"]))
scene.cycles.transmission_bounces = min(6, int(A["bounces"]))
scene.cycles.transparent_max_bounces = min(8, max(4, int(A["bounces"])))
scene.cycles.volume_bounces = 0
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = float(A["threshold"])
# Denoising cost is not negligible on a CPU and the plan requires it be part of the measured budget
# rather than assumed, so it is switchable and recorded.
scene.cycles.use_denoising = bool(int(A["denoise"]))
if hasattr(scene.cycles, "denoiser"):
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
# Persistent data is what makes the marginal frame cheap: geometry and BVH survive between frames.
# Without it every frame repays the setup cost, which is precisely the 185 -> 56.6 s/frame effect
# measured in stage 05.
scene.render.use_persistent_data = True
scene.render.threads_mode = "FIXED"
scene.render.threads = THREADS
print(f"  threads FIXED at {THREADS}, persistent_data ON")

scene_end = int(A["scene_frames"])
if scene.frame_end < scene_end:
    scene.frame_end = scene_end


def peak_rss_mb():
    """Peak working set of this process. Blender exposes no direct call, so it is read from the OS.

    On Windows this uses GetProcessMemoryInfo through ctypes; if that is unavailable the value is
    reported as None rather than as a misleading zero.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        c = PROCESS_MEMORY_COUNTERS()
        c.cb = ctypes.sizeof(c)
        h = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
            return c.PeakWorkingSetSize / 1048576.0
    except Exception:
        return None
    return None


results = []
for (rx, ry, spp) in TIERS:
    scene.render.resolution_x = rx
    scene.render.resolution_y = ry
    scene.render.resolution_percentage = 100
    scene.cycles.samples = spp
    tag = f"{rx}x{ry}_{spp}spp"
    print(f"\n=== tier {tag} ===")
    d = OUT / f"cost_{tag}"
    d.mkdir(parents=True, exist_ok=True)
    per = []
    for k, f in enumerate(FRAMES):
        scene.frame_set(f)
        p = d / f"f_{f:04d}.png"
        scene.render.filepath = str(p)
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        dt = time.time() - t0
        if not p.is_file():
            raise SystemExit(f"FATAL: {p} was not written; the timing would be meaningless")
        per.append({"frame": f, "seconds": dt, "bytes": p.stat().st_size,
                    "is_first_in_session": k == 0 and not results})
        print(f"  frame {f:4d}  {dt:8.2f} s  {p.stat().st_size / 1024:9.1f} KB"
              + ("   (first frame in this session: includes one-time setup)" if per[-1]["is_first_in_session"] else ""))
    first = per[0]["seconds"]
    rest = [x["seconds"] for x in per[1:]]
    marginal = sum(rest) / len(rest) if rest else first
    entry = {"tier": tag, "resolution": [rx, ry], "spp": spp, "threads": THREADS,
             "frames": per, "first_frame_seconds": first,
             "marginal_seconds_per_frame": marginal,
             "peak_rss_mb": peak_rss_mb(),
             "note": ("the first frame carries texture decode and BVH build; the marginal figure is "
                      "the mean of the frames after it and is what the rest of a clip costs")}
    for n_frames, label in ((96, "video A ~4 s at 24 fps"), (120, "video B ~5 s at 24 fps")):
        entry[f"estimated_clip_seconds_{n_frames}_frames"] = first + (n_frames - 1) * marginal
        entry[f"label_{n_frames}"] = label
    results.append(entry)
    print(f"  first {first:.2f} s | marginal {marginal:.2f} s/frame | "
          f"peak RSS {entry['peak_rss_mb']}")
    for n in (96, 120):
        est = entry[f"estimated_clip_seconds_{n_frames}_frames"]
        print(f"    {n} frames -> {est / 3600:.2f} h")

report = {
    "blend": str(TARGET_BLEND), "blend_bytes": TARGET_BLEND.stat().st_size,
    "open_seconds": open_s, "threads": THREADS, "logical_cpus": os.cpu_count(),
    "camera": scene.camera.name,
    "resolution_independent_settings": {
        "engine": "CYCLES", "device": "CPU", "denoising": bool(int(A["denoise"])),
        "max_bounces": 6, "diffuse_bounces": 2, "glossy_bounces": 3,
        "transmission_bounces": 6, "transparent_max_bounces": 8, "volume_bounces": 0,
        "adaptive_sampling": True, "adaptive_threshold": float(A["threshold"]),
        "persistent_data": True, "compositing": False,
        "denoiser": getattr(scene.cycles, "denoiser", None),
    },
    "tiers": results,
    "method": ("all tiers measured in one Blender session so the one-time texture/BVH cost is "
               "attributed to the first frame rather than smeared across every tier"),
}
(OUT / "cost_measurement.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

print("\n=== section 8.2 verdict ===")
for e in results:
    print(f"  {e['tier']:16s} first {e['first_frame_seconds']:7.2f} s  marginal "
          f"{e['marginal_seconds_per_frame']:7.2f} s/frame  120 frames -> "
          f"{e['estimated_clip_seconds_120_frames'] / 3600:5.2f} h")
print(f"\nwritten: {OUT / 'cost_measurement.json'}")
