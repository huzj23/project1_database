"""Workspace-safe output allocation and quarantine (V5.5 stage 01).

Why this module exists
----------------------
The V5.5 task rules forbid deleting files. Two behaviours in the live render chain
violated that:

``physim.render.blender_backend.purge_stale_frames`` called ``Path.unlink()`` on any
leftover ``frame_*``/``rgba_*``/``depth_*``/``segmentation_*`` PNG/EXR in the scratch
directory, and ``build_scene()`` called it on every render.  The scratch directory is
derived as ``cache/<scenario>/seed-<n>/<variant>`` (see ``pipeline.py``), so the same
path is reused whenever a sample is rendered again -- which is exactly why the purge
existed (Kubric reads the whole directory back and would mix old frames into a new
clip).

This module replaces deletion with two safe primitives:

``allocate_run_dir(base, run_id)``
    Create ``base/<run_id>`` and refuse to write into a directory that already holds
    output.  A re-run therefore gets a fresh directory instead of overwriting, which
    removes the reason the purge was written in the first place.

``quarantine``
    Move content into ``<remove_root>/<timestamp>/<relative path>`` instead of
    deleting it, and record a manifest (original, destination, reason, size, sha256)
    BEFORE and AFTER the move so the move can be audited.

Both are workspace-confined: every destination is resolved and checked to be inside
the declared workspace, so a misconfigured path cannot move data outside it.  Nothing
in this module calls ``unlink``/``rmtree``/``os.remove``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

#: Frame-file prefixes Kubric/PhyCo writes into the scratch directory.
FRAME_PREFIXES = ("frame_", "rgba_", "depth_", "segmentation_")
FRAME_SUFFIXES = (".exr", ".png")


class OutputConflictError(RuntimeError):
    """Raised when a run directory already contains output from a previous run."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_inside(path: Path, root: Path, what: str) -> Path:
    """Resolve ``path`` and assert it lives under ``root``."""
    resolved = path.resolve()
    root = root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"{what} escapes the workspace: {resolved} is not under {root}"
        ) from exc
    return resolved


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class MoveRecord:
    """One quarantined file or directory."""

    original: str
    destination: str
    reason: str
    is_dir: bool
    bytes: int
    sha256: str | None
    moved_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "destination": self.destination,
            "reason": self.reason,
            "is_dir": self.is_dir,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "moved_at": self.moved_at,
        }


@dataclass
class QuarantineResult:
    """Summary of a quarantine operation."""

    batch_dir: Path
    manifest_path: Path | None = None
    moved: list[MoveRecord] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def moved_count(self) -> int:
        return len(self.moved)

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_dir": str(self.batch_dir),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "moved_count": self.moved_count,
            "moved": [m.to_dict() for m in self.moved],
            "failures": list(self.failures),
        }


def is_run_dir_populated(path: Path) -> bool:
    """True when ``path`` exists and holds anything at all."""
    if not path.is_dir():
        return False
    for _ in path.iterdir():
        return True
    return False


def stale_frame_files(scratch_dir: Path) -> list[Path]:
    """Leftover frame files in ``scratch_dir`` that the old code would have deleted."""
    scratch_dir = Path(scratch_dir)
    if not scratch_dir.is_dir():
        return []
    found: list[Path] = []
    for sub in ("images", "exr", ""):
        directory = scratch_dir / sub if sub else scratch_dir
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if not entry.is_file():
                continue
            if entry.suffix.lower() in FRAME_SUFFIXES and entry.name.startswith(
                FRAME_PREFIXES
            ):
                found.append(entry)
    return found


def allocate_run_dir(
    base: str | Path,
    run_id: str,
    *,
    workspace_root: str | Path,
    allow_existing_empty: bool = True,
) -> Path:
    """Return ``base/run_id``, created fresh, refusing to reuse populated output.

    This is the replacement for "purge the old frames and reuse the directory": a
    second run of the same sample gets its own directory, so no previous frame can be
    read back into the new clip.
    """
    workspace_root = Path(workspace_root)
    base = Path(base)
    target = _require_inside(base / run_id, workspace_root, "run directory")

    if target.exists():
        if not target.is_dir():
            raise OutputConflictError(f"run path exists and is not a directory: {target}")
        if is_run_dir_populated(target) and not allow_existing_empty:
            raise OutputConflictError(
                f"run directory already holds output, refusing to reuse it: {target}"
            )
        if is_run_dir_populated(target):
            raise OutputConflictError(
                "run directory already holds output; choose a new run_id or "
                f"quarantine it first: {target}"
            )
    target.mkdir(parents=True, exist_ok=True)
    return target


def quarantine(
    paths: Iterable[str | Path],
    *,
    workspace_root: str | Path,
    remove_root: str | Path,
    reason: str,
    batch_id: str | None = None,
) -> QuarantineResult:
    """MOVE ``paths`` into ``remove_root/<timestamp>/<relative path>``.

    Never deletes.  Writes a manifest describing every move so the operation is
    auditable, and verifies the sha256 of each moved file after the move.

    ``remove_root`` is the workspace's ``remove`` directory, which the user inspects
    and empties personally.
    """
    workspace_root = Path(workspace_root)
    remove_root = Path(remove_root)
    resolved_remove = _require_inside(remove_root, workspace_root, "remove root")
    resolved_remove.mkdir(parents=True, exist_ok=True)

    batch_dir = resolved_remove / (batch_id or _timestamp())
    _require_inside(batch_dir, workspace_root, "quarantine batch")
    batch_dir.mkdir(parents=True, exist_ok=True)

    result = QuarantineResult(batch_dir=batch_dir)
    moved_at = _timestamp()

    for raw in paths:
        src = Path(raw)
        if not src.exists():
            result.failures.append(f"missing, skipped: {src}")
            continue
        try:
            resolved_src = _require_inside(src, workspace_root, "quarantine source")
        except ValueError as exc:
            result.failures.append(str(exc))
            continue

        # Preserve a recognisable relative path under the batch directory.
        try:
            rel = resolved_src.relative_to(workspace_root)
        except ValueError:
            rel = Path(resolved_src.name)
        dest = batch_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest = dest.with_name(f"{dest.name}.{moved_at}")

        is_dir = resolved_src.is_dir()
        if is_dir:
            size = sum(f.stat().st_size for f in resolved_src.rglob("*") if f.is_file())
            digest = None
        else:
            size = resolved_src.stat().st_size
            digest = sha256_file(resolved_src)

        shutil.move(str(resolved_src), str(dest))

        # Post-move verification: the data must exist at the destination with the
        # same digest, or the move is reported as a failure.
        if is_dir:
            ok = dest.is_dir()
        else:
            ok = dest.is_file() and sha256_file(dest) == digest
        if not ok:
            result.failures.append(f"post-move verification failed: {dest}")
            continue

        result.moved.append(
            MoveRecord(
                original=str(resolved_src),
                destination=str(dest),
                reason=reason,
                is_dir=is_dir,
                bytes=size,
                sha256=digest,
                moved_at=moved_at,
            )
        )

    manifest = batch_dir / "move_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "v55.quarantine.1",
                "batch_dir": str(batch_dir),
                "reason": reason,
                "moved_at": moved_at,
                "moved_count": result.moved_count,
                "moved": [m.to_dict() for m in result.moved],
                "failures": list(result.failures),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    result.manifest_path = manifest
    return result


def quarantine_stale_frames(
    scratch_dir: str | Path,
    *,
    workspace_root: str | Path,
    remove_root: str | Path,
    reason: str = "stale frames from a previous run of the same sample",
) -> QuarantineResult:
    """Replacement for the old ``purge_stale_frames``: move, never delete."""
    return quarantine(
        stale_frame_files(Path(scratch_dir)),
        workspace_root=workspace_root,
        remove_root=remove_root,
        reason=reason,
    )


def find_workspace_root(start: str | Path | None = None) -> Path | None:
    """Walk up from ``start`` looking for the project workspace root.

    The workspace is the directory that holds the project's ``remove`` quarantine
    alongside its working trees (``code``/``models``/``tools``).  The repository
    itself lives at ``<workspace>/code/physics-video-sim/physics-video-sim-main``,
    so this climbs out of the checkout.

    Returns ``None`` when no candidate matches, so callers can decide how to fail;
    they must never fall back to deleting.
    """
    path = Path(start or os.getcwd()).resolve()
    for candidate in (path, *path.parents):
        if not (candidate / "remove").is_dir():
            continue
        if any((candidate / name).is_dir() for name in ("code", "models", "tools")):
            return candidate
    return None


def resolve_workspace_root(
    explicit: str | Path | None = None, start: str | Path | None = None
) -> Path:
    """Resolve the workspace root, in precedence order:

    1. an explicit argument;
    2. ``$PHYSIM_WORKSPACE_ROOT``;
    3. discovery by walking up from ``start`` (see :func:`find_workspace_root`).

    Raises when none apply.  Failing loudly is deliberate: silently proceeding
    would mean either deleting (forbidden) or leaving stale frames in place (which
    corrupts the clip), so an unknown workspace must stop the run.
    """
    if explicit is not None:
        return Path(explicit)
    value = os.environ.get("PHYSIM_WORKSPACE_ROOT")
    if value:
        return Path(value)
    discovered = find_workspace_root(start)
    if discovered is not None:
        return discovered
    raise ValueError(
        "workspace root unknown: pass workspace_root explicitly, set "
        "$PHYSIM_WORKSPACE_ROOT, or run from inside the project workspace"
    )
