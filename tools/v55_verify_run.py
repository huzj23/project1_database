"""Verify the run directory satisfies 02's required-file list, and print every key check."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
RUN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle" / (
    sys.argv[1] if len(sys.argv) > 1 else "20260929T090000")

REQUIRED = ["resolved_config.json", "provenance.json", "bodies.json", "trajectory.json",
            "motion_substeps.jsonl", "contacts.jsonl", "events.json", "causality.json",
            "validation.json", "scene_delta.json", "camera.json", "status.json", "commands.txt"]

print("=" * 96)
print(f"=== {RUN.name}: required-file check ===")
missing = []
for name in REQUIRED:
    p = RUN / name
    if p.is_file():
        print(f"  [x] {name:26s} {p.stat().st_size:>10d} bytes")
    else:
        print(f"  [ ] {name:26s} MISSING")
        missing.append(name)
for extra in ("acceptance.json", "control_no_trigger.json", "soft_no_go_check.json",
              "SHA256SUMS.txt", "impulse_proxy.json"):
    p = RUN / extra
    print(f"  [{'x' if p.is_file() else ' '}] {extra:26s} "
          f"{p.stat().st_size if p.is_file() else 0:>10d} bytes")

print("\n=== acceptance.json ===")
acc = json.loads((RUN / "acceptance.json").read_text(encoding="utf-8"))
print(json.dumps(acc, indent=2)[:3000])

print("\n=== status.json ===")
st = json.loads((RUN / "status.json").read_text(encoding="utf-8"))
print(f"  all_pass={st['all_pass']}  frames={st['frame_count']}  "
      f"physics_fps={st['physics_fps']}  video_fps={st['video_fps']}")
for c in st["criteria"]:
    print(f"    [{'x' if c['pass'] else ' '}] {c['name']}: {c['detail']}")

print("\n=== validation.json ===")
print(json.dumps(json.loads((RUN / "validation.json").read_text(encoding="utf-8")), indent=2))

print("\n=== contacts.jsonl summary ===")
pairs = {}
n = 0
steps = set()
with (RUN / "contacts.jsonl").open("r", encoding="utf-8") as h:
    for line in h:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        n += 1
        steps.add(r["step"])
        pairs["|".join(r["pair"])] = pairs.get("|".join(r["pair"]), 0) + 1
print(f"  {n} contact rows across {len(steps)} distinct substeps (steps {min(steps)}..{max(steps)})")
for k, v in sorted(pairs.items(), key=lambda kv: -kv[1]):
    print(f"    {k:40s} {v:>7d} rows")

print("\n=== trajectory.json ===")
tr = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))
print(f"  video_fps={tr['video_fps']}  quaternions={tr['quaternion_convention']}")
for k, rows in tr["bodies"].items():
    print(f"    {k:18s} {len(rows)} frames  first t={rows[0]['time_s']} "
          f"last t={rows[-1]['time_s']}  blender {rows[0]['blender_frame']}.."
          f"{rows[-1]['blender_frame']}")

print("\n=== SHA256SUMS.txt ===")
sp = RUN / "SHA256SUMS.txt"
if sp.is_file():
    lines = sp.read_text(encoding="utf-8").strip().splitlines()
    print(f"  {len(lines)} files hashed")
    for line in lines[:6]:
        print(f"    {line}")
    print("    ...")
else:
    print("  MISSING")

print("\n" + "=" * 96)
print(f"RESULT: {'COMPLETE' if not missing else 'INCOMPLETE: ' + ', '.join(missing)}")
