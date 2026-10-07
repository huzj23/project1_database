"""V6.5 -- launch a group of server jobs over one SSH connection, so the plan's per-step work does not cost a
separate connection each time.

Each job is written as a small launcher script under the project tmp tree and started in its own tmux session on the
project control socket. Every session name is unique, every output directory is distinct, and nothing overwrites an
existing artifact -- the same rules the rest of this project runs under.

Usage:
    python tools/v65/launch_group.py --spec <spec.json>

The spec is a list of {name, script, also, args, interpreter} objects. `also` lists shared modules to upload
alongside (byte-identical uploads are skipped by the underlying tool).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RUNNER = os.path.join(ROOT, "tools", "v64", "remote_run.py")
PY = sys.executable


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--account", default="chenliang")
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as handle:
        spec = json.load(handle)

    failed = []
    for job in spec["jobs"]:
        cmd = [PY, "-u", RUNNER, "run", "--account", args.account, "--name", job["name"],
               "--script", job["script"], "--interpreter", job.get("interpreter", "python")]
        for extra in job.get("also", []):
            cmd += ["--also", extra]
        if job.get("args"):
            cmd += ["--args", job["args"]]
        print(f"==> launching {job['name']}", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        out = (proc.stdout or "") + (proc.stderr or "")
        if "started session" in out:
            print(f"    OK  {job['name']}", flush=True)
        else:
            failed.append(job["name"])
            print(f"    FAILED {job['name']}\n{out.strip()[-600:]}", flush=True)

    if failed:
        print(f"\n{len(failed)} job(s) failed to launch: {failed}", flush=True)
        return 1
    print(f"\nall {len(spec['jobs'])} job(s) launched", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
