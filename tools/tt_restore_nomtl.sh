#!/usr/bin/env bash
# ===========================================================================
# Restore the turntable visual OBJ/MTL to their pre-experiment state.
#
# The MTL route was MEASURED and REJECTED (disc R/B 4.04 R/G 2.55 vs the frozen
# target 1.99/1.67).  The frozen look comes from a full PBR node tree applied by
# the pipeline, so the asset must go back to an EMPTY MTL and NO `usemtl` line.
#
# The .nomtl-bak backups are kept in place (they are the record of the original
# state); only model.obj / model.mtl are rewritten from them.
# ===========================================================================
export LC_ALL=C
V=/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/assets/objects/turntable/visual

cp -f "$V/model.obj.nomtl-bak" "$V/model.obj"
cp -f "$V/model.mtl.nomtl-bak" "$V/model.mtl"

echo "--- md5 (restored vs backup must match) ---"
md5sum "$V/model.obj" "$V/model.obj.nomtl-bak" "$V/model.mtl" "$V/model.mtl.nomtl-bak"

echo "--- usemtl count in model.obj (want 0) ---"
grep -c usemtl "$V/model.obj" || echo "0 (no usemtl line -- good)"

echo "--- model.mtl contents ---"
cat "$V/model.mtl"

echo "--- head of model.obj ---"
head -6 "$V/model.obj"

echo "--- directory listing (backups must still be present) ---"
ls -la "$V"
