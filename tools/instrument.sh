#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Instrument the render + write path to answer two questions at once:
#   (1) is the camera that gets recorded in metadata the one Blender renders with?
#   (2) where do 32 rgb frames come from when the trajectory only has 16 states?
#
# Prints go to stderr with a DIAG tag so they cannot be confused with normal logs.
# This modifies project-side code only (src/physim/...), never third_party/.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$PY" - "$REPO" <<'PY'
import sys, pathlib, re
repo = pathlib.Path(sys.argv[1])

# ---- 1. camera + frame count at render time --------------------------------
p = repo / "src/physim/render/blender_backend.py"
t = p.read_text()
if "DIAG render" not in t:
    t = t.replace(
        """        layers = built.renderer.render(
            frames=[state.frame for state in simulation.trajectory],
            return_layers=("rgba", "depth", "segmentation"),
        )""",
        """        import sys as _sys
        _frames = [state.frame for state in simulation.trajectory]
        try:
            import bpy as _bpy
            _cam = _bpy.context.scene.camera
            _mw = _cam.matrix_world.translation if _cam else None
            print(f"DIAG render traj_states={len(simulation.trajectory)} "
                  f"render_frames={len(_frames)} first={_frames[0]} last={_frames[-1]}",
                  file=_sys.stderr, flush=True)
            print(f"DIAG blender camera={None if _mw is None else (round(_mw.x,3), round(_mw.y,3), round(_mw.z,3))} "
                  f"frame_start={_bpy.context.scene.frame_start} "
                  f"frame_end={_bpy.context.scene.frame_end} "
                  f"res={tuple(_bpy.context.scene.render.resolution_x for _ in [0])}"
                  f"x{_bpy.context.scene.render.resolution_y}",
                  file=_sys.stderr, flush=True)
        except Exception as _e:
            print(f"DIAG camera probe failed: {_e}", file=_sys.stderr, flush=True)
        layers = built.renderer.render(
            frames=_frames,
            return_layers=("rgba", "depth", "segmentation"),
        )
        try:
            print(f"DIAG rendered rgba={layers['rgba'].shape} depth={layers['depth'].shape}",
                  file=_sys.stderr, flush=True)
        except Exception:
            pass""")
    p.write_text(t)
    print("  instrumented blender_backend.render")

if "DIAG build_scene" not in t:
    t = p.read_text()
    t = t.replace(
        """            "camera_position": [float(v) for v in camera_object.location],""",
        """            "camera_position": [float(v) for v in camera_object.location],""")
    t = t.replace(
        """        scene.camera = camera""",
        """        scene.camera = camera
        import sys as _sys
        print(f"DIAG build_scene camera_spec={tuple(round(v,3) for v in camera_spec.position)} "
              f"look={tuple(round(v,3) for v in camera_spec.look_at)} "
              f"focal={camera_spec.focal_length_mm}", file=_sys.stderr, flush=True)""", 1)
    p.write_text(t)
    print("  instrumented blender_backend.build_scene")

# ---- 2. what the writer receives and writes --------------------------------
q = repo / "src/physim/io/__init__.py"
s = q.read_text()
if "DIAG writer" not in s:
    s = s.replace("    def write(", "    def write(", 1)
    # add a probe at the top of write()
    m = re.search(r"(    def write\(self[^)]*\)[^:]*:\n)", s)
    if m:
        s = s[:m.end()] + (
            '        import sys as _sys\n'
            '        try:\n'
            '            print(f"DIAG writer rgb={getattr(self, \'rgb\', None) is not None} "\n'
            '                  f"depth={getattr(self, \'depth\', None) is not None} "\n'
            '                  f"seg={getattr(self, \'segmentation\', None) is not None} "\n'
            '                  f"frames={len(self.rgb) if getattr(self, \'rgb\', None) is not None else -1}",\n'
            '                  file=_sys.stderr, flush=True)\n'
            '        except Exception as _e:\n'
            '            print(f"DIAG writer probe failed: {_e}", file=_sys.stderr, flush=True)\n'
        ) + s[m.end():]
        q.write_text(s)
        print("  instrumented io.write")
    else:
        print("  !! could not find write() signature")
PY

echo
echo "=== clean run with diagnostics ==="
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
cd "$REPO" || exit 1
rm -rf "$REPO/datasets/free_fall"
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml --seed 1000 --variant x0.5 > "$WS/log/diag.log" 2>&1
echo "  exit code: $?"
echo
echo "=== DIAG lines ==="
grep -E '^DIAG' "$WS/log/diag.log" | sed 's/^/  /'
echo
echo "=== frames actually on disk ==="
D="$REPO/datasets/free_fall/seed-001000/x0.5"
for sub in rgb depth segmentation; do
  printf '  %-14s %s\n' "$sub" "$(ls "$D/$sub" 2>/dev/null | wc -l)"
done
