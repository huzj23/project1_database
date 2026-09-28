#!/usr/bin/env python3
"""Inventory render candidates inside the project's server workspace only.

The report is intentionally read-only and records enough geometry/texture facts
to select a complete batch of previously untested rigid objects and scenes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


WORKSPACE = Path("/data/raw/huzijian/project1_database")
GSO_ROOT = WORKSPACE / "models" / "gso"
BACKGROUND_ROOT = WORKSPACE / "models" / "backgrounds"
OUTCOME_ROOT = WORKSPACE / "outcomes"
REPORT_PATH = WORKSPACE / "tmp" / "v5_candidate_inventory.json"


def image_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return tuple(int(v) for v in image.size)
    except Exception:
        return None


def mesh_stats(path: Path) -> dict:
    result = {"vertices": None, "faces": None, "watertight": None}
    try:
        import trimesh

        loaded = trimesh.load(path, force="scene", process=False)
        meshes = list(loaded.geometry.values()) if hasattr(loaded, "geometry") else [loaded]
        result["vertices"] = int(sum(len(mesh.vertices) for mesh in meshes))
        result["faces"] = int(sum(len(mesh.faces) for mesh in meshes))
        result["watertight"] = bool(meshes and all(mesh.is_watertight for mesh in meshes))
    except Exception:
        pass
    return result


def inventory_gso() -> list[dict]:
    rows: list[dict] = []
    if not GSO_ROOT.is_dir():
        return rows
    for directory in sorted(path for path in GSO_ROOT.iterdir() if path.is_dir()):
        data_path = directory / "data.json"
        if not data_path.is_file():
            continue
        try:
            data = json.loads(data_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        kwargs = data.get("kwargs", {})
        bounds = kwargs.get("bounds")
        dimensions = None
        if isinstance(bounds, list) and len(bounds) == 2:
            dimensions = [float(bounds[1][axis] - bounds[0][axis]) for axis in range(3)]
        visual_candidates = [
            directory / "visual_geometry.obj",
            directory / "meshes" / "model.obj",
            directory / "model.obj",
        ]
        visual_path = next((path for path in visual_candidates if path.is_file()), None)
        textures: list[dict] = []
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            size = image_size(path)
            textures.append(
                {
                    "path": str(path.relative_to(WORKSPACE)),
                    "width": size[0] if size else None,
                    "height": size[1] if size else None,
                    "bytes": path.stat().st_size,
                }
            )
        rows.append(
            {
                "directory": directory.name,
                "id": data.get("id"),
                "category": data.get("metadata", {}).get("category"),
                "dimensions_m": dimensions,
                "mass_raw": kwargs.get("mass"),
                "visual": str(visual_path.relative_to(WORKSPACE)) if visual_path else None,
                "mesh": mesh_stats(visual_path) if visual_path else {},
                "textures": textures,
                "total_bytes": int(sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())),
            }
        )
    return rows


def inventory_backgrounds() -> list[dict]:
    rows: list[dict] = []
    if not BACKGROUND_ROOT.is_dir():
        return rows
    wanted = {".blend", ".glb", ".gltf", ".obj", ".fbx", ".usd", ".usdc"}
    for path in sorted(BACKGROUND_ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in wanted:
            continue
        rows.append(
            {
                "path": str(path.relative_to(WORKSPACE)),
                "bytes": path.stat().st_size,
                "suffix": path.suffix.lower(),
                "mesh": mesh_stats(path) if path.suffix.lower() in {".glb", ".gltf", ".obj"} else {},
            }
        )
    return rows


def inventory_outputs() -> list[dict]:
    rows: list[dict] = []
    if not OUTCOME_ROOT.is_dir():
        return rows
    for path in sorted(OUTCOME_ROOT.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".mp4", ".webm"}:
            rows.append(
                {
                    "path": str(path.relative_to(WORKSPACE)),
                    "bytes": path.stat().st_size,
                }
            )
    return rows


def main() -> None:
    if not str(REPORT_PATH).startswith(str(WORKSPACE) + os.sep):
        raise RuntimeError("report path escaped workspace")
    report = {
        "workspace": str(WORKSPACE),
        "gso": inventory_gso(),
        "backgrounds": inventory_backgrounds(),
        "existing_outputs": inventory_outputs(),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: len(value) if isinstance(value, list) else value for key, value in report.items()}))
    print(str(REPORT_PATH))


if __name__ == "__main__":
    main()
