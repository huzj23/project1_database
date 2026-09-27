"""License-gated synchronization for the project Hugging Face asset dataset.

Authentication is intentionally delegated to ``HF_TOKEN`` or the credential
stored by ``hf auth login``. Tokens must never be passed as command arguments
or written to project files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


DEFAULT_REPO_ID = "physics-video-lab/physics-video-assets"
DEFAULT_ENDPOINT = "https://huggingface.co"
DEFAULT_ALLOWED_LICENSES = ("CC0-1.0",)
DATASET_CARD = Path("docs/HUGGINGFACE_DATASET_CARD.md")
REMOTE_MANIFEST = "assets_manifest.json"
IGNORED_NAMES = {".DS_Store", "Thumbs.db"}
IGNORED_SUFFIXES = {".part", ".blend1", ".blend2", ".blend3"}


@dataclass(frozen=True)
class AssetRecord:
    asset_id: str
    kind: str
    license: str
    directory: Path
    relative_directory: Path
    metadata: dict[str, Any]


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_payload_file(path: Path) -> bool:
    return (
        path.is_file()
        and path.name not in IGNORED_NAMES
        and path.suffix.lower() not in IGNORED_SUFFIXES
        and "__pycache__" not in path.parts
    )


def discover_assets(project_root: Path) -> list[AssetRecord]:
    asset_root = project_root / "assets"
    records: list[AssetRecord] = []
    for manifest in sorted(asset_root.glob("**/asset.yaml")):
        metadata = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        directory = manifest.parent
        records.append(
            AssetRecord(
                asset_id=str(metadata["id"]),
                kind=str(metadata["kind"]),
                license=str(metadata.get("license", "UNKNOWN")),
                directory=directory,
                relative_directory=directory.relative_to(project_root),
                metadata=metadata,
            )
        )
    return records


def select_assets(
    records: Iterable[AssetRecord],
    requested_ids: set[str],
    allowed_licenses: set[str],
    *,
    include_unknown_private: bool = False,
) -> tuple[list[AssetRecord], list[AssetRecord]]:
    forbidden_license_labels = {"UNKNOWN", "UNLICENSED", "NONE", ""}
    unsafe_allowlist = {
        license_name
        for license_name in allowed_licenses
        if license_name.strip().upper() in forbidden_license_labels
    }
    if unsafe_allowlist:
        raise ValueError(
            "Unknown or absent licenses can never be upload-allowed: "
            + ", ".join(sorted(unsafe_allowlist))
        )
    records = list(records)
    known_ids = {record.asset_id for record in records}
    unknown_ids = requested_ids - known_ids
    if unknown_ids:
        raise ValueError("Unknown asset IDs: " + ", ".join(sorted(unknown_ids)))

    candidates = [
        record for record in records if not requested_ids or record.asset_id in requested_ids
    ]
    selected = [
        record
        for record in candidates
        if record.license in allowed_licenses
        or (include_unknown_private and record.license.strip().upper() == "UNKNOWN")
    ]
    blocked = [record for record in candidates if record not in selected]
    if requested_ids and blocked:
        details = ", ".join(
            f"{record.asset_id} ({record.license})" for record in blocked
        )
        raise RuntimeError(
            "Requested assets are not redistributable under the configured license "
            f"allowlist: {details}"
        )
    return selected, blocked


def _payload_files(record: AssetRecord) -> list[Path]:
    return [
        path
        for path in sorted(record.directory.rglob("*"))
        if _is_payload_file(path)
    ]


def build_remote_manifest(
    project_root: Path, records: Iterable[AssetRecord], repo_id: str = DEFAULT_REPO_ID
) -> dict[str, Any]:
    assets = []
    for record in records:
        files = []
        for path in _payload_files(record):
            files.append(
                {
                    "path": path.relative_to(project_root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        assets.append(
            {
                "id": record.asset_id,
                "kind": record.kind,
                "license": record.license,
                "source_page": record.metadata.get("source_page"),
                "directory": record.relative_directory.as_posix(),
                "files": files,
            }
        )
    return {
        "schema_version": 1,
        "repository": repo_id,
        "assets": assets,
    }


def _hub_api(endpoint: str):
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError(
            'Install asset synchronization dependencies with pip install -e ".[assets]"'
        ) from exc
    return HfApi(endpoint=endpoint)


def _require_authentication(api) -> None:
    try:
        api.whoami()
    except Exception as exc:
        raise RuntimeError(
            "Hugging Face authentication is required. Set HF_TOKEN for this process "
            "or run `hf auth login`; never commit a token to the repository."
        ) from exc


def upload_assets(
    project_root: Path,
    records: list[AssetRecord],
    repo_id: str,
    revision: str,
    endpoint: str,
) -> None:
    api = _hub_api(endpoint)
    _require_authentication(api)
    repo_info = api.repo_info(repo_id=repo_id, repo_type="dataset", revision=revision)
    unknown_license_assets = [
        record for record in records if record.license.strip().upper() == "UNKNOWN"
    ]
    if unknown_license_assets and not bool(repo_info.private):
        asset_ids = ", ".join(record.asset_id for record in unknown_license_assets)
        raise RuntimeError(
            "Refusing to upload UNKNOWN-license assets to a non-private repository: "
            + asset_ids
        )

    # Hash every payload before the first remote mutation. This catches local
    # read errors early and makes the manifest describe the exact upload input.
    manifest = build_remote_manifest(project_root, records, repo_id)
    manifest_path = project_root / "cache" / "huggingface-assets" / REMOTE_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    card_path = project_root / DATASET_CARD
    api.upload_file(
        path_or_fileobj=str(card_path),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
        revision=revision,
        commit_message="Document physics-video asset bundle",
    )

    ignore_patterns = [
        "**/.DS_Store",
        "**/Thumbs.db",
        "**/*.part",
        "**/*.blend1",
        "**/*.blend2",
        "**/*.blend3",
        "**/__pycache__/**",
    ]
    for record in records:
        print(
            f"Uploading {record.asset_id} ({record.license}) -> "
            f"{record.relative_directory.as_posix()}"
        )
        api.upload_folder(
            folder_path=str(record.directory),
            path_in_repo=record.relative_directory.as_posix(),
            repo_id=repo_id,
            repo_type="dataset",
            revision=revision,
            ignore_patterns=ignore_patterns,
            commit_message=f"Sync asset {record.asset_id}",
        )

    api.upload_file(
        path_or_fileobj=str(manifest_path),
        path_in_repo=REMOTE_MANIFEST,
        repo_id=repo_id,
        repo_type="dataset",
        revision=revision,
        commit_message="Update checksummed asset manifest",
    )


def _download_manifest(
    project_root: Path, repo_id: str, revision: str, endpoint: str
) -> dict[str, Any]:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            'Install asset synchronization dependencies with pip install -e ".[assets]"'
        ) from exc
    path = hf_hub_download(
        repo_id=repo_id,
        repo_type="dataset",
        revision=revision,
        filename=REMOTE_MANIFEST,
        cache_dir=project_root / "cache" / "huggingface-assets" / "hub",
        endpoint=endpoint,
    )
    return json.loads(Path(path).read_text(encoding="utf-8"))


def download_assets(
    project_root: Path,
    repo_id: str,
    revision: str,
    requested_ids: set[str],
    endpoint: str,
) -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            'Install asset synchronization dependencies with pip install -e ".[assets]"'
        ) from exc
    manifest = _download_manifest(project_root, repo_id, revision, endpoint)
    remote_assets = {entry["id"]: entry for entry in manifest["assets"]}
    unknown_ids = requested_ids - remote_assets.keys()
    if unknown_ids:
        raise ValueError("Assets absent from remote manifest: " + ", ".join(unknown_ids))
    selected = [
        entry
        for asset_id, entry in sorted(remote_assets.items())
        if not requested_ids or asset_id in requested_ids
    ]
    cache_dir = project_root / "cache" / "huggingface-assets" / "hub"
    for entry in selected:
        print(f"Downloading {entry['id']} ({entry['license']})")
        for file_record in entry["files"]:
            relative_path = Path(file_record["path"])
            target = project_root / relative_path
            if target.exists() and _sha256(target) == file_record["sha256"]:
                continue
            cached = hf_hub_download(
                repo_id=repo_id,
                repo_type="dataset",
                revision=revision,
                filename=relative_path.as_posix(),
                cache_dir=cache_dir,
                endpoint=endpoint,
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cached, target)
            if _sha256(target) != file_record["sha256"]:
                raise RuntimeError(f"SHA-256 mismatch after download: {target}")


def verify_assets(
    project_root: Path,
    repo_id: str,
    revision: str,
    requested_ids: set[str],
    endpoint: str,
) -> None:
    manifest = _download_manifest(project_root, repo_id, revision, endpoint)
    failures = []
    for entry in manifest["assets"]:
        if requested_ids and entry["id"] not in requested_ids:
            continue
        for file_record in entry["files"]:
            path = project_root / file_record["path"]
            if not path.exists():
                failures.append(f"missing: {file_record['path']}")
            elif path.stat().st_size != file_record["bytes"]:
                failures.append(f"size: {file_record['path']}")
            elif _sha256(path) != file_record["sha256"]:
                failures.append(f"sha256: {file_record['path']}")
    if failures:
        raise RuntimeError("Asset verification failed:\n" + "\n".join(failures))
    print("Asset verification passed")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "upload", "download", "verify"))
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument("--revision", default="main")
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=(
            "Hub API endpoint. Defaults to the official service so private repository "
            "authentication is not accidentally sent to a public mirror."
        ),
    )
    parser.add_argument("--asset-id", action="append", default=[])
    parser.add_argument(
        "--allowed-license",
        action="append",
        default=[],
        help="Upload allowlist. Defaults to CC0-1.0; does not affect downloads.",
    )
    parser.add_argument(
        "--include-unknown-private",
        action="store_true",
        help=(
            "Include UNKNOWN-license assets for private archival only. Upload aborts "
            "unless the Hub confirms that the dataset repository is private."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    project_root = _project_root()
    requested_ids = set(args.asset_id)
    records = discover_assets(project_root)
    allowed_licenses = set(args.allowed_license or DEFAULT_ALLOWED_LICENSES)
    if args.include_unknown_private and args.command not in {"list", "upload"}:
        raise ValueError("--include-unknown-private is only valid for list/upload")
    selected, blocked = select_assets(
        records,
        requested_ids,
        allowed_licenses,
        include_unknown_private=args.include_unknown_private,
    )

    if args.command == "list" or args.dry_run:
        for record in selected:
            size = sum(path.stat().st_size for path in _payload_files(record))
            print(f"UPLOAD\t{record.asset_id}\t{record.license}\t{size}")
        for record in blocked:
            print(f"BLOCKED\t{record.asset_id}\t{record.license}")
        if args.command == "list" or args.dry_run:
            return 0

    if args.command == "upload":
        upload_assets(
            project_root, selected, args.repo_id, args.revision, args.endpoint
        )
    elif args.command == "download":
        download_assets(
            project_root,
            args.repo_id,
            args.revision,
            requested_ids,
            args.endpoint,
        )
    elif args.command == "verify":
        verify_assets(
            project_root,
            args.repo_id,
            args.revision,
            requested_ids,
            args.endpoint,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
