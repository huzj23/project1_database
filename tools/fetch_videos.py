"""Download ONLY the preview videos (*.mp4) of completed runs to a local tree.

Frames (rgba/segmentation/depth PNG-JPG), metadata.json and QA sheets stay on the
server; this pulls just the encoded videos so they can be previewed locally.

Usage
-----
    python tools/fetch_videos.py                 # all completed runs
    python tools/fetch_videos.py --motion circular
    python tools/fetch_videos.py --limit 5
    python tools/fetch_videos.py --dry_run
    python tools/fetch_videos.py --flat          # no per-run subdirectory

Remote paths are validated against the permitted workspace before any transfer.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ssh_ctl  # noqa: E402

REMOTE_ROOT = posixpath.join(ssh_ctl.WORKSPACE,
                             "outcomes/dataset/single_object")
LOCAL_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "outcomes", "dataset", "single_object")

VIDEO_SUFFIXES = (".mp4",)


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024.0:
            return f"{n:6.1f} {unit}"
        n /= 1024.0
    return f"{n:6.1f} TB"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch preview videos only.")
    ap.add_argument("--account", default=ssh_ctl.DEFAULT_ACCOUNT,
                    choices=sorted(ssh_ctl.HOSTS))
    ap.add_argument("--motion", default=None,
                    help="only runs whose name starts with this (circular/damped/rotation)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--local_root", default=LOCAL_ROOT)
    ap.add_argument("--flat", action="store_true",
                    help="write straight into local_root instead of per-run folders")
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args(argv)

    client = ssh_ctl.connect(args.account)
    try:
        sftp = client.open_sftp()

        run_dirs = sorted(
            e.filename for e in sftp.listdir_attr(REMOTE_ROOT)
            if e.st_mode & 0o040000)          # directories only
        if args.motion:
            run_dirs = [d for d in run_dirs if d.startswith(args.motion)]
        if args.limit:
            run_dirs = run_dirs[:args.limit]

        print(f"remote : {REMOTE_ROOT}")
        print(f"local  : {args.local_root}")
        print(f"runs   : {len(run_dirs)}")

        total_bytes = 0
        total_files = 0
        skipped = []

        for i, run in enumerate(run_dirs, 1):
            rdir = ssh_ctl.check_remote_path(posixpath.join(REMOTE_ROOT, run))
            try:
                entries = sftp.listdir_attr(rdir)
            except IOError:
                skipped.append((run, "unreadable"))
                continue

            videos = [(e.filename, e.st_size) for e in entries
                      if e.filename.lower().endswith(VIDEO_SUFFIXES)]
            # a run counts as complete only if metadata.json is present
            complete = any(e.filename == "metadata.json" for e in entries)
            if not videos:
                skipped.append((run, "no videos"))
                continue

            size = sum(s for _, s in videos)
            flag = "" if complete else "  [INCOMPLETE]"
            print(f"[{i:2d}/{len(run_dirs)}] {run}{flag}")
            for name, sz in sorted(videos):
                print(f"        {name:24s} {human(sz)}")
            total_bytes += size
            total_files += len(videos)

            if args.dry_run:
                continue

            if args.flat:
                ldir = args.local_root
            else:
                ldir = os.path.join(args.local_root, run)
            os.makedirs(ldir, exist_ok=True)
            for name, _ in videos:
                sftp.get(posixpath.join(rdir, name), os.path.join(ldir, name))

        print()
        print(f"videos : {total_files} files, {human(total_bytes)}"
              + ("  (dry run, nothing transferred)" if args.dry_run else " transferred"))
        if skipped:
            print(f"skipped: {len(skipped)}")
            for name, why in skipped[:10]:
                print(f"  - {name}: {why}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ssh_ctl.SafetyError as e:
        print(f"SAFETY REFUSAL: {e}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
