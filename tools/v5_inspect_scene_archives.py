#!/usr/bin/env python3
"""Inspect and safely extract candidate scene archives inside the workspace."""

from __future__ import annotations

import json
import os
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath


WORKSPACE = Path("/data/raw/huzijian/project1_database")
CANDIDATE_ROOT = WORKSPACE / "models" / "backgrounds" / "candidates"
REPORT_PATH = WORKSPACE / "tmp" / "v5_scene_archive_inventory.json"
ARCHIVES = {
    "the_shed": CANDIDATE_ROOT / "the_shed" / "source" / "the_shed.zip",
    "hidden_alley": CANDIDATE_ROOT / "hidden_alley" / "source" / "hidden_alley.zip",
    "pine_forest": CANDIDATE_ROOT / "pine_forest" / "source" / "pine_forest.zip",
}


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def inspect_extract(tag: str, archive: Path) -> dict:
    extract_root = CANDIDATE_ROOT / tag / "extracted"
    if not str(extract_root).startswith(str(WORKSPACE) + os.sep):
        raise RuntimeError("extraction path escaped workspace")
    with zipfile.ZipFile(archive) as handle:
        members = handle.infolist()
        unsafe = [member.filename for member in members if not safe_member(member.filename)]
        if unsafe:
            raise RuntimeError(f"unsafe archive members: {unsafe[:5]}")
        suffixes = Counter(Path(member.filename).suffix.lower() for member in members if not member.is_dir())
        blend_files = [member.filename for member in members if member.filename.lower().endswith(".blend")]
        text_files = [
            member.filename
            for member in members
            if Path(member.filename).name.lower().startswith(("readme", "license", "credits"))
        ]
        uncompressed = int(sum(member.file_size for member in members))
        extract_root.mkdir(parents=True, exist_ok=True)
        handle.extractall(extract_root)
    return {
        "archive": str(archive.relative_to(WORKSPACE)),
        "compressed_bytes": archive.stat().st_size,
        "uncompressed_bytes": uncompressed,
        "file_count": len(members),
        "suffix_counts": dict(sorted(suffixes.items())),
        "blend_files": blend_files,
        "text_files": text_files,
        "extract_root": str(extract_root.relative_to(WORKSPACE)),
    }


def main() -> None:
    report = {}
    for tag, archive in ARCHIVES.items():
        print(f"SCENE_EXTRACT {tag} {archive}", flush=True)
        report[tag] = inspect_extract(tag, archive)
        print(
            f"SCENE_EXTRACTED {tag} files={report[tag]['file_count']} "
            f"blend={len(report[tag]['blend_files'])}",
            flush=True,
        )
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SCENE_ARCHIVE_REPORT {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
