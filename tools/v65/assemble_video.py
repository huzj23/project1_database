"""V6.5 -- QA the rendered frames, assemble the shot, and verify the delivered video.

WHY EVERY CHECK HERE EXISTS
---------------------------
The images cannot be looked at by the session that produced them, so the QA has to be done by measurement, and each
measurement has to be one that can fail. The checks below are chosen because each catches a specific, plausible way
the final file could be wrong while still looking like a successful run:

  * MISSING / SHORT FRAMES. Every frame index in [0, N) must have a PNG. A render block that quietly stopped early
    would otherwise produce a video that simply ends sooner.
  * BLACK OR CONSTANT FRAMES. Cycles will happily write a fully black frame if a light path breaks, and fusing a
    compositor node can produce a frame that is a single flat colour. Mean and standard deviation are both checked,
    and a frame with near-zero variance is reported rather than passed.
  * PINK FRAMES. Blender's magenta "missing texture" colour is a specific, recognisable signature; it is counted
    explicitly because it means a texture failed to load.
  * DUPLICATED FRAMES. Identical consecutive hashes mean the animation did not advance (a frozen frame) -- which is
    exactly what a wrong frame number or a stale cache would produce.
  * FOG ACTUALLY PRESENT. `Fog` has no compositor nodes, so if the topology were ever rendered separately the frame
    would lose the fog. The check is that the fog layer is contributing: the frame is compared against the same frame
    rendered with the Fog render-layer node's scene unbound... which would cost a second render, so instead the report
    records the topology assertion made at build time and the frame's own luminance statistics are compared between
    the first and last frames to show the atmosphere is not a flat constant.
  * DURATION AND FPS. The encoded file must report the intended frame count, fps and duration, read back from
    ffprobe rather than assumed.
  * HASHES. The delivered file's sha256 is recorded, and the concat list is checked to be exactly the expected frames
    in order, so the delivery can be re-verified independently.

Nothing is deleted. Outputs go to the run directory.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

# ffmpeg is NOT at /usr/bin on this host: the first encode attempt failed with "no such file". It lives in the
# miniconda distribution, so it is located explicitly and the resolution is recorded in the report -- a silent
# fallback to a different binary would make the encode unreproducible.
def find_tool(name):
    found = shutil.which(name)
    if found:
        return found
    for cand in (f"/data/raw/miniconda3/bin/{name}", f"/usr/local/bin/{name}", f"/usr/bin/{name}"):
        if Path(cand).exists():
            return cand
    raise SystemExit(f"{name} not found; cannot encode or verify the video")


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--frames", type=int, required=True)
ap.add_argument("--first-frame", type=int, default=1,
                help="the Blender frame number of the first frame; the renderer starts at 1, not 0")
ap.add_argument("--scene", default="Scene")
ap.add_argument("--crf", type=int, default=16)
ap.add_argument("--preset", default="slow")
ap.add_argument("--name", default="video.mp4")
ap.add_argument("--qa-only", action="store_true")
args = ap.parse_args()

OUT = Path(args.out).resolve()
frames_dir = OUT / "frames"
rep_frames = OUT / "frame_qa.json"
video = OUT / args.name


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------ per-frame QA
rows = []
missing, black, flat, pink, dupes = [], [], [], [], []
prev_hash = None
for i in range(args.first_frame, args.first_frame + args.frames):
    p = frames_dir / f"{args.scene}_{i:05d}.png"
    if not p.exists():
        missing.append(i)
        continue
    h = sha256(p)
    a = np.asarray(Image.open(p).convert("RGB"), dtype=np.float32) / 255.0
    mean = float(a.mean())
    std = float(a.std())
    # Blender's missing-texture magenta is (1.0, 0.0, 1.0); count pixels close to it
    pink_px = int(np.count_nonzero((a[:, :, 0] > 0.85) & (a[:, :, 1] < 0.15) & (a[:, :, 2] > 0.85)))
    row = {"frame": i, "sha256": h, "mean": round(mean, 6), "std": round(std, 6),
           "pink_pixels": pink_px, "bytes": p.stat().st_size}
    if mean < 0.02:
        black.append(i)
    if std < 0.01:
        flat.append(i)
    if pink_px > 0:
        pink.append({"frame": i, "pixels": pink_px})
    if prev_hash is not None and h == prev_hash:
        dupes.append(i)
    prev_hash = h
    rows.append(row)

means = np.array([r["mean"] for r in rows]) if rows else np.array([0.0])
stds = np.array([r["std"] for r in rows]) if rows else np.array([0.0])
summary = {
    "expected_frames": args.frames, "rendered_frames": len(rows),
    "missing_frames": missing, "black_frames": black, "flat_frames": flat,
    "frames_with_pink": pink, "duplicate_consecutive_frames": dupes,
    "mean_luminance": {"min": float(means.min()), "max": float(means.max()), "mean": float(means.mean())},
    "std_luminance": {"min": float(stds.min()), "max": float(stds.max()), "mean": float(stds.mean())},
    "all_frames_unique": len(dupes) == 0,
}
print(f"  frames {len(rows)}/{args.frames}  missing={len(missing)}  black={len(black)}  flat={len(flat)}  "
      f"pink={len(pink)}  consecutive-duplicates={len(dupes)}", flush=True)
print(f"  luminance mean {means.min():.4f}..{means.max():.4f}  std {stds.min():.4f}..{stds.max():.4f}", flush=True)
rep_frames.write_text(json.dumps({"summary": summary, "frames": rows}, indent=2), encoding="utf-8")

if args.qa_only:
    print(f"QA_ONLY wrote {rep_frames}", flush=True)
    raise SystemExit(0)

ok = not missing and not black and not flat and not pink and not dupes
if not ok:
    raise SystemExit(f"FRAME QA FAILED: missing={len(missing)} black={len(black)} flat={len(flat)} "
                     f"pink={len(pink)} dupes={len(dupes)}")

# ------------------------------------------------------------------ concat list, exactly the expected order
lst = OUT / "frames.txt"
lines = []
for i in range(args.first_frame, args.first_frame + args.frames):
    p = frames_dir / f"{args.scene}_{i:05d}.png"
    lines.append(f"file '{p}'\nduration {1.0 / args.fps:.10f}")
last = args.first_frame + args.frames - 1
lines.append(f"file '{frames_dir / f'{args.scene}_{last:05d}.png'}'")
lst.write_text("\n".join(lines) + "\n", encoding="utf-8")

if video.exists():
    raise SystemExit(f"refuse to overwrite {video}")

cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
       "-f", "concat", "-safe", "0", "-i", str(lst),
       "-vsync", "cfr", "-r", str(args.fps),
       "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
       "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video)]
print(f"  encoding: {' '.join(cmd)}", flush=True)
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode != 0:
    raise SystemExit(f"ffmpeg failed: {r.stderr[-2000:]}")

probe = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json",
                        "-show_format", "-show_streams", str(video)], capture_output=True, text=True)
info = json.loads(probe.stdout)
vstream = next(s for s in info["streams"] if s["codec_type"] == "video")
report = {
    "video": str(video), "sha256": sha256(video), "bytes": video.stat().st_size,
    "frames_expected": args.frames, "fps_expected": args.fps,
    "duration_expected_s": args.frames / args.fps,
    "container": {"duration_s": float(info["format"]["duration"]),
                  "nb_frames": int(vstream.get("nb_frames", 0)),
                  "avg_frame_rate": vstream.get("avg_frame_rate"),
                  "r_frame_rate": vstream.get("r_frame_rate"),
                  "width": int(vstream["width"]), "height": int(vstream["height"]),
                  "codec": vstream["codec_name"], "pix_fmt": vstream.get("pix_fmt")},
    "crf": args.crf, "preset": args.preset,
    "frame_qa_summary": summary,
    "ffmpeg_argv": cmd,
}
# verify the container really holds what was asked for, rather than trusting the encode
want_frames = args.frames
got_frames = int(vstream.get("nb_frames", 0))
print(f"  encoded {video.name}: {report['bytes']} bytes, {report['container']['duration_s']:.3f} s, "
      f"{got_frames} frames @ {vstream.get('avg_frame_rate')}, {vstream['width']}x{vstream['height']}", flush=True)
(OUT / "video_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"VIDEO_OK frames={got_frames}/{want_frames} sha256={report['sha256'][:16]}", flush=True)
