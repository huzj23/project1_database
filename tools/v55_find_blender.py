"""Locate Blender and ffmpeg on the server, and report the render capability honestly.

Blender 3.4.1 is stated to be on the server but is also stated to require glibc 2.26+ while the host
provides 2.17. That combination cannot start, so the render must be planned around it rather than
assumed. This script reports what is actually present and whether it runs, which decides how the
stage-05 video is produced.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")

print("=" * 100)
print("=== host ===")
print(f"  python {sys.version.split()[0]}")
print(f"  machine {platform.machine()}  platform {platform.platform()}")
libc = platform.libc_ver()
print(f"  libc {libc[0]} {libc[1]}")

print("\n=== ffmpeg ===")
ff = shutil.which("ffmpeg")
print(f"  which ffmpeg: {ff}")
if ff:
    r = subprocess.run([ff, "-version"], capture_output=True, text=True, timeout=60)
    print(f"  {r.stdout.splitlines()[0] if r.stdout else '(no output)'}")

print("\n=== blender candidates ===")
cands = [
    ROOT / "tools/blender-3.4.1-linux-x64/blender",
    ROOT / "tools/blender/blender",
    ROOT / "tools/runtime/blender-3.4.1-linux-x64/blender",
    Path("/usr/local/blender-3.4.1-linux-x64/blender"),
    Path("/opt/blender/blender"),
    Path("/usr/bin/blender"),
]
found = []
for c in cands:
    ex = c.is_file() and os.access(c, os.X_OK)
    print(f"  {str(c):70s} exists={c.is_file()} executable={ex}")
    if ex:
        found.append(c)
w = shutil.which("blender")
print(f"  which blender: {w}")
if w:
    found.append(Path(w))

print("\n=== does each candidate actually START? (this is the question that matters) ===")
for c in found:
    try:
        r = subprocess.run([str(c), "--background", "--version"], capture_output=True,
                           text=True, timeout=180)
        first = (r.stdout or r.stderr or "").splitlines()
        print(f"  {c}")
        print(f"    rc={r.returncode}  {first[0] if first else '(no output)'}")
        for line in first[1:4]:
            print(f"    {line}")
    except Exception as exc:
        print(f"  {c} -> FAILED TO RUN: {type(exc).__name__}: {exc}")

print("\n=== any blender-looking tree under the workspace ===")
for d in sorted(ROOT.glob("tools/*blender*")):
    print(f"  {d}  (dir={d.is_dir()})")
    if d.is_dir():
        for sub in sorted(d.iterdir())[:12]:
            print(f"      {sub.name}")

print("\n=== conclusion for rendering ===")
print("  The server can only be used for the solve if no Blender starts here. If none starts, the")
print("  render runs locally with Blender 4.2.23, which CAN open the runtime copy because the runtime")
print("  copy is written by that same local build. That is why the runtime .blend is produced")
print("  locally: the server has no working Blender to produce or consume one.")
