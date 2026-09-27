# ReplicaCAD

Asset ID: `replicad_apartment`

## Source

- **Dataset**: ReplicaCAD (FAIR / Meta)
- **Components used**: `frl_apartment_stage` stage + the authored `apt_0` layout
- **Source page**: <https://aihabitat.org/datasets/replica_cad/>
- **Download**: `ReplicaCAD_Interactive_full.zip`
  (<https://dl.fbaipublicfiles.com/habitat/ReplicaCAD/ReplicaCAD_Interactive_full.zip>)
- **Author / attribution**: Meta AI (FAIR) — ReplicaCAD
- **License**: CC BY-NC 4.0 (NonCommercial) —
  <https://creativecommons.org/licenses/by-nc/4.0/>

## What is in `source/`

A deliberately small subset of the original dataset — the stage mesh plus the
licence and dataset description. The full dataset is ~1000 files and is **not**
mirrored here.

| file | sha256 |
| --- | --- |
| `frl_apartment_stage.glb` | `9a28a0511ab15cb48bbd1a6a171798918f24b66e54a8406d69d270938d71d923` |
| `LICENSE.txt` | `c9762a65b0ea0af9d2370ec5127dc10873ae04603df4da9acc884d99b68995a3` |
| `README.md` | `f1e8537c1f559964534e320843aa0fa36f9505c83f28cddeadbef4ff9d2239e4` |
| `replicaCAD.scene_dataset_config.json` | `137c59f82387650d3e62ecef6a0053753e54b67c5b53526cc134cbe9ef386b06` |

## Runtime files derived from it

- `visual/scene.blend` — packed Blender scene: world transforms baked, merged
  into a single mesh object named `environment` (313,181 vertices), all 86/86
  textures packed, the author's lights preserved in the `environment_lighting`
  collection (7 POINT) and the original World preserved as `environment_world`.
- `collision/surfaces/replicad_apartment_floor.obj` (+ `.urdf`) — 94-triangle
  static floor mesh extracted from the scene's own floor slab.

## NonCommercial

CC BY-NC 4.0 forbids commercial use. Academic research use is permitted; the
attribution above must be retained and the NonCommercial restriction passed on.
