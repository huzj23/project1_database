"""V5.5 stage 03: decode .blend headers exactly, and classify readability.

A .blend header is:
    bytes 0..6   "BLENDER"
    byte  7      pointer size: '_' = 4-byte, '-' = 8-byte
    byte  8      endianness:   'v' = little, 'V' = big
    bytes 9..11  three ASCII version digits, e.g. "293" = 2.93, "400" = 4.00

Some .blend files are gzip-wrapped (magic 1f 8b), in which case the real header is
inside the compressed stream.

The point of this script is to decide, WITHOUT guessing, whether the server's only
runnable Blender (3.4.1) can read each scene.  Blender refuses newer-format files, and
3.4.1's failure mode here is a hard SEGFAULT rather than a clean error.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
OUT = ROOT / "outcomes" / "v55" / "bootstrap" / "20260928T194500"

SCENES = [
    ("italian_flat", ROOT / "models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend"),
    ("hidden_alley", ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend"),
    ("the_shed", ROOT / "models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend"),
]

# Blender 3.4.1 is the newest build that starts on this host (glibc 2.17).
SERVER_BLENDER = (3, 4, 1)


def head_bytes(path: Path, n: int = 16) -> bytes:
    with path.open("rb") as handle:
        return handle.read(n)


def decode(path: Path) -> dict:
    raw = head_bytes(path, 16)
    info: dict = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "raw_head_hex": raw.hex(),
    }

    payload = raw
    if raw[:2] == b"\x1f\x8b":
        info["container"] = "gzip"
        with gzip.open(path, "rb") as handle:
            payload = handle.read(16)
        info["inner_head_hex"] = payload.hex()
    else:
        info["container"] = "plain"

    if payload[:7] != b"BLENDER":
        info["error"] = f"unrecognised magic: {payload[:7]!r}"
        return info

    ptr = payload[7:8].decode("latin-1")
    endian = payload[8:9].decode("latin-1")
    digits = payload[9:12].decode("latin-1")

    info["pointer_size"] = {"_": 4, "-": 8}.get(ptr, ptr)
    info["endianness"] = {"v": "little", "V": "big"}.get(endian, endian)
    info["version_digits"] = digits

    # Blender writes 3 digits: major is the first digit, minor is the next two.
    # e.g. "293" -> 2.93 ; "304" -> 3.4 ; "400" -> 4.0
    if digits.isdigit() and len(digits) == 3:
        major = int(digits[0])
        minor = int(digits[1:3])
        info["writer_version"] = f"{major}.{minor}"
        info["writer_version_tuple"] = [major, minor, 0]
    else:
        info["writer_version"] = None

    if info.get("writer_version_tuple"):
        info["readable_by_server_blender_3_4_1"] = (
            tuple(info["writer_version_tuple"]) <= SERVER_BLENDER
        )
    return info


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, path in SCENES:
        print(f"\n===== {name} =====")
        if not path.is_file():
            print(f"  ABSENT: {path}")
            results[name] = {"error": "absent", "path": str(path)}
            continue
        info = decode(path)
        results[name] = info
        for key in (
            "container", "raw_head_hex", "inner_head_hex", "pointer_size",
            "endianness", "version_digits", "writer_version",
            "readable_by_server_blender_3_4_1", "sha256", "bytes",
        ):
            if key in info:
                print(f"  {key:34s}: {info[key]}")
        if "error" in info:
            print(f"  error                             : {info['error']}")

    report = OUT / "03_blend_header_decode.json"
    report.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwritten: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
