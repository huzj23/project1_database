#!/usr/bin/env bash
source /data/raw/huzijian/project1_database/tools/server_env.sh
"$WS/tools/conda_env/bin/python" "$WS/tools/zz_mask.py" 2>&1
echo "=================================================="
"$BLENDER" --background --factory-startup --python "$WS/tools/zz_project.py" 2>&1 \
  | grep -vE 'Progress|^$|gvfs|Material not found|Blender 3.4|Blender quit|building geometries|Importing OBJ|Parsing OBJ|Done'
