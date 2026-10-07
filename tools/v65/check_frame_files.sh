#!/bin/bash
# The frame QA found 215/216 PNGs on disk although all 216 sidecars exist. Report exactly which frame lacks a PNG and
# which lacks a sidecar -- the two are written at different moments, so a kill between them leaves this state.
R=/data/raw/huzijian/project1_database
O=$R/outcomes/v65/radio_scurve_domino/v65_20261007_final
echo "pngs:     $(ls "$O/frames"/Scene_*.png 2>/dev/null | wc -l)"
echo "sidecars: $(ls "$O/frames_meta"/Scene_*.json 2>/dev/null | wc -l)"
mp=""
ms=""
for i in $(seq 1 216); do
  [ -f "$(printf '%s/frames/Scene_%05d.png' "$O" "$i")" ] || mp="$mp $i"
  [ -f "$(printf '%s/frames_meta/Scene_%05d.json' "$O" "$i")" ] || ms="$ms $i"
done
echo "missing PNG:$mp"
echo "missing sidecar:$ms"
