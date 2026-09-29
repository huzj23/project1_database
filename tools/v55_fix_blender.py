"""Try to make the server's Blender 3.4.1 actually start, by supplying its missing libraries.

The earlier belief was that Blender could not run here because the host glibc is 2.17 while Blender
needs 2.26+. The real error is narrower: `libxkbcommon.so.0` is not on the loader path. That is a
library, not the C runtime, so it may be satisfiable from the conda environment or from a bundled
copy -- and if it is, the server can render and the whole render architecture changes.

This script searches for each missing library, reports where it was found, and then tries to run
Blender with `LD_LIBRARY_PATH` set to those locations. It iterates because the loader reports one
missing library at a time.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
BLENDER = ROOT / "tools/runtime/blender-3.4.1-linux-x64/blender"
CONDA_LIB = ROOT / "tools/conda_env/lib"

print("=" * 100)
print(f"blender: {BLENDER}")
print(f"conda lib: {CONDA_LIB}  (exists={CONDA_LIB.is_dir()})")

# Where a shared library might live.
search_dirs = [CONDA_LIB]
for extra in (ROOT / "tools/conda_env/lib64", ROOT / "tools/runtime/blender-3.4.1-linux-x64/lib",
              Path("/usr/lib64"), Path("/usr/lib"), Path("/lib64"), Path("/usr/lib/x86_64-linux-gnu")):
    if extra.is_dir():
        search_dirs.append(extra)

site_pkgs = list((ROOT / "tools/conda_env/lib").glob("python3.*/site-packages"))
for sp in site_pkgs:
    for sub in sp.glob("*.libs"):
        search_dirs.append(sub)

print(f"\nsearch dirs ({len(search_dirs)}):")
for d in search_dirs:
    print(f"  {d}")

MISSING_RE = re.compile(r"error while loading shared libraries: ([^:]+): cannot open shared object")


def try_run(env_path: list[str]) -> tuple[int, str]:
    env = dict(os.environ)
    if env_path:
        env["LD_LIBRARY_PATH"] = ":".join(env_path)
    r = subprocess.run([str(BLENDER), "--background", "--version"], capture_output=True,
                       text=True, timeout=300, env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


found: dict[str, str] = {}
env_path: list[str] = [str(CONDA_LIB)]
for attempt in range(1, 25):
    rc, out = try_run(env_path)
    if rc == 0:
        print(f"\n=== attempt {attempt}: BLENDER RUNS (rc=0) ===")
        for line in out.splitlines()[:4]:
            print(f"  {line}")
        break
    m = MISSING_RE.search(out)
    if not m:
        print(f"\n=== attempt {attempt}: failed for a different reason (rc={rc}) ===")
        for line in out.splitlines()[:8]:
            print(f"  {line}")
        break
    lib = m.group(1)
    hit = None
    for d in search_dirs:
        cand = d / lib
        if cand.is_file():
            hit = cand
            break
    print(f"  attempt {attempt}: missing {lib} -> "
          f"{'found at ' + str(hit) if hit else 'NOT FOUND anywhere searched'}")
    if hit is None:
        print("\n  Cannot satisfy this library from the available trees; the loader list is:")
        for l in env_path:
            print(f"    {l}")
        break
    found[lib] = str(hit)
    if str(hit.parent) not in env_path:
        env_path.insert(0, str(hit.parent))

print("\n" + "=" * 100)
print("=== libraries located ===")
for k, v in found.items():
    print(f"  {k} -> {v}")
print(f"\nfinal LD_LIBRARY_PATH: {':'.join(env_path)}")

rc, out = try_run(env_path)
print(f"\nfinal run rc={rc}")
for line in out.splitlines()[:6]:
    print(f"  {line}")
print(f"\nVERDICT: server Blender {'USABLE' if rc == 0 else 'NOT USABLE'}")
