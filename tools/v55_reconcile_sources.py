#!/usr/bin/env python
"""V5.5 stage 03: reconcile the plan's source SHA-256 baselines with reality.

Findings so far (server AND local agree):
    Italian Flat  0027fcbd...  MATCHES the plan
    Hidden Alley  be1247889...  does NOT match the plan's 3dd51c6d...
    The Shed      fe6294a8...  does NOT match the plan's 18b007e0...

Both archives pass `unzip -t` and the extracted member sizes equal the archive
directory listing exactly, so neither download nor extraction is corrupt.  This
script reads the planning-stage audit JSONs to see what was measured when the
baselines were recorded, which distinguishes "stale baseline" from "wrong file".
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CANDIDATES = [
    "outcomes/v5_asset_review/scenes/hidden_alley.json",
    "outcomes/v5_asset_review/scenes/italian_flat.json",
    "outcomes/v5_asset_review/scenes/the_shed.json",
    "outcomes/v5_asset_review/scenes/render_manifest.json",
    "outcomes/v54_feasibility/hidden_alley_interaction_audit.json",
    "outcomes/v54_feasibility/italian_flat_interaction_audit.json",
]

PLAN = {
    "0027fcbd73411cce7f49b3d86c22c03d18980e22641083da9d8ba82d9fc94e25": "Italian Flat (plan)",
    "3dd51c6dc7aad321e6cd4bada26785d87cdf376e649f20aa4f87ef5cf127e151": "Hidden Alley (plan)",
    "18b007e0f55c4bb3b5f746c698b6c524508253cb763f2b7b14345cbefb81c8d0": "The Shed (plan)",
}
ACTUAL = {
    "0027fcbd73411cce7f49b3d86c22c03d18980e22641083da9d8ba82d9fc94e25": "Italian Flat (actual)",
    "be1247889cee3ce10028ee1ef1066a96728b3c2aa191ad12b51cc3b578fa4ae9": "Hidden Alley (actual)",
    "fe6294a84839e2225f2d9702a05ff5bc4472ff78743daabbcc60a7a95761c6e1": "The Shed (actual)",
}


def scan(obj, path=""):
    """Yield (path, key, value) for keys of interest anywhere in a JSON tree."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                yield from scan(value, f"{path}{key}.")
            elif any(t in key.lower() for t in ("sha", "hash", "mesh", "object", "size", "blend", "light", "camera")):
                yield (f"{path}{key}", key, value)
    elif isinstance(obj, list):
        for i, value in enumerate(obj[:5]):
            yield from scan(value, f"{path}[{i}].")


print("=== scanning planning-stage audit records ===")
for rel in CANDIDATES:
    p = ROOT / rel
    if not p.is_file():
        print(f"\n  [absent] {rel}")
        continue
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"\n  [unreadable] {rel}: {exc}")
        continue
    print(f"\n  [present] {rel}  ({p.stat().st_size} bytes)")
    hits = list(scan(data))
    shown = 0
    for full, key, value in hits:
        if any(t in key.lower() for t in ("sha", "hash", "mesh", "light", "camera")):
            print(f"      {full} = {value}")
            shown += 1
        if shown > 25:
            print("      ... (truncated)")
            break

    # Does this record contain a plan baseline or an actual hash?
    text = p.read_text(encoding="utf-8", errors="replace")
    for h, label in {**PLAN, **ACTUAL}.items():
        if h in text:
            print(f"      >>> contains {label}")

print()
print("=== conclusion inputs ===")
print("  plan baseline matches Italian Flat only;")
print("  Hidden Alley and The Shed on disk (server AND local) carry different hashes,")
print("  yet their archives verify and their extracted sizes equal the listings.")
