#!/usr/bin/env bash
# Two blockers that decide tonight's plan shape:
#  A) is there ANY ball-like object with a real visual? (spheres have asset.yaml
#     pointing at visual/model.glb, but no visual/ dir exists)
#  B) is damping (linearDamping/angularDamping) wired into the physics backend?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== A) ball-like GSO objects we downloaded ==="
ls -1 "$WS/models/gso" | grep -iE 'ball|sphere|orb|globe|marble|bounc|round' | sed 's/^/  /'
echo "  (count of all GSO dirs: $(ls -1 "$WS/models/gso" | wc -l))"

echo
echo "=== A2) confirm spheres/food/cup truly lack visuals ==="
for n in sphere_basketball sphere_football food_apple special_coffee_cup; do
  d="$REPO/assets/objects/$n"
  echo "  $n:"
  find "$d" -type f 2>/dev/null | sed "s|$d/|    |"
done

echo
echo "=== A3) which GSO dirs have a visual model.obj we registered? ==="
for d in "$REPO"/assets/objects/gso_*/; do
  n=$(basename "$d")
  sz=$(stat -c%s "$d/visual/model.obj" 2>/dev/null || echo 0)
  printf "  %-46s model.obj=%s bytes\n" "$n" "$sz"
done

echo
echo "=== B) the full changeDynamics call (is damping passed?) ==="
sed -n '130,160p' "$REPO/src/physim/physics/pybullet_backend.py" 2>/dev/null | sed 's/^/  /'

echo
echo "=== B2) does the physics asset spec even have a damping field? ==="
grep -rn 'damping' "$REPO/src/physim/assets/"*.py "$REPO/src/physim/physics/"*.py 2>/dev/null | sed 's/^/  /'
echo "  (empty above = damping is NOT supported yet)"
