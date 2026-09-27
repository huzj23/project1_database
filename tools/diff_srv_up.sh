#!/usr/bin/env bash
# ===========================================================================
# AUTHORITATIVE diff: SERVER tree vs pristine upstream.
#
# The V3.7 subagent diffed a STALE LOCAL checkout, which is why it reported that
# setTimeStep does not exist, that physics_fps 560 is rejected by a `!= 240` guard,
# and that scenarios/damping.py is missing.  All three are false on the server
# (verified: setTimeStep at pybullet_backend.py:73, guard is `< 240` at line 45,
# damping.py exists, projectile_gso.yaml exists).  The server produced every
# delivered video, so the server is the authoritative side.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
UP="$WS/tmp/upstream_x/physics-video-sim-main"
SRV="$WS/code/physics-video-sim/physics-video-sim-main"

"$WS/tools/conda_env/bin/python" -u - <<'PY'
import hashlib, os, subprocess
UP  = "/data/raw/huzijian/project1_database/tmp/upstream_x/physics-video-sim-main"
SRV = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
SKIP = {"__pycache__", ".git", ".pytest_cache", "cache", "datasets", "outputs", "logs"}
EXT = {".py", ".yaml", ".yml", ".md", ".toml", ".cfg", ".txt", ".urdf", ".obj", ".mtl"}

def walk(root):
    out = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP]
        for fn in fns:
            p = os.path.join(dp, fn)
            if os.path.splitext(fn)[1].lower() in EXT:
                out[os.path.relpath(p, root)] = hashlib.md5(open(p, "rb").read()).hexdigest()
    return out

up, srv = walk(UP), walk(SRV)
added   = sorted(set(srv) - set(up))
removed = sorted(set(up) - set(srv))
common  = sorted(set(up) & set(srv))
modified = [f for f in common if up[f] != srv[f]]

print(f"upstream={len(up)}  server={len(srv)}  identical={len(common)-len(modified)}")
print(f"\n=== ADDED ({len(added)}) ===")
for f in added: print(f"  + {f}")
print(f"\n=== MODIFIED ({len(modified)}) ===")
for f in modified: print(f"  M {f}")
print(f"\n=== REMOVED ({len(removed)}) ===")
for f in removed: print(f"  - {f}")

print("\n=== line deltas for modified source ===")
tot_p = tot_m = 0
for f in modified:
    if not f.endswith((".py", ".yaml")): continue
    r = subprocess.run(["diff", "-u", os.path.join(UP, f), os.path.join(SRV, f)],
                       capture_output=True, text=True).stdout
    p = sum(1 for l in r.splitlines() if l.startswith("+") and not l.startswith("+++"))
    m = sum(1 for l in r.splitlines() if l.startswith("-") and not l.startswith("---"))
    tot_p += p; tot_m += m
    print(f"  {f:54s} +{p:5d} / -{m:5d}")
print(f"  {'TOTAL':54s} +{tot_p:5d} / -{tot_m:5d}")
PY
