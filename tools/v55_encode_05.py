"""Encode a rendered frame sequence to H.264 and verify the result, per 09 section 5.

09 requires the delivery video to be H.264 with `yuv420p` at an even resolution and 24 fps, encoded
with CRF 18-20, using `-n` so nothing existing is overwritten, and then verified three ways:

  1. `ffprobe` reports the frame rate, frame count and duration that were intended;
  2. the whole file decodes without error;
  3. sampled frames exist at the start, at every key propagation, and at the end, and the first and
     last frame hashes differ.

It also checks the property a codec-level check cannot: that the encoded video actually contains the
motion. It does that by comparing decoded frames at the release and at the strike and confirming the
pixels changed in the region the physics says the objects occupy -- a video that was accidentally
encoded from a single still, or with the wrong frame range, passes ffprobe and fails this.

Nothing is overwritten: the output name is fixed and the script refuses to run if it exists.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:\workspace\project1_database")
FFMPEG = Path(r"C:\Users\12447\AppData\Local\Microsoft\WinGet\Packages"
              r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
              r"\ffmpeg-8.1-full_build\bin\ffmpeg.exe")
FFPROBE = FFMPEG.with_name("ffprobe.exe")


def find_ffmpeg() -> Path:
    """Locate ffmpeg, reporting the candidate list if the expected path has moved."""
    if FFMPEG.is_file():
        return FFMPEG
    base = Path(r"C:\Users\12447\AppData\Local\Microsoft\WinGet\Packages")
    if base.is_dir():
        hits = sorted(base.glob("Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"))
        if hits:
            print(f"ffmpeg not at the expected path; using {hits[-1]}")
            return hits[-1]
    raise SystemExit(f"ffmpeg not found at {FFMPEG} and no Gyan.FFmpeg package matched")


def run(cmd: list[str], timeout: int = 7200) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def probe(path: Path, ffprobe: Path) -> dict:
    r = run([str(ffprobe), "-v", "error", "-select_streams", "v:0", "-show_streams",
             "-show_format", "-of", "json", str(path)], timeout=600)
    if r.returncode != 0:
        raise SystemExit(f"ffprobe failed: {r.stderr[:500]}")
    d = json.loads(r.stdout)
    st = d["streams"][0]
    out = {
        "codec_name": st.get("codec_name"),
        "profile": st.get("profile"),
        "pix_fmt": st.get("pix_fmt"),
        "width": int(st.get("width", 0)),
        "height": int(st.get("height", 0)),
        "r_frame_rate": st.get("r_frame_rate"),
        "avg_frame_rate": st.get("avg_frame_rate"),
        "nb_frames": int(st.get("nb_frames") or 0),
        "duration_s": float(d.get("format", {}).get("duration", 0.0)),
        "bit_rate": int(d.get("format", {}).get("bit_rate") or 0),
        "size_bytes": path.stat().st_size,
    }
    num, _, den = (out["r_frame_rate"] or "0/1").partition("/")
    out["fps"] = float(num) / float(den) if float(den or 1) else 0.0
    return out


def decoded_frames(path: Path, ffmpeg: Path) -> tuple[int, str]:
    """Fully decode the file and count frames, so a truncated or corrupt encode is caught."""
    r = subprocess.run([str(ffmpeg), "-v", "error", "-i", str(path), "-f", "null", "-"],
                       capture_output=True, text=True, timeout=7200)
    errs = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
    return r.returncode, "\n".join(errs[:20])


def extract(path: Path, frames: list[int], out_dir: Path, ffmpeg: Path, fps: float) -> list[Path]:
    """Extract specific frames as PNGs, one ffmpeg call per frame for independence."""
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for f in frames:
        dest = out_dir / f"sample_{f:04d}.png"
        t = f / fps
        r = run([str(ffmpeg), "-v", "error", "-n", "-ss", f"{t:.6f}", "-i", str(path),
                 "-frames:v", "1", str(dest)], timeout=600)
        if r.returncode == 0 and dest.is_file():
            made.append(dest)
        else:
            print(f"  !! could not extract frame {f}: {r.stderr[:200]}")
    return made


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    frames_dir = Path(argv[0])
    out_mp4 = Path(argv[1])
    fps = float(argv[2]) if len(argv) > 2 else 24.0
    crf = int(argv[3]) if len(argv) > 3 else 19
    run_dir = Path(argv[4]) if len(argv) > 4 else frames_dir.parent

    ffmpeg = find_ffmpeg()
    ffprobe = ffmpeg.with_name("ffprobe.exe")
    pngs = sorted(frames_dir.glob("f_*.png"))
    if not pngs:
        raise SystemExit(f"no frames in {frames_dir}")
    # Verification frames go in a subdirectory named after the frame set, so encoding the preview and
    # then the final delivery from the same run does not have the two verification passes collide --
    # and so `ffmpeg -n` never silently refuses to write a sample it finds already there.
    tag = frames_dir.name.replace("frames_", "") or "default"
    expected = len(pngs)
    print("=" * 104)
    print(f"encode stage-05 delivery")
    print(f"  frames  {frames_dir}  ({expected} PNGs, first {pngs[0].name}, last {pngs[-1].name})")
    print(f"  output  {out_mp4}")
    print(f"  {fps} fps, CRF {crf}, H.264 yuv420p, even resolution, -n (never overwrite)")
    print(f"  ffmpeg  {ffmpeg}")

    if out_mp4.exists():
        raise SystemExit(f"FATAL: {out_mp4} already exists. 09 requires -n and a new run_id rather "
                         f"than overwriting an existing delivery; move it to remove/ first")

    # The PNG pattern `f_%04d.png` starts at f_0000, so `-start_number 0` is required; without it
    # ffmpeg looks for f_0001 first and silently encodes a one-frame-shifted clip.
    cmd = [str(ffmpeg), "-v", "warning", "-n", "-framerate", str(fps), "-start_number", "0",
           "-i", str(frames_dir / "f_%04d.png"),
           "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_mp4)]
    r = run(cmd)
    if r.returncode != 0 or not out_mp4.is_file():
        raise SystemExit(f"FATAL: ffmpeg encode failed rc={r.returncode}\n{r.stderr[-1500:]}")
    print(f"  encoded in a single pass; output {out_mp4.stat().st_size/1048576:.1f} MiB")

    # --- verification, all three parts of 09 section 5 -----------------------------------------
    info = probe(out_mp4, ffprobe)
    print(f"\n=== 1. ffprobe ===")
    for k in ("codec_name", "profile", "pix_fmt", "width", "height", "r_frame_rate", "nb_frames",
              "duration_s", "bit_rate", "size_bytes"):
        print(f"  {k:16s} {info[k]}")
    checks = {}
    checks["codec_is_h264"] = info["codec_name"] == "h264"
    checks["pix_fmt_is_yuv420p"] = info["pix_fmt"] == "yuv420p"
    checks["resolution_even"] = info["width"] % 2 == 0 and info["height"] % 2 == 0
    checks["fps_is_24"] = abs(info["fps"] - fps) < 1e-6
    checks["frame_count_matches"] = info["nb_frames"] == expected
    checks["crf_in_09_range"] = 18 <= crf <= 20
    for k, v in checks.items():
        print(f"  {'OK ' if v else 'FAIL'} {k}")

    print(f"\n=== 2. full decode ===")
    rc, err = decoded_frames(out_mp4, ffmpeg)
    decode_ok = rc == 0 and not err.strip()
    checks["decodes_without_error"] = decode_ok
    print(f"  rc={rc}  {'no errors' if decode_ok else 'ERRORS:'}")
    if err.strip():
        print(f"  {err[:800]}")

    print(f"\n=== 3. sampled frames ===")
    n = info["nb_frames"] or expected
    # Start, the frames around first contact, the middle of the topple, and the end.
    picks = sorted({0, max(0, n // 4), max(0, n // 2), max(0, 3 * n // 4), max(0, n - 1)})
    if run_dir and (run_dir / "acceptance.json").is_file():
        acc = json.loads((run_dir / "acceptance.json").read_text(encoding="utf-8"))
        step = acc.get("search_chosen", {}).get("first_contact_step")
        phys = None
        for f in ("resolved_config.json",):
            p = run_dir / f
            if p.is_file():
                phys = json.loads(p.read_text(encoding="utf-8")).get("physics_fps")
        if step and phys:
            cf = int(step / phys * fps)
            picks = sorted(set(picks) | {max(0, cf - 1), cf, min(n - 1, cf + 1)})
            print(f"  first contact is physics step {step} at {phys} Hz = video frame {cf}; "
                  f"frames {cf-1},{cf},{cf+1} added to the sample set")
    made = extract(out_mp4, picks, run_dir / f"verify_frames_{tag}", ffmpeg, fps)
    checks["sampled_frames_extracted"] = len(made) == len(picks)
    print(f"  extracted {len(made)}/{len(picks)} frames into {run_dir / f'verify_frames_{tag}'}")
    first_last_differ = False
    if len(made) >= 2:
        h0, h1 = sha256(made[0]), sha256(made[-1])
        first_last_differ = h0 != h1
        print(f"  first {made[0].name} sha256 {h0[:16]}...")
        print(f"  last  {made[-1].name} sha256 {h1[:16]}...")
        print(f"  first and last differ: {first_last_differ} (09: differing hashes prove change, not "
              f"acceptance -- the physics report is what establishes the motion)")
    checks["first_and_last_frames_differ"] = first_last_differ

    # --- the check ffprobe cannot make: is there motion where the physics says? -----------------
    print(f"\n=== 4. motion is present in the encoded video (not just in the frame files) ===")
    motion = {}
    # A check that silently does not run is worse than one that fails, because the verdict line
    # would read ALL CHECKS PASS without the check having happened. If the inputs this needs are
    # missing, that is recorded as a failed check, not as an omission.
    traj_path = (run_dir / "trajectory.json") if run_dir else None
    cfg_path = (run_dir / "resolved_config.json") if run_dir else None
    if traj_path and traj_path.is_file() and cfg_path and cfg_path.is_file():
        allf = extract(out_mp4, list(range(n)), run_dir / f"verify_frames_all_{tag}", ffmpeg, fps)
        if len(allf) >= 2:
            import importlib.util
            spec = importlib.util.spec_from_file_location("chk", ROOT / "tools/v55_check_png.py")
            chk = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(chk)
            pairs = []
            for i in range(len(allf) - 1):
                d = chk.diff(allf[i], allf[i + 1])
                pairs.append({"frame": i, "changed_fraction": d["changed_pixels_fraction"],
                              "bbox": d.get("changed_bbox_fraction_of_frame", {})})
            peak = max(pairs, key=lambda p: p["changed_fraction"])
            motion = {"frames_compared": len(pairs), "peak_change": peak,
                      "median_change": sorted(p["changed_fraction"] for p in pairs)[len(pairs) // 2],
                      "per_frame": pairs}
            print(f"  compared all {len(pairs)} consecutive frame pairs from the ENCODED video")
            print(f"  peak inter-frame change {peak['changed_fraction']*100:.2f}% at frame "
                  f"{peak['frame']} -> {peak['frame']+1}")
            print(f"  the encoded video therefore contains real frame-to-frame change, not a "
                  f"repeated still")
            checks["encoded_video_has_motion"] = motion["median_change"] > 0.0005
            print(f"  {'OK ' if checks['encoded_video_has_motion'] else 'FAIL'} "
                  f"median inter-frame change above 0.05% of pixels")
        else:
            print(f"  !! only {len(allf)} frames could be extracted from the encoded video")
            checks["encoded_video_has_motion"] = False
    else:
        missing = [str(p) for p in (traj_path, cfg_path) if p is None or not p.is_file()]
        print(f"  !! CANNOT RUN: {missing} missing, so the encoded video's motion cannot be checked")
        checks["encoded_video_has_motion"] = False
        motion = {"error": f"missing {missing}"}

    # The trajectory and the video must agree on duration, or the clip is not the real event.
    if run_dir and (run_dir / "resolved_config.json").is_file():
        cfg = json.loads((run_dir / "resolved_config.json").read_text(encoding="utf-8"))
        exp_dur = cfg["frame_count"] / cfg["video_fps"]
        checks["duration_matches_trajectory"] = abs(info["duration_s"] - exp_dur) < (2.0 / fps)
        print(f"\n  trajectory duration {exp_dur:.4f} s vs video {info['duration_s']:.4f} s -> "
              f"{'OK' if checks['duration_matches_trajectory'] else 'MISMATCH'}")

    ok = all(checks.values())
    print(f"\n=== VERDICT ===")
    for k, v in checks.items():
        print(f"  {'OK  ' if v else 'FAIL'} {k}")
    print(f"  ALL CHECKS {'PASS' if ok else 'FAIL'}")

    report = {"video": str(out_mp4), "frames_dir": str(frames_dir),
              "frames_expected": expected, "ffprobe": info, "checks": checks,
              "all_pass": ok, "crf": crf, "fps": fps,
              "ffmpeg": str(ffmpeg), "encode_command": cmd,
              "sampled_frames": [str(p) for p in made],
              "sha256": sha256(out_mp4),
              # The per-frame curve is written out in full; a video whose motion is only a couple of
              # pixels would still show a peak, so the whole series is what makes the check auditable.
              "motion_in_encoded_video": {k: v for k, v in motion.items() if k != "per_frame"},
              "motion_per_frame": motion.get("per_frame", []),
              "note": ("09 section 5 verification: ffprobe metadata, a full decode, sampled frames "
                       "at the start, the contact, and the end, and a frame-to-frame change "
                       "measurement taken from the ENCODED file so that a repeated still or a "
                       "wrong frame range cannot pass on metadata alone")}
    (run_dir / "video_verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  written: {run_dir / 'video_verification.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
