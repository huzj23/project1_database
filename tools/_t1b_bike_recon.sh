#!/usr/bin/env bash
# Locate the bicycle (and all props) in the ReplicaCAD source layout.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
R="$WS/models/backgrounds/replicad"
echo "=== A: replicad root ==="
ls -la "$R" 2>/dev/null
echo "=== B: configs ==="
ls -la "$R/configs" 2>/dev/null
ls -la "$R/configs/scenes" 2>/dev/null
echo "=== C: scene instance json ==="
head -c 2000 "$R/configs/scenes/apt_0.scene_instance.json" 2>/dev/null
echo ""
echo "=== D: objects dir ==="
ls "$R/objects" 2>/dev/null | head -60
echo "=== E: bike-ish templates ==="
ls "$R/objects" 2>/dev/null | grep -i -E 'bike|cycle|wheel'
echo "=== F: object count ==="
ls "$R/objects" 2>/dev/null | wc -l
echo "=== G: apt_0 dataset json ==="
ls -la "$R/configs/scenes" 2>/dev/null
echo "RC BIKE RECON DONE"
