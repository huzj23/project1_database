"""V5.5 stage 01 verification: prove the no-delete behaviour.

01_operations.md section 5 requires:

    "放一个本次生成的哨兵帧文件，执行新目录分配/清理入口后旧文件必须仍在原位置或
     remove 且哈希一致；第二次运行不复用第一次帧。测试本身也不能通过框架 teardown
     删除临时目录，应使用持久化工作区 fixture。"

This script does exactly that, using only the project's own workspace:

1. write two sentinel "frames" into a scratch dir (with the names the old purge
   targeted) plus one non-frame file that the old purge ignored;
2. call the NEW purge entry point and prove every sentinel was MOVED to
   ``remove/`` with an unchanged sha256 -- none deleted, none altered;
3. prove the non-frame file was left alone;
4. prove ``allocate_run_dir`` refuses to reuse a populated run directory (so a
   second run cannot read the first run's frames);
5. prove the move manifest records original/destination/size/hash.

No TemporaryDirectory is used and nothing is cleaned up by the test, so the
evidence stays on disk for inspection.

Run it from anywhere inside the project workspace:

    python tools/v55_test_no_delete.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / "code" / "physics-video-sim" / "physics-video-sim-main"
sys.path.insert(0, str(REPO / "src"))

from physim.render.blender_backend import purge_stale_frames  # noqa: E402
from physim.safe_output import (  # noqa: E402
    OutputConflictError,
    allocate_run_dir,
    sha256_file,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def main() -> int:
    run_id = "no_delete_proof"
    base = ROOT / "tmp" / "v55_no_delete_test"
    scratch = base / "scratch"
    # Each invocation gets its OWN remove subtree so the assertions below can look
    # for exactly one copy.  Batches from earlier invocations are left in place as
    # evidence (nothing is ever deleted).
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    remove_dir = ROOT / "remove" / "v55_no_delete_test" / stamp

    # Fresh scratch, but never delete: if a previous test run left files, move the
    # whole scratch aside so this test starts clean without unlinking anything.
    # NOTE: no TemporaryDirectory anywhere -- the evidence must survive the test.
    from physim.safe_output import quarantine

    for stale, batch in (
        (scratch, "v55_no_delete_test_previous_scratch"),
        (base / "runs", "v55_no_delete_test_previous_runs"),
    ):
        if stale.exists() and any(stale.rglob("*")):
            quarantine(
                [stale],
                workspace_root=ROOT,
                remove_root=ROOT / "remove",
                reason="re-running the no-delete proof; previous attempt set aside",
                batch_id=batch,
            )
    scratch.mkdir(parents=True, exist_ok=True)

    print("=== 1. plant sentinel files (the names the OLD purge deleted) ===")
    sentinels = {
        "frame_0001.png": b"sentinel-frame-png",
        "rgba_0002.exr": b"sentinel-rgba-exr",
        "depth_0003.png": b"sentinel-depth-png",
        "segmentation_0004.png": b"sentinel-segmentation-png",
    }
    keeper = scratch / "NOT_A_FRAME.txt"
    keeper.write_bytes(b"this file must survive untouched")

    before: dict[str, str] = {}
    for name, payload in sentinels.items():
        p = scratch / name
        p.write_bytes(payload)
        before[name] = sha256_file(p)
        print(f"    wrote {name}  sha256={before[name][:16]}...")

    print("\n=== 2. run the NEW purge entry point ===")
    moved = purge_stale_frames(scratch, workspace_root=ROOT, remove_root=remove_dir)
    check("purge reports the 4 sentinels", moved == len(sentinels), f"moved={moved}")

    print("\n=== 3. nothing was deleted; hashes are unchanged ===")
    for name, digest in before.items():
        still = scratch / name
        check(f"{name} left the scratch dir", not still.exists())
        candidates = list(remove_dir.rglob(name))
        check(f"{name} arrived in remove/", len(candidates) == 1,
              f"{len(candidates)} match(es)")
        if candidates:
            check(f"{name} sha256 unchanged", sha256_file(candidates[0]) == digest,
                  f"{sha256_file(candidates[0])[:16]}...")

    print("\n=== 4. a non-frame file is untouched ===")
    check("NOT_A_FRAME.txt still in scratch", keeper.is_file())
    check("NOT_A_FRAME.txt content intact",
          keeper.read_bytes() == b"this file must survive untouched")

    print("\n=== 5. the move manifest records the evidence ===")
    manifests = sorted(remove_dir.glob("*/move_manifest.json"))
    check("a move manifest was written", len(manifests) >= 1, f"{len(manifests)} found")
    if manifests:
        data = json.loads(manifests[-1].read_text(encoding="utf-8"))
        print(f"    manifest: {manifests[-1]}")
        print(f"    moved_count={data['moved_count']}  schema={data['schema_version']}")
        fields_ok = all(
            {"original", "destination", "reason", "bytes", "sha256"} <= set(m)
            for m in data["moved"]
        )
        check("every record has original/destination/reason/bytes/sha256", fields_ok)
        check("no failures recorded", not data["failures"], str(data["failures"]))

    print("\n=== 6. a re-run cannot reuse the first run's frames ===")
    run_base = base / "runs"
    first = allocate_run_dir(run_base, run_id, workspace_root=ROOT)
    (first / "frame_0001.png").write_bytes(b"first-run-frame")
    print(f"    first run dir : {first}")
    try:
        allocate_run_dir(run_base, run_id, workspace_root=ROOT)
        check("second allocation into a populated dir is REFUSED", False,
              "it was allowed")
    except OutputConflictError as exc:
        check("second allocation into a populated dir is REFUSED", True, str(exc)[:60])
    second = allocate_run_dir(run_base, f"{run_id}_a002", workspace_root=ROOT)
    print(f"    second run dir: {second}")
    check("the new attempt dir is distinct", first != second)
    check("the second dir does not contain the first run's frame",
          not (second / "frame_0001.png").exists())

    print("\n=== 7. workspace escape is refused ===")
    # NOTE: "tmp/../escape" resolves to "<root>/escape", which is still INSIDE the
    # workspace, so it is legitimately allowed.  A real escape must climb above the
    # workspace root.
    try:
        allocate_run_dir(ROOT / "tmp", "../../escape", workspace_root=ROOT)
        check("escaping run dir is refused", False, "it was allowed")
    except ValueError as exc:
        check("escaping run dir is refused", True, str(exc)[:60])

    try:
        from physim.safe_output import quarantine

        quarantine(
            [ROOT / "tmp"],
            workspace_root=ROOT,
            remove_root=ROOT.parent / "v55_escape_probe",
            reason="escape probe; must be refused",
        )
        check("escaping remove_root is refused", False, "it was allowed")
    except ValueError as exc:
        check("escaping remove_root is refused", True, str(exc)[:60])

    print()
    if FAILURES:
        print(f"RESULT: FAIL ({len(FAILURES)} check(s))")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("RESULT: PASS -- no file was deleted; stale frames were moved with matching hashes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
