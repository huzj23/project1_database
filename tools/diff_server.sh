#!/usr/bin/env bash
# ===========================================================================
# Confirm the pristine upstream zip really IS the repo the user named
# (https://github.com/TLEphage/physics-video-sim), then diff the SERVER tree
# against it -- NOT the stale local checkout.
#
# The V3.7 subagent's diff was taken from a local copy that has since diverged from
# the server (the server has setTimeStep, a relaxed <240 guard, damping.py and
# projectile_gso.yaml, none of which the local copy had).  The server is what
# produced every delivered video, so it is the authoritative side of this diff.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
UP="$WS/tmp/upstream_physics_video_sim/physics-video-sim-main"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== upstream README identity ==="
head -30 "$UP/README.md" 2>/dev/null | sed 's/^/  /'
echo "  --- any repo URL mentioned? ---"
grep -rniE 'github.com/[A-Za-z0-9_.-]+/physics-video-sim' "$UP/README.md" "$UP/pyproject.toml" 2>/dev/null | head -5 | sed 's/^/  /'

echo
echo "=== upstream scenario/config inventory (proves it is pristine) ==="
ls "$UP/configs/scenarios/" 2>/dev/null | sed 's/^/  /'
echo "  --- upstream assets (should be mentor's, not ours) ---"
ls "$UP/assets/objects/" 2>/dev/null | head -20 | sed 's/^/  /'
echo "  --- upstream maps.yaml map ids ---"
grep -nE '^\s{2}[a-z_]+:' "$UP/configs/maps.yaml" 2>/dev/null | head -12 | sed 's/^/  /'

echo
echo "=== SERVER vs UPSTREAM: file-by-file diff ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import hashlib, os
UP = "/data/raw/huzijian/project1_database/tmp/upstream_physics_video_sim/physics-video-sim-main"
SRV = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
SKIP = {"__pycache__", ".git", "cache", "datasets", "outputs", "logs", "tmp"}
EXT = {".py", ".yaml", ".yml", ".md", ".toml", ".cfg", ".txt", ".json", ".urdf", ".obj", ".mtl"}

def walk(root):
    out = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP]
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root)
            if os.path.splitext(fn)[1].lower() in EXT:
                out[rel] = hashlib.md5(open(p, "rb").read()).hexdigest()
    return out

up, srv = walk(UP), walk(SRV)
added = sorted(set(srv) - set(up))
removed = sorted(set(up) - set(srv))
common = sorted(set(up) & set(srv))
modified = [f for f in common if up[f] != srv[f]]

print(f"  upstream files={len(up)}  server files={len(srv)}")
print(f"  ADDED   = {len(added)}")
for f in added: print(f"      + {f}")
print(f"  MODIFIED= {len(modified)}")
for f in modified: print(f"      M {f}")
print(f"  REMOVED = {len(removed)}")
for f in removed[:40]: print(f"      - {f}")
print(f"  IDENTICAL = {len(common) - len(modified)}")

# line-level counts for the modified python files
print()
print("  --- line deltas for modified source files ---")
import subprocess
for f in modified:
    if not f.endswith((".py", ".yaml")):
        continue
    a = os.path.join(UP, f); b = os.path.join(SRV, f)
    r = subprocess.run(["diff", "-u", a, b], capture_output=True, text=True).stdout
    plus = sum(1 for l in r.splitlines() if l.startswith("+") and not l.startswith("+++"))
    minus = sum(1 for l in r.splitlines() if l.startswith("-") and not l.startswith("---"))
    print(f"    {f:52s} +{plus:5d} / -{minus:5d}")
PY
