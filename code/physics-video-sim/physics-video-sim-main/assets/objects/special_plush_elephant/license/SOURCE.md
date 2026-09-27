# Sootheze_Cold_Therapy_Elephant

Asset ID: `special_plush_elephant`

## Source

- **Dataset**: Google Scanned Objects (GSO) — "Scanned Objects by Google Research"
- **Object**: `Sootheze_Cold_Therapy_Elephant`
- **Source page**: <https://app.gazebosim.org/GoogleResearch/fuel/collections/Scanned%20Objects%20by%20Google%20Research>
- **Mirror used** (unaltered, in `source/`):
  <https://console.cloud.google.com/storage/browser/kubric-public/assets/GSO>
  archive `Sootheze_Cold_Therapy_Elephant.tar.gz`
- **Author / attribution**: Google Research (Google LLC), Scanned Objects dataset.
- **License**: CC BY-SA 4.0 — <https://creativecommons.org/licenses/by-sa/4.0/>

The license is recorded as `CC BY-SA 4.0` in the dataset manifest (`GSO.json`,
`assets.Sootheze_Cold_Therapy_Elephant.license`) and in the object's own
`data.json` (`"license": "CC BY-SA 4.0"`), both of which are reproduced in
`source/`.

## What is in `source/`

The unaltered original download, byte-for-byte:

| file | sha256 |
| --- | --- |
| `Sootheze_Cold_Therapy_Elephant.tar.gz` | `1d19e919625da7054ea1f054208281e676711385dfd03f5c0eb189a3b4cac63c` |
| `visual_geometry.obj` | `a84d957258a57222bd324098538896cd9e4ed39ff6af4731f3134d5eb07efe4d` |
| `visual_geometry.mtl` | `857543aabcc8a25b1c200b087d6bbe7395cd865666930960fa0f0aec421ea6aa` |
| `texture.png` | `3879b965fd2b4fc64c19dc2668bf09fb6835768ae933f1d84089117891ff6b3c` |
| `collision_geometry.obj` | `c573d7a81f0f3e2518e091177a4100bbf431ccd71892d634f3ad7a3529707410` |
| `object.urdf` | `19fbc2b4ecd9734462c9f20790ae1454acc93998f7f9b3fe7c3348cc702e0bb7` |
| `data.json` | `5dcfec5ba9dbc97a0ca18e6fe7c81ac654ebe9c6570e77b7970087d3e30bec57` |

`source/` is never overwritten by asset processing (see the project asset
conventions).

## Runtime files derived from it

- `visual/model.obj` — copy of `source/visual_geometry.obj` (unchanged).
- `collision/model.obj` + `collision/model.urdf` — regenerated low-poly convex
  hull, 512 triangles, produced with the project's
  `scripts/generate_collision_mesh.py` at `--target-faces 512`, then rotated by
  the exact inverse `Rx(-90)` so that it shares the visual's own frame.  See the
  header comment in `asset.yaml` and
  `log/V4.1_调研结果文档_碰撞体生成脚本对OBJ输入的坐标系缺陷_20260923.md`.

## ShareAlike

CC BY-SA 4.0 is a copyleft licence. Derivative datasets that redistribute this
asset, or renders of it, must be released under a compatible licence and must
carry the attribution above. Academic use is permitted.
