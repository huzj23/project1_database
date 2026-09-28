#!/usr/bin/env python3
"""Audit a Blender scene without modifying or saving the source file."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import bpy


DEFAULT_WORKSPACE = Path("/data/raw/huzijian/project1_database")


def vector(values) -> list[float]:
    return [float(value) for value in values]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    args = parser.parse_args(os.sys.argv[os.sys.argv.index("--") + 1 :])
    workspace = Path(args.workspace).resolve()
    report_path = Path(args.report)
    if not str(report_path.resolve()).startswith(str(workspace) + os.sep):
        raise RuntimeError("report path escaped workspace")

    scene = bpy.context.scene
    cameras = []
    for obj in sorted((item for item in bpy.data.objects if item.type == "CAMERA"), key=lambda item: item.name):
        cameras.append(
            {
                "name": obj.name,
                "location": vector(obj.matrix_world.translation),
                "rotation_euler": vector(obj.matrix_world.to_euler()),
                "type": obj.data.type,
                "lens_mm": float(obj.data.lens),
            }
        )
    lights = []
    for obj in sorted((item for item in bpy.data.objects if item.type == "LIGHT"), key=lambda item: item.name):
        lights.append(
            {
                "name": obj.name,
                "type": obj.data.type,
                "energy": float(obj.data.energy),
                "location": vector(obj.matrix_world.translation),
            }
        )
    images = []
    missing_images = []
    for image in sorted(bpy.data.images, key=lambda item: item.name):
        if image.source != "FILE":
            continue
        absolute = Path(bpy.path.abspath(image.filepath, library=image.library)).resolve()
        row = {
            "name": image.name,
            "path": str(absolute),
            "exists": absolute.is_file(),
            "packed": image.packed_file is not None,
            "size": [int(value) for value in image.size],
        }
        images.append(row)
        if not row["exists"] and not row["packed"]:
            missing_images.append(row)

    report = {
        "tag": args.tag,
        "source": str(Path(bpy.data.filepath).resolve()),
        "blender_runtime": bpy.app.version_string,
        "object_counts": {
            object_type: sum(1 for obj in bpy.data.objects if obj.type == object_type)
            for object_type in sorted({obj.type for obj in bpy.data.objects})
        },
        "scene_names": [item.name for item in bpy.data.scenes],
        "active_scene": scene.name,
        "active_camera": scene.camera.name if scene.camera else None,
        "cameras": cameras,
        "lights": lights,
        "world": scene.world.name if scene.world else None,
        "world_uses_nodes": bool(scene.world and scene.world.use_nodes),
        "render": {
            "engine": scene.render.engine,
            "resolution": [int(scene.render.resolution_x), int(scene.render.resolution_y)],
            "percentage": int(scene.render.resolution_percentage),
            "frame": int(scene.frame_current),
            "frame_start": int(scene.frame_start),
            "frame_end": int(scene.frame_end),
            "film_transparent": bool(scene.render.film_transparent),
        },
        "image_count": len(images),
        "missing_image_count": len(missing_images),
        "missing_images": missing_images,
        "libraries": [str(Path(library.filepath)) for library in bpy.data.libraries],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"SCENE_AUDIT tag={args.tag} camera={report['active_camera']} cameras={len(cameras)} "
        f"lights={len(lights)} meshes={report['object_counts'].get('MESH', 0)} "
        f"missing_images={len(missing_images)} engine={scene.render.engine}",
        flush=True,
    )


if __name__ == "__main__":
    main()
