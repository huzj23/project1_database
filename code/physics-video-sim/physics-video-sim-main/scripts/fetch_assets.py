"""Download files declared by project-owned asset manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import urllib.request
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/server.yaml")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root / "src"))
    from physim.assets import AssetManager
    from physim.config import load_run_config

    config_path = project_root / args.config
    config = load_run_config(config_path)
    asset_root = Path(config["paths"]["asset_root"])
    if not asset_root.is_absolute():
        asset_root = project_root / asset_root
    try:
        import certifi

        tls_context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        tls_context = ssl.create_default_context()
    registry_path = Path(config["paths"]["asset_registry"])
    if not registry_path.is_absolute():
        registry_path = project_root / registry_path
    asset_manager = AssetManager(registry_path, asset_root)
    records = []
    for asset in asset_manager.all(require_files=False):
        entry = asset.metadata
        target = asset.visual_path
        download_url = entry.get("download_url")
        if target is None or not download_url:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            print(f"Downloading {asset.asset_id} -> {target}")
            partial = target.with_suffix(target.suffix + ".part")
            request = urllib.request.Request(
                download_url,
                headers={"User-Agent": "physics-video-sim/0.1 asset fetcher"},
            )
            with urllib.request.urlopen(request, context=tls_context) as response, partial.open(
                "wb"
            ) as stream:
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
            partial.replace(target)
        digest = _sha256(target)
        expected_digest = entry.get("sha256")
        if expected_digest and digest != expected_digest:
            raise RuntimeError(
                f"SHA-256 mismatch for {target}: expected {expected_digest}, got {digest}"
            )
        records.append(
            {
                "id": asset.asset_id,
                "kind": asset.kind,
                "path": str(target.relative_to(asset_root)),
                "source_page": entry.get("source_page"),
                "download_url": download_url,
                "license": entry.get("license"),
                "sha256": digest,
                "bytes": target.stat().st_size,
            }
        )
    manifest = asset_root / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"ASSET_MANIFEST={manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
