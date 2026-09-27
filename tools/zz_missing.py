#!/usr/bin/env python
"""Are the AssetManager FileNotFoundError entries pre-existing?

Print exactly which file each failing asset is missing, and confirm none of
them is something this task touched.
"""
import sys

sys.path.insert(0, "src")
from physim.assets import AssetManager

am = AssetManager("configs/assets.yaml", "assets")
for aid in sorted(am.ids):
    try:
        am.get(aid)
        status = "OK"
    except Exception as e:
        status = f"MISSING -> {e}"
    print(f"{aid:45s} {status}")
