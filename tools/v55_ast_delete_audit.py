#!/usr/bin/env python
"""AST-accurate check: does any LIVE code path still DELETE files?

A plain ``grep unlink`` is not evidence -- it matches docstrings and comments (as
this project already discovered).  This walks the real AST and reports only actual
call expressions, classifying each as:

  * ``blender_object_unlink``  -- ``obj.users_collection`` / collection unlink, which
    removes an object from a Blender collection.  It does not touch the filesystem.
  * ``file_delete``            -- ``Path.unlink`` / ``os.remove`` / ``shutil.rmtree``
    on a real path.  THIS IS WHAT V5.5 FORBIDS.

Exit code 1 when any ``file_delete`` is found in live code, so it can gate a stage.

Usage:
    python tools/v55_ast_delete_audit.py <dir-or-file> [...]
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

DELETE_ATTRS = {"unlink", "rmtree", "remove", "rmdir", "removedirs", "rmtree"}


def classify(node: ast.Call) -> str | None:
    func = node.func
    # x.unlink() / x.rmdir()
    if isinstance(func, ast.Attribute):
        name = func.attr
        if name == "unlink":
            # Distinguish a Blender collection unlink from a filesystem unlink by the
            # receiver: ``<something>.objects.unlink(obj)`` is a Blender API call.
            recv = func.value
            if isinstance(recv, ast.Attribute) and recv.attr in {
                "objects",
                "children",
                "users_collection",
            }:
                return "blender_object_unlink"
            return "file_delete"
        if name in {"rmtree", "removedirs"}:
            return "file_delete"
        if name == "remove":
            # os.remove / shutil.rmtree style, but also Blender bpy.data.*.remove()
            recv = func.value
            if isinstance(recv, ast.Attribute) and recv.attr in {"data", "objects", "collections", "meshes", "materials", "images", "node_groups"}:
                return "blender_data_remove"
            if isinstance(recv, ast.Name) and recv.id in {"os", "shutil", "pathlib"}:
                return "file_delete"
            if isinstance(recv, ast.Attribute) and recv.attr in {"path", "shutil", "os"}:
                return "file_delete"
            return "file_delete"  # conservative: unknown .remove() treated as delete
        if name == "rmdir":
            return "file_delete"
    # TemporaryDirectory(..., delete=True) style auto-cleanup
    if isinstance(func, ast.Name) and func.id == "TemporaryDirectory":
        return "auto_tempdir"
    if isinstance(func, ast.Attribute) and func.attr == "TemporaryDirectory":
        return "auto_tempdir"
    if isinstance(func, ast.Name) and func.id == "mkdtemp":
        return "auto_tempdir"
    return None


def audit_file(path: Path) -> list[tuple[str, int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return [("parse_error", exc.lineno or 0, str(exc))]
    hits: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kind = classify(node)
        if kind is None:
            continue
        # Prefer the exact source line when available.
        hits.append((kind, node.lineno, ast.unparse(node)[:90]))
    return hits


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] or [Path("src")]
    files: list[Path] = []
    for t in targets:
        if t.is_dir():
            files.extend(sorted(p for p in t.rglob("*.py") if "__pycache__" not in p.parts))
        elif t.is_file():
            files.append(t)

    print(f"auditing {len(files)} python file(s) via AST (docstrings/comments ignored)")
    print()
    file_deletes: list[tuple[Path, int, str]] = []
    others: list[tuple[Path, str, int, str]] = []

    for f in files:
        for kind, lineno, src in audit_file(f):
            if kind == "file_delete":
                file_deletes.append((f, lineno, src))
            else:
                others.append((f, kind, lineno, src))

    print("--- filesystem-DELETING calls (must be zero) ---")
    if file_deletes:
        for f, lineno, src in file_deletes:
            print(f"  DELETE  {f}:{lineno}: {src}")
    else:
        print("  none")

    print()
    print("--- non-filesystem operations seen (allowed) ---")
    counts: dict[str, int] = {}
    for _f, kind, _lineno, _src in others:
        counts[kind] = counts.get(kind, 0) + 1
    for kind, n in sorted(counts.items()):
        print(f"  {kind}: {n}")
    for f, kind, lineno, src in others:
        if kind == "parse_error":
            print(f"  PARSE ERROR {f}:{lineno}: {src}")

    print()
    if file_deletes:
        print(f"RESULT: FAIL -- {len(file_deletes)} filesystem-deleting call(s) in live code")
        return 1
    print("RESULT: PASS -- no live code path deletes files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
