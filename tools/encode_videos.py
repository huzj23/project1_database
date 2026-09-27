"""Encode a run's PNG frame sequence into preview mp4s.

The batches write lossless PNG frames (the source of truth for a dataset);
this turns them into watchable video for review:

    rgb.mp4            H.264 from rgba_*.png
    depth.mp4          H.264 from depth_*.png   (preview only)
    segmentation.mp4   H.264 from segmentation_*.png (preview only)

Quality is deliberately high (CRF 16, yuv420p) so the preview does not hide
artefacts that the PNGs would reveal.  Depth and segmentation previews are
tonemapped by ffmpeg's default conversion, so they are for eyeballing motion,
not for measurement -- the PNGs remain the measurable artefact.

Usage
-----
    python tools/encode_videos.py                       # every run under outcomes/
    python tools/encode_videos.py --root outcomes/dataset_real
    python tools/encode_videos.py --root outcomes/dataset_real --only cardgame
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ROOTS = [
    os.path.join(ROOT, "outcomes", "dataset_real"),
    os.path.join(ROOT, "outcomes", "dataset", "single_object"),
]

#: (layer tag, frame glob, output name)
LAYERS = [
    ("rgba", "rgb.mp4"),
    ("depth", "depth.mp4"),
    ("segmentation", "segmentation.mp4"),
]


def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    for c in (r"C:\ffmpeg\bin\ffmpeg.exe",
              os.path.join(ROOT, "tools", "runtime", "ffmpeg", "ffmpeg.exe")):
        if os.path.isfile(c):
            return c
    return None


def encode(ffmpeg: str, run_dir: str, layer: str, out_name: str,
           fps: int, crf: int, overwrite: bool) -> tuple[bool, str]:
    frames = sorted(f for f in os.listdir(run_dir)
                    if f.startswith(layer + "_") and f.endswith(".png"))
    if not frames:
        return False, "no frames"
    out = os.path.join(run_dir, out_name)
    if os.path.isfile(out) and not overwrite:
        return True, "exists"

    # derive the printf pattern and the first index from the actual filenames
    first = frames[0]
    stem, ext = os.path.splitext(first)
    digits = len(stem.split("_")[-1])
    start = int(stem.split("_")[-1])
    pattern = os.path.join(run_dir, f"{layer}_%0{digits}d{ext}")

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-framerate", str(fps), "-start_number", str(start),
           "-i", pattern,
           "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, (r.stderr or "").strip().splitlines()[-1][:90] if r.stderr else "ffmpeg failed"
    return True, f"{len(frames)} frames"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Encode PNG frame sequences to mp4.")
    ap.add_argument("--root", default=None,
                    help="one run-parent dir; defaults to every known dataset root")
    ap.add_argument("--only", default=None, help="substring filter on the run name")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("ERROR: ffmpeg not found on PATH", file=sys.stderr)
        return 2
    print(f"ffmpeg: {ffmpeg}")

    roots = [args.root] if args.root else DEFAULT_ROOTS
    t0 = time.time()
    n_runs = n_made = n_skip = n_fail = 0

    for root in roots:
        if not os.path.isdir(root):
            continue
        runs = sorted(d for d in os.listdir(root)
                      if os.path.isdir(os.path.join(root, d)))
        if args.only:
            runs = [r for r in runs if args.only in r]
        if not runs:
            continue
        print(f"\n{root}  ({len(runs)} runs)")
        for run in runs:
            rd = os.path.join(root, run)
            n_runs += 1
            made = []
            for layer, out_name in LAYERS:
                ok, msg = encode(ffmpeg, rd, layer, out_name, args.fps,
                                 args.crf, args.overwrite)
                if not ok:
                    if msg != "no frames":
                        n_fail += 1
                        print(f"  ! {run}/{out_name}: {msg}")
                    continue
                if msg == "exists":
                    n_skip += 1
                else:
                    n_made += 1
                    made.append(f"{out_name} ({msg})")
            if made:
                print(f"  {run}: " + ", ".join(made))

    dt = time.time() - t0
    print(f"\nruns={n_runs}  encoded={n_made}  already={n_skip}  failed={n_fail}"
          f"  in {dt/60:.1f} min")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
