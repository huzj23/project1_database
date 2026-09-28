#!/usr/bin/env bash
# V5.5 stage 03 section 2: which candidates ship a usable collision mesh + URDF?
#
# 03 requires the chosen assets to have a reliable collision proxy.  GSO ships a designed
# `collision_geometry.obj` and an `object.urdf` per asset, so this records which of the
# shortlisted candidates actually have them, and their triangle counts.
set -uo pipefail
R=/data/raw/huzijian/project1_database
G="$R/models/gso"

CANDS="Borage_GLA240Gamma_Tocopherol Creatine_Monohydrate Big_Dot_Aqua_Pencil_Case \
Clue_Board_Game_Classic_Edition JarroDophilusFOS_Value_Size \
New_Super_Mario_BrosWii_Wii_Game Pokmon_X_Nintendo_3DS_Game \
Animal_Crossing_New_Leaf_Nintendo_3DS_Game Paper_Mario_Sticker_Star_Nintendo_3DS_Game \
Luigis_Mansion_Dark_Moon_Nintendo_3DS_Game House_of_Cards_The_Complete_First_Season_4_D \
Simon_Swipe_Game"

printf '%-46s %-8s %-10s %-8s %-8s %s\n' ASSET COLL OBJ_TRIS URDF TXT VIS_TRIS
for a in $CANDS; do
  d="$G/$a"
  if [ ! -d "$d" ]; then printf '%-46s %s\n' "$a" "ABSENT"; continue; fi
  coll="-"; urdf="-"; txt="-"; vtris="-"
  [ -f "$d/collision_geometry.obj" ] && coll="yes"
  [ -f "$d/object.urdf" ] && urdf="yes"
  [ -f "$d/texture.png" ] && txt="yes"
  ctris=$(grep -c '^f ' "$d/collision_geometry.obj" 2>/dev/null || echo 0)
  vtris=$(grep -c '^f ' "$d/visual_geometry.obj" 2>/dev/null || echo 0)
  printf '%-46s %-8s %-10s %-8s %-8s %s\n' "$a" "$coll" "$ctris" "$urdf" "$txt" "$vtris"
done

echo
echo "=== does the URDF reference a mesh, and which one? ==="
for a in Big_Dot_Aqua_Pencil_Case Animal_Crossing_New_Leaf_Nintendo_3DS_Game; do
  echo "  --- $a ---"
  grep -E 'mesh|filename|mass|inertia' "$G/$a/object.urdf" 2>/dev/null | head -8 | sed 's/^/      /'
done

echo
echo "=== data.json for the pencil case (why no review image?) ==="
cat "$G/Big_Dot_Aqua_Pencil_Case/data.json" 2>/dev/null | head -20
