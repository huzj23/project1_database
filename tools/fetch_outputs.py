"""Download PhyCo-Sim run outputs from the server to the local workspace.

Three payload tiers, because the full delivery is ~3.9 GB and the link runs at
roughly 0.5 MB/s:

``small``   videos + metadata.json + QA contact sheet   (~12 MB for 36 runs)
``frames``  everything (lossless PNG frames included)    (~110 MB per run)
``videos``  just the three mp4 previews

Per-file SFTP latency is ~0.35 s, and a full run is ~290 files, so the fetch is
parallelised across several SFTP channels -- latency, not bandwidth, is the
binding constraint for the many-small-files case.

Usage
-----
    python tools/fetch_outputs.py --what small
    python tools/fetch_outputs.py --what full --motion circular --limit 3
    python tools/fetch_outputs.py --what full --workers 8
"""

from __future__ import annotations

import argparse
import os
import posixpath
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ssh_ctl  # noqa: E402

REMOTE_ROOT = posixpath.join(ssh_ctl.WORKSPACE,
                             "outcomes/dataset/single_object")
LOCAL_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "outcomes", "dataset", "single_object")

SMALL_SUFFIX = (".mp4",)
SMALL_NAMES = ("metadata.json", "qa_contact_sheet.jpg")


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024.0:
            return f"{n:8.1f} {u}"
        n /= 1024.0
    return f"{n:8.1f} TB"


def want(name: str, what: str) -> bool:
    if what == "full":
        return True
    if name in SMALL_NAMES:
        return True
    if what in ("small", "videos") and name.lower().endswith(SMALL_SUFFIX):
        return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch run outputs.")
    ap.add_argument("--account", default=ssh_ctl.DEFAULT_ACCOUNT,
                    choices=sorted(ssh_ctl.HOSTS))
    ap.add_argument("--what", default="small",
                    choices=["small", "videos", "full"])
    ap.add_argument("--motion", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--run", default=None, help="fetch a single named run")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--local_root", default=None)
    ap.add_argument("--remote_root", default=REMOTE_ROOT,
                    help="server-side run dir (default: the phase1 dataset)")
    ap.add_argument("--overwrite", action="store_true",
                    help="re-fetch files that already exist locally")
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args(argv)
    args.remote_root = ssh_ctl.check_remote_path(args.remote_root)
    if args.local_root is None:
        args.local_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "outcomes", os.path.basename(args.remote_root))

    # --- enumerate ---------------------------------------------------------
    client = ssh_ctl.connect(args.account)
    sftp = client.open_sftp()
    runs = sorted(e.filename for e in sftp.listdir_attr(args.remote_root)
                  if e.st_mode & 0o040000)
    if args.run:
        runs = [r for r in runs if r == args.run]
    if args.motion:
        runs = [r for r in runs if r.startswith(args.motion)]
    if args.limit:
        runs = runs[: args.limit]

    plan: list[tuple[str, str, int]] = []       # (remote, local, size)
    missing = []
    skipped = 0
    for run in runs:
        rdir = ssh_ctl.check_remote_path(posixpath.join(args.remote_root, run))
        try:
            entries = sftp.listdir_attr(rdir)
        except IOError:
            missing.append(run)
            continue
        for e in entries:
            if e.st_mode & 0o040000:
                continue
            if not want(e.filename, args.what):
                continue
            local_path = os.path.join(args.local_root, run, e.filename)
            # Resumable: skip anything already on disk at the same size, so
            # topping up a partially-fetched batch does not re-send 2.7 GB.
            if not args.overwrite and os.path.isfile(local_path) \
                    and os.path.getsize(local_path) == e.st_size:
                skipped += 1
                continue
            plan.append((posixpath.join(rdir, e.filename), local_path, e.st_size))
    sftp.close()
    client.close()

    total = sum(s for _, _, s in plan)
    print(f"runs    : {len(runs)}")
    print(f"files   : {len(plan)} to fetch, {skipped} already local")
    print(f"total   : {human(total)}")
    print(f"mode    : {args.what}   workers={args.workers}")
    if missing:
        print(f"skipped : {len(missing)} unreadable runs")
    if args.dry_run or not plan:
        return 0

    # --- parallel fetch ----------------------------------------------------
    lock = threading.Lock()
    done_files = 0
    done_bytes = 0
    failed = 0

    def worker(chunk):
        nonlocal done_files, done_bytes, failed
        cl = ssh_ctl.connect(args.account)
        sf = cl.open_sftp()
        try:
            for remote, local, size in chunk:
                os.makedirs(os.path.dirname(local), exist_ok=True)
                try:
                    sf.get(remote, local)
                    with lock:
                        done_files += 1
                        done_bytes += size
                except Exception as e:
                    with lock:
                        failed += 1
                    print(f"  ! {os.path.basename(remote)}: {type(e).__name__}")
        finally:
            sf.close()
            cl.close()

    chunks = [plan[i:: args.workers] for i in range(args.workers)]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(worker, c) for c in chunks if c]
        last = 0.0
        for f in as_completed(futs):
            f.result()
            now = time.time()
            if now - last > 5:
                last = now
                el = now - t0
                rate = done_bytes / el if el else 0
                pct = 100.0 * done_files / max(len(plan), 1)
                eta = (total - done_bytes) / rate if rate else 0
                print(f"  {done_files:5d}/{len(plan)} files  "
                      f"{human(done_bytes)}  {pct:5.1f}%  "
                      f"{rate/1024:6.0f} KB/s  ETA {eta/60:5.1f} min", flush=True)

    el = time.time() - t0
    print()
    print(f"done    : {done_files}/{len(plan)} files, {human(done_bytes)} "
          f"in {el/60:.1f} min  ({done_bytes/1024/max(el,1):.0f} KB/s)")
    if failed:
        print(f"failed  : {failed}")
    print(f"local   : {args.local_root}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ssh_ctl.SafetyError as e:
        print(f"SAFETY REFUSAL: {e}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
