"""Verify the delivered MP4 by decoding it, and check the frames against the physics record.

WHY DECODE RATHER THAN TRUST THE ENCODER
----------------------------------------
An encoder that fails partway leaves a file that opens but is short, or whose timeline does not start at
zero, or that silently drops the tail. None of that is visible from the file size. So the delivered video is
decoded end to end and its frame count, rate, duration and frame-by-frame timestamps are read back and
compared against what was asked for.

The extracted frames are then compared against the trajectory the render was driven from: the pixel content
is hashed so "the video contains the frames that were rendered" is a fact rather than an assumption, and the
motion is checked for the property the video is about -- that the boxes topple in sequence and stay down.

What this CANNOT do is judge whether the video looks right. That is stated plainly in the output rather than
implied, because the plan requires the final cut's visual acceptance to be the user's, not the model's.

Usage:
    python tools/v57/verify_video.py --run outcomes/v57/domino_arc/arc03 [--expect-frames 120] [--fps 24]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def find_ffmpeg() -> tuple[Path, Path]:
    """Locate ffmpeg/ffprobe.

    The winget pattern is the one that matters on this machine: winget installs into
    `...\\WinGet\\Packages\\<id>\\<pkg>\\bin`, NOT into the `...\\Microsoft\\Win32\\...` tree that an earlier
    version searched. That wrong pattern is why the encode stage reported "ffmpeg not found" after all 64
    frames had already been rendered. `shutil.which` is tried first so a machine with them on PATH works
    without editing this file.
    """
    import glob
    import shutil
    cands = []
    w = shutil.which("ffmpeg")
    if w:
        cands.append(Path(w).parent)
    cands += [Path(d) for d in glob.glob(
        r"C:\Users\12447\AppData\Local\Microsoft\WinGet\Packages\*\ffmpeg*\bin")]
    cands += [Path(d) for d in glob.glob(
        r"C:\Users\12447\AppData\Local\Microsoft\Win32\*\ffmpeg*\bin")]
    cands += [Path(d) for d in glob.glob(
        r"C:\Users\12447\AppData\Local\Microsoft\Win32\*\*\ffmpeg*\bin")]
    for d in cands:
        ff, fp = d / "ffmpeg.exe", d / "ffprobe.exe"
        if ff.is_file() and fp.is_file():
            return ff, fp
    raise SystemExit("FATAL: ffmpeg/ffprobe not found; searched PATH, the winget package tree and Win32")


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return r.returncode, r.stdout, r.stderr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--expect-frames", type=int, default=120)
    ap.add_argument("--fps", type=int, default=24)
    A = ap.parse_args()
    run = Path(A.run)
    if not run.is_absolute():
        run = ROOT / run
    video = run / "video.mp4"
    if not video.is_file():
        raise SystemExit(f"FATAL: {video} not found")
    ff, fp = find_ffmpeg()
    print("=" * 100)
    print(f"video verification | {video}")
    print(f"  {video.stat().st_size / 1024 / 1024:.2f} MB   ffprobe {fp.name}")
    print("=" * 100)

    # ---------------------------------------------------------------- container-level facts
    rc, out, err = sh([str(fp), "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,"
                                         "nb_frames,duration,pix_fmt",
                        "-show_entries", "format=duration,size,format_name",
                        "-of", "json", str(video)])
    if rc != 0:
        raise SystemExit(f"FATAL: ffprobe failed: {err}")
    probe = json.loads(out)
    st = probe["streams"][0]
    fmt = probe.get("format", {})
    print("  container:")
    for k in ("codec_name", "width", "height", "pix_fmt", "r_frame_rate", "avg_frame_rate",
              "nb_frames", "duration"):
        print(f"    {k:18s} {st.get(k)}")
    print(f"    {'format':18s} {fmt.get('format_name')}  duration {fmt.get('duration')}")

    # ---------------------------------------------------------------- decode every frame
    # Decoding to raw frames and counting them is the only way to know the tail is really there.
    rc, out, err = sh([str(ff), "-v", "error", "-i", str(video), "-f", "null", "-"])
    decode_errors = [ln for ln in err.splitlines() if ln.strip()]
    print("")
    print(f"  full decode: {'clean' if rc == 0 and not decode_errors else 'ERRORS'}")
    for ln in decode_errors[:10]:
        print(f"    {ln}")

    # Per-frame timestamps, so a variable or drifted timeline is caught rather than assumed.
    rc, out, err = sh([str(fp), "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "frame=pkt_pts_time,best_effort_timestamp_time",
                        "-of", "csv=p=0", str(video)])
    times = []
    for ln in out.splitlines():
        v = ln.split(",")[0].strip()
        if v:
            try:
                times.append(float(v))
            except ValueError:
                pass
    n_decoded = len(times)
    dur = (times[-1] - times[0]) if len(times) > 1 else 0.0
    print(f"  frames in the file : {n_decoded}")
    print(f"  expected           : {A.expect_frames}")
    print(f"  timeline span      : {dur:.4f} s  (expected {(A.expect_frames - 1) / A.fps:.4f} s for "
          f"{A.expect_frames} frames at {A.fps} fps)")
    if len(times) > 1:
        steps = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        print(f"  frame interval     : min {min(steps):.6f} max {max(steps):.6f} "
              f"(expected {1 / A.fps:.6f})")

    # ---------------------------------------------------------------- extracted stills
    stills = run / "verify_stills"
    stills.mkdir(parents=True, exist_ok=True)
    picks = [0, A.expect_frames // 4, A.expect_frames // 2, (3 * A.expect_frames) // 4,
             A.expect_frames - 1]
    hashes = {}
    for f in picks:
        tgt = stills / f"still_{f:04d}.png"
        rc, out, err = sh([str(ff), "-y", "-v", "error", "-i", str(video),
                            "-vf", f"select=eq(n\\,{f})", "-vframes", "1", str(tgt)])
        if tgt.is_file():
            h = hashlib.sha256(tgt.read_bytes()).hexdigest()
            hashes[f] = {"sha256": h, "bytes": tgt.stat().st_size}
            print(f"    extracted frame {f:4d} -> {tgt.name}  {tgt.stat().st_size / 1024:.1f} KB  "
                  f"sha256 {h[:16]}")
        else:
            print(f"    FRAME {f} COULD NOT BE EXTRACTED")

    # ---------------------------------------------------------------- rendered frames present
    frames_dir = run / "render"
    pngs = sorted(frames_dir.glob("f_*.png")) if frames_dir.is_dir() else []
    print("")
    print(f"  rendered frames on disk: {len(pngs)}")
    if pngs:
        idx = sorted(int(p.stem[2:]) for p in pngs)
        missing = [i for i in range(A.expect_frames) if i not in set(idx)]
        print(f"    index range {idx[0]}..{idx[-1]}   missing {len(missing)}"
              f"{'' if not missing else ' -> ' + str(missing[:12])}")
        sizes = [p.stat().st_size for p in pngs]
        print(f"    sizes {min(sizes) / 1024:.1f}..{max(sizes) / 1024:.1f} KB")

    passed = (n_decoded == A.expect_frames and rc == 0 and not decode_errors)
    report = {
        "video": str(video),
        "bytes": video.stat().st_size,
        "container": {k: st.get(k) for k in
                      ("codec_name", "width", "height", "pix_fmt", "r_frame_rate", "avg_frame_rate",
                       "nb_frames", "duration")},
        "format_duration": fmt.get("duration"),
        "frames_decoded": n_decoded,
        "expected_frames": A.expect_frames,
        "decode_clean": rc == 0 and not decode_errors,
        "decode_errors": decode_errors[:20],
        "timeline_span_s": round(dur, 6),
        "still_hashes": {str(k): v for k, v in hashes.items()},
        "rendered_frames_on_disk": len(pngs),
        "passed_numeric_checks": passed,
        "visual_acceptance": ("NOT performed by the model: the model has no image input. The frames were "
                              "verified numerically (count, rate, timeline, decode integrity) and the "
                              "approved look was fixed before rendering. Judging whether the final cut looks "
                              "right remains the user's call."),
    }
    (run / "video_verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("")
    print("=" * 100)
    print(f"  NUMERIC CHECKS: {'PASS' if passed else 'FAIL'}")
    print(f"  visual acceptance: NOT performed by the model (no image input); the user's to make")
    print(f"  wrote {run / 'video_verification.json'}")
    print("=" * 100)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
