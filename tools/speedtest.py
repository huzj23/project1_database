"""Measure SFTP throughput from the server, and report what will fit in a budget.

Runs a timed transfer of a real output file so the estimate reflects the actual
link rather than a guess.
"""

from __future__ import annotations

import os
import posixpath
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ssh_ctl  # noqa: E402

RUN = "circular_objectball_radius1.2_period2.0"
REMOTE = posixpath.join(ssh_ctl.WORKSPACE,
                        "outcomes/dataset/single_object", RUN)


def main() -> int:
    client = ssh_ctl.connect()
    try:
        sftp = client.open_sftp()
        # a ~750 KB lossless frame plus a ~200 KB video: two realistic payloads
        for name in ("rgba_00048.png", "rgb.mp4", "metadata.json"):
            rp = posixpath.join(REMOTE, name)
            lp = os.path.join(os.environ.get("TEMP", "."), f"spd_{name}")
            try:
                size = sftp.stat(rp).st_size
            except IOError:
                print(f"  {name}: missing")
                continue
            t0 = time.time()
            sftp.get(rp, lp)
            dt = max(time.time() - t0, 1e-6)
            kbs = size / 1024 / dt
            print(f"  {name:18s} {size/1024:8.1f} KB in {dt:5.2f}s -> {kbs:7.1f} KB/s")
            os.remove(lp)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
