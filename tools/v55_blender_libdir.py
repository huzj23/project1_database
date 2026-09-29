"""Test whether the server's Blender can start with the PROJECT'S OWN library directory.

Stage-01 recorded that the server Blender 3.4.1 works once `tools/runtime/lib` is added to
`LD_LIBRARY_PATH`, because the system lacks `libxkbcommon.so.0`. An earlier check of mine searched
only the conda environment's lib directory and therefore concluded Blender was unusable, which
contradicts the stage-01 record. This script tests the documented route directly, and if it works,
the server can render and the render architecture changes.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
BLENDER = ROOT / "tools/runtime/blender-3.4.1-linux-x64/blender"
LIBDIR = ROOT / "tools/runtime/lib"

print("=" * 100)
print(f"blender : {BLENDER}  (exists={BLENDER.is_file()})")
print(f"lib dir : {LIBDIR}    (exists={LIBDIR.is_dir()})")
if LIBDIR.is_dir():
    libs = sorted(p.name for p in LIBDIR.iterdir())
    print(f"  {len(libs)} entries; xkb-related: {[n for n in libs if 'xkb' in n]}")
    print(f"  first 25: {libs[:25]}")

env = dict(os.environ)
env["LD_LIBRARY_PATH"] = f"{LIBDIR}:" + env.get("LD_LIBRARY_PATH", "")
print(f"\nLD_LIBRARY_PATH = {env['LD_LIBRARY_PATH'][:200]}")

for args in (["--background", "--version"],
             ["--background", "--factory-startup", "--python-expr", "print('BLENDER_PY_OK')"]):
    print(f"\n=== blender {' '.join(args)} ===")
    try:
        r = subprocess.run([str(BLENDER)] + args, capture_output=True, text=True, timeout=600,
                           env=env)
        print(f"  rc={r.returncode}")
        for line in ((r.stdout or "") + (r.stderr or "")).splitlines()[:12]:
            print(f"    {line}")
    except Exception as exc:
        print(f"  FAILED: {type(exc).__name__}: {exc}")

# If it starts, can it open the Italian Flat runtime copy? That is the actual question for rendering.
print("\n=== can it open the Italian Flat runtime copy? ===")
RUNTIME = ROOT / "outcomes/v55/scenes/italian_flat/runtime/italian_flat_runtime.blend"
print(f"  {RUNTIME}  exists={RUNTIME.is_file()}")
if RUNTIME.is_file() and subprocess.run([str(BLENDER), "--background", "--version"],
                                        capture_output=True, text=True, env=env,
                                        timeout=300).returncode == 0:
    expr = (
        "import bpy,sys;"
        f"bpy.ops.wm.open_mainfile(filepath={str(RUNTIME)!r});"
        "s=bpy.context.scene;"
        "print('OPENED objects=',len(s.objects),'cams=',len([o for o in s.objects if o.type=='CAMERA']),"
        "'res=',s.render.resolution_x,s.render.resolution_y);"
        "print('VERDICT_OPEN_OK')"
    )
    try:
        r = subprocess.run([str(BLENDER), "--background", "--factory-startup",
                            "--python-expr", expr],
                           capture_output=True, text=True, timeout=1800, env=env)
        print(f"  rc={r.returncode}")
        for line in ((r.stdout or "") + (r.stderr or "")).splitlines():
            if any(k in line for k in ("OPENED", "VERDICT", "Error", "error", "Segmentation")):
                print(f"    {line}")
    except Exception as exc:
        print(f"  FAILED: {type(exc).__name__}: {exc}")
