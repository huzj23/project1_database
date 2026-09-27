"""Build a slim, shareable package: RGB video + physics annotation per run.

The full dataset is ~3.5 GB because it keeps lossless PNG frames for every layer
(rgba + depth + segmentation).  That is the right artefact for training or
measurement, but it is far too heavy to hand to a colleague.

This copies only what is needed to watch a clip and read its ground truth:

    <out>/<motion>/<run>/rgb.mp4        H.264, 1280x720, CRF 16
    <out>/<motion>/<run>/sample.json    per-frame physics annotation
    <out>/README.md                     schema + provenance
    <out>/INDEX.json                    machine-readable manifest

Typical size: ~1.2 MB per run, so the whole 36-clip batch lands around 45 MB
before compression -- roughly an order of magnitude below sharing the frames.

Usage
-----
    python tools/make_share_package.py --root outcomes/dataset_real
    python tools/make_share_package.py --root outcomes/dataset_interior --out outcomes/_分享包_D
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: what each run contributes to the package
FILES = [("rgb.mp4", "RGB video (H.264, CRF 16)"),
         ("sample.json", "per-frame physics annotation")]

MOTION_ORDER = ["circular", "damped", "rotation"]


def motion_of(run: str) -> str:
    """Map a run directory name onto its motion family."""
    name = run.lower()
    for m in MOTION_ORDER:
        if name.startswith(m) or name.startswith("d_" + m):
            return m
    return "other"


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {u}"
        n /= 1024.0
    return f"{n:.1f} TB"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build a slim share package.")
    ap.add_argument("--root", default=os.path.join(ROOT, "outcomes", "dataset_real"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--clean", action="store_true", help="wipe the target first")
    args = ap.parse_args(argv)

    out = args.out or os.path.join(os.path.dirname(args.root), "_share_package")
    if args.clean and os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)

    runs = sorted(d for d in os.listdir(args.root)
                  if os.path.isdir(os.path.join(args.root, d)))
    index = []
    total = 0
    per_motion: dict[str, list[str]] = {}

    for run in runs:
        motion = motion_of(run)
        src = os.path.join(args.root, run)
        dst = os.path.join(out, motion, run)

        copied = {}
        for fname, _desc in FILES:
            s = os.path.join(src, fname)
            if not os.path.isfile(s):
                continue
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(s, os.path.join(dst, fname))
            copied[fname] = os.path.getsize(s)

        if not copied:
            continue
        sz = sum(copied.values())
        total += sz
        per_motion.setdefault(motion, []).append(run)

        meta = {}
        mj = os.path.join(src, "sample.json")
        if os.path.isfile(mj):
            with open(mj, encoding="utf-8") as fh:
                meta = json.load(fh)
        index.append({
            "run": run,
            "motion": motion,
            "path": f"{motion}/{run}",
            "files": copied,
            "bytes": sz,
            "gso_object": meta.get("gso_object"),
            "backdrop": meta.get("backdrop"),
            "resolution": meta.get("resolution"),
            "frames": meta.get("frames"),
            "fps": meta.get("fps"),
            "motion_applied": meta.get("motion_applied"),
            "actor_pct_of_frame_width": meta.get("actor_pct_of_frame_width"),
            "camera_distance_m": meta.get("camera_distance_m"),
        })

    # --- manifest + README -------------------------------------------------
    with open(os.path.join(out, "INDEX.json"), "w", encoding="utf-8") as fh:
        json.dump({"count": len(index),
                   "total_bytes": total,
                   "by_motion": {k: len(v) for k, v in sorted(per_motion.items())},
                   "runs": index}, fh, indent=2, ensure_ascii=False)

    lines = [
        "# PhyCo-Sim single-object physics clips",
        "",
        f"{len(index)} clips, {human(total)} total (uncompressed).",
        "",
        "## Layout",
        "",
        "```",
    ]
    for m in MOTION_ORDER + ["other"]:
        if m in per_motion:
            lines.append(f"{m}/")
            for r in per_motion[m]:
                lines.append(f"    {r}/")
            lines.append("")
    lines += [
        "```",
        "",
        "Each clip directory holds:",
        "",
    ]
    for fname, desc in FILES:
        lines.append(f"* `{fname}` - {desc}")
    lines += [
        "",
        "## Physics annotation (`sample.json`)",
        "",
        "| field | meaning |",
        "|---|---|",
        "| `gso_object` | scanned source object (Google Scanned Objects) |",
        "| `motion` | `circular` / `damped` / `rotation` |",
        "| `motion_applied` | the motion actually driven, in SI units |",
        "| `actor_span_m` | object bounding box (x, y, z) in metres |",
        "| `actor_rest_z` | height that puts the object's lowest point on the floor |",
        "| `floor_z` | floor height under the object |",
        "| `camera_distance_m` | camera stand-off |",
        "| `actor_pct_of_frame_width` | how much of the frame the subject occupies |",
        "| `resolution`, `frames`, `fps` | video format |",
        "",
        "## Provenance",
        "",
        "* Actor geometry/texture: Google Scanned Objects, CC BY-SA 4.0.",
        "* Backdrop: Poly Haven HDRI (CC0) + Poly Haven PBR ground (CC0).",
        "* Rendered with Blender 3.4 / Cycles on CPU.",
        "* Trajectories are prescribed analytically (not solver-integrated);",
        "  see the accompanying plan document for why.",
        "",
        "Full lossless frames (rgba/depth/segmentation PNG) are available on request;",
        "they are ~95 MB per clip, which is why this package ships video only.",
    ]
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    # --- report ------------------------------------------------------------
    print(f"package : {out}")
    print(f"clips   : {len(index)}")
    print(f"total   : {human(total)}")
    print()
    for m in MOTION_ORDER + ["other"]:
        if m not in per_motion:
            continue
        sub = sum(r["bytes"] for r in index if r["motion"] == m)
        print(f"  {m:10s} {len(per_motion[m]):3d} clips   {human(sub):>10s}")
    print()
    biggest = sorted(index, key=lambda r: -r["bytes"])[:3]
    for r in biggest:
        print(f"  largest: {r['run']}  {human(r['bytes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
