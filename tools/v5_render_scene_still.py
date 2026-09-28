#!/usr/bin/env python3
"""Render one authored scene camera to a high-resolution CPU-only review still."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import bpy


DEFAULT_WORKSPACE = Path("/data/raw/huzijian/project1_database")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--camera")
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--disable-compositing", action="store_true")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    args = parser.parse_args(os.sys.argv[os.sys.argv.index("--") + 1 :])
    workspace = Path(args.workspace).resolve()

    output = Path(args.output)
    report_path = Path(args.report)
    for path in (output, report_path):
        if not str(path.resolve()).startswith(str(workspace) + os.sep):
            raise RuntimeError(f"output path escaped workspace: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    if args.camera:
        camera = bpy.data.objects.get(args.camera)
        if camera is None or camera.type != "CAMERA":
            raise RuntimeError(f"author camera not found: {args.camera}")
        scene.camera = camera
    if scene.camera is None:
        raise RuntimeError("scene has no authored active camera")

    original_resolution = [int(scene.render.resolution_x), int(scene.render.resolution_y)]
    aspect = original_resolution[0] / max(original_resolution[1], 1)
    scene.render.resolution_x = 1920
    scene.render.resolution_y = max(1, round(1920 / aspect))
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.filepath = str(output)
    scene.render.use_file_extension = True
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 8
    if args.disable_compositing:
        scene.render.use_compositing = False

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = int(args.samples)
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.02
    if hasattr(scene.cycles, "denoiser"):
        scene.cycles.denoiser = "OPENIMAGEDENOISE"

    # File Output compositor nodes can retain author-machine paths.  Redirect
    # them inside this task's output directory while leaving the main Composite
    # node, author lighting, world, camera, geometry and materials untouched.
    redirected_file_outputs = []
    if scene.use_nodes and scene.node_tree:
        for node in scene.node_tree.nodes:
            if node.bl_idname == "CompositorNodeOutputFile":
                redirected_file_outputs.append({"node": node.name, "old_base_path": node.base_path})
                node.base_path = str(output.parent / "compositor_outputs")

    source = Path(bpy.data.filepath).resolve()
    started = time.time()
    print(
        f"SCENE_RENDER_START tag={args.tag} camera={scene.camera.name} "
        f"resolution={scene.render.resolution_x}x{scene.render.resolution_y} samples={scene.cycles.samples}",
        flush=True,
    )
    bpy.ops.render.render(write_still=True)
    elapsed = time.time() - started
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"render output missing: {output}")

    report = {
        "tag": args.tag,
        "source": str(source),
        "source_sha256": file_sha256(source),
        "output": str(output.resolve().relative_to(workspace)),
        "output_sha256": file_sha256(output),
        "camera": {
            "name": scene.camera.name,
            "type": scene.camera.data.type,
            "lens_mm": float(scene.camera.data.lens),
            "location": [float(value) for value in scene.camera.matrix_world.translation],
        },
        "authored_light_count": sum(1 for obj in bpy.data.objects if obj.type == "LIGHT"),
        "world": scene.world.name if scene.world else None,
        "missing_images": [
            image.name
            for image in bpy.data.images
            if image.source == "FILE"
            and image.packed_file is None
            and not Path(bpy.path.abspath(image.filepath, library=image.library)).is_file()
        ],
        "render": {
            "engine": scene.render.engine,
            "device": "CPU",
            "threads": 8,
            "samples": int(scene.cycles.samples),
            "denoising": bool(scene.cycles.use_denoising),
            "resolution": [int(scene.render.resolution_x), int(scene.render.resolution_y)],
            "original_resolution": original_resolution,
            "frame": int(scene.frame_current),
            "elapsed_seconds": elapsed,
        },
        "content_policy": {
            "camera": "existing authored camera",
            "lighting": "existing authored lights and world only",
            "added_geometry": 0,
            "deleted_geometry": 0,
            "material_overrides": 0,
            "author_compositing_enabled": not args.disable_compositing,
            "redirected_compositor_file_outputs": redirected_file_outputs,
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"SCENE_RENDER_DONE tag={args.tag} seconds={elapsed:.1f} output={output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
