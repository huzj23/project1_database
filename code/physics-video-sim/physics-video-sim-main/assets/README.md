# Asset conventions

本目录保存项目资产。`source/`、`visual/`、纹理、碰撞网格和 HDRI 等大文件保留在仓库
工作目录中并由 `.gitignore` 排除；`asset.yaml` 与 `license/` 需要提交到 Git。Scenario
只能按 asset ID 请求 `AssetManager`，不得引用具体文件路径。

## 命名规则

正式 ID、资产目录名和 `asset.yaml` 中的 `id` 必须一致，使用小写
`<category>_<minimal_name>`，只使用 ASCII 字母、数字和下划线。名称描述资产本身，
不包含下载站、作者、许可证或 `custom`、`final`、`new` 等过程信息。

对象类别固定为：

- `sphere`：近似球体，例如 `sphere_baseball`、`sphere_basketball`；
- `cylinder`：圆柱体；
- `cube`：立方体或长方体；
- `cone`：圆锥体；
- `food`：不应仅按基本几何体理解的食品；
- `special`：组合机构或特殊装置，例如 `special_newtons_cradle`。

环境仍使用 `kind: environment` 和 `category: environment`，但目录名与 asset ID 不添加
`environment_` 前缀，直接使用最简场景名，例如 `classroom`、`basketball_court`。这是因为
其所在的 `assets/environments/` 目录和 manifest kind 已经表达资产类型。拼写统一使用
`sphere`，不使用 `shpere`。

## 目录结构

```text
assets/
├── objects/<asset_id>/
│   ├── asset.yaml
│   ├── source/                 # 未修改的原始下载
│   ├── visual/model.glb        # 推荐的运行时对象
│   ├── collision/              # 低面数碰撞网格与 URDF
│   └── license/SOURCE.md
├── environments/<asset_id>/
│   ├── asset.yaml
│   ├── source/                 # 原始场景、压缩包和纹理
│   ├── visual/scene.blend      # 复杂场景使用 packed Blend
│   ├── collision/surfaces/     # 从选中区域真实几何提取的静态 mesh/URDF
│   └── license/SOURCE.md
├── materials/<asset_id>/...
└── hdri/<asset_id>/...
```

简单对象优先使用自包含 GLB。具有大量旧节点材质、层级实例或外部纹理的复杂环境优先
使用 packed `.blend`，并在 manifest 中设置 `visual.object_name: environment`。

## 处理流程

1. 将下载文件原样放入 `source/`，记录来源页、作者、许可证和原始 SHA256。
2. 在 Blender 中检查单位、世界坐标、层级、材质、纹理、UV、法线和模型边界。
3. 对象烘焙世界变换、移除父子层级、居中，并缩放到真实米制尺寸。烘焙负行列式（镜像）变换时必须翻转法线，避免开启背面剔除的材质出现半边消失。
   manifest 还应通过 `initial_orientation.quaternion_wxyz` 记录符合常识的静止初始姿态：
   杯子底面朝下且杯口朝上；具有明显长短轴的水果应让稳定短轴触地。该四元数必须同时用于
   Scenario、PyBullet 和 Blender，不能只在预览中旋转 visual。
4. 对于类别不是 `sphere`、`cylinder`、`cube`、`cone` 的对象，必须从归一化后的
   visual 生成独立低面数碰撞 mesh；禁止退化为包围球，也禁止直接使用高模 visual mesh。
5. 环境烘焙世界变换，合并为一个名为 `environment` 的 mesh，并把所有纹理打包。原工程的
   灯光对象必须保留在 `environment_lighting` collection，原 World 必须保留为
   `environment_world`；不得为了简化运行时资产而删除作者灯光设计。
6. 运行时必须先导入原灯光和 World，且不得删除或修改作者灯光。固定 seed 的 Cycles 预览若确认
   原灯光不足，则在 `asset.yaml` 显式增加 `render.supplemental_lights`：先采用一盏 Sun 和一盏
   Area；仍不足时才为该环境设计多 Area。不得按帧自动改灯或曝光。完全没有原灯光和显式补光时，
   才使用 `render.area_lights`；三者都没有时才使用 renderer 默认灯光。
7. 在 `asset.yaml` 中记录运行时 SHA256、实际 `size`、`scale`、碰撞和物理范围。
8. 环境还需在 `configs/maps.yaml` 中配置经过人工核对的 surface；复杂场景不能把
   整体可视网格直接当作仿真支撑面。
   同一地图应按 `surface_groups` 声明区域类型、适用物体最大尺寸范围和多个 `regions`。
   例如 classroom 的 `floor` 接受篮球/足球，`table_top` 接受棒球、lime、lychee 等小物体。
   每个 region 必须确认运动范围内没有杂物或静态几何占用，并标记
   `cleanliness: verified_clear`；教师桌等有书本文具的表面不得登记为合法 surface。
   对大而连续且干净的地面，优先登记尽可能大的区域；被路沿、家具或杂物切断时，登记多个
   经过验证的小区域。不能只保留一个方便测试的角落，应在保持净空的前提下充分覆盖地图。
   非矩形或曲面区域应从模型对应部件提取低面静态碰撞 mesh，不能用覆盖空洞或曲面的简单
   立方体代替；采样 bounds 仍应取碰撞 mesh 内部经验证的安全范围。
   视线被家具遮挡时，region 相机覆盖应优先设置 `azimuth_offset_degrees` 绕世界 Z 轴旋转，
   而不是优先增大 `elevation_degrees` 或 `min_height_above_trajectory`。
   linked collection instance（例如 classroom 的课桌和椅子）必须先实体化，再合并运行时 mesh。
9. 先进行 AssetManager/Scenario 枚举，再用 Blender 固定 seed 渲染物体与场景组合。

当前可注册的刚体 Scenario 为 `rolling`、`constant_force` 和 `free_fall`。只有经过对应
物理与碰撞验证的资产才应把该名称加入 `allowed_scenarios`；该字段表示兼容性，不表示每次
运行都必须选择该资产。
10. 服务器完整生成前还需执行 PyBullet、Validation 和单 GPU Blender headless 测试。

项目脚本 `scripts/prepare_visual_asset.py` 用于生成运行时副本。例如：

```powershell
# 把任意单位的篮球归一化到直径 0.24 m
blender --background --factory-startup --python scripts/prepare_visual_asset.py -- `
  --source assets/objects/sphere_basketball/source/original.glb `
  --output assets/objects/sphere_basketball/visual/model.glb `
  --center --target-max-dimension 0.24

# 保留复杂材质、原灯光与 World，并生成单 mesh、纹理打包的场景
blender --background --factory-startup --python scripts/prepare_visual_asset.py -- `
  --source assets/environments/basketball_court/source/室内篮球场blend.blend `
  --output assets/environments/basketball_court/visual/scene.blend `
  --object-name environment

# 为非基础几何对象生成低面数凸包碰撞体
blender --background --factory-startup --python scripts/generate_collision_mesh.py -- `
  --source assets/objects/food_lime/visual/model.glb `
  --output assets/objects/food_lime/collision/model.obj `
  --urdf-output assets/objects/food_lime/collision/model.urdf `
  --target-faces 512
```

`--target-max-dimension` 的单位是米。不得覆盖 `source/` 原文件。源许可证未知时可以进行
本地验证，但必须标记 `license: UNKNOWN`，不得分发或上传该大文件。

## 碰撞约定

- `sphere` 使用球体 primitive；`cylinder`、`cube`、`cone` 使用对应 primitive；
- 其他类别必须提供 `collision/model.obj` 等低面数 mesh，并使用 `mesh` 或
  `convex_hull` collision；该规则由 AssetManager 校验；
- 碰撞 mesh 必须从已经完成米制缩放、居中和变换烘焙的 visual 生成，保持相同原点、
  朝向和尺度；
- 动态刚体优先使用封闭凸包；凹形物体应拆成多个凸部件或使用 compound URDF；
- 常规非基础几何对象的默认上限为 512 个三角面；需要保留曲面的 compound 或静态 surface
  collision 可提高到 1024/2048 面，但必须在 manifest/map 中记录实际值和上限；
- 空心容器不能使用会封住内部空间的单一 convex hull。咖啡杯采用分段杯壁、独立杯底和
  分段把手组成的 compound URDF，杯腔与把手孔保持为空；
- manifest 需要记录碰撞 mesh 的 SHA256、顶点/三角面数、`bounding_radius` 和
  `support_height`；
- 带把手等突出部件时可额外记录 `footprint_radius`，用于表面边界留量；它不得大于
  `bounding_radius`。`support_height` 仍独立用于落地高度和滚动角速度尺度；
- `support_height` 和 `footprint_radius` 必须按 manifest 的初始姿态计算，而不是无条件采用
  未旋转模型的 Z 半高；例如青柠短轴转到世界 Z 后，支撑高度约为短轴半径；
- 不得直接把高面数渲染 mesh 交给 PyBullet；
- `special` 通常需要多刚体/约束，但每个刚体仍应使用低面数碰撞 mesh；
- 平整矩形地面可使用贴合厚度的 box proxy；异形/曲面区域使用从原模型部件提取的静态 mesh。
  未登记为当前 surface collision 的墙体和家具仍可能只是视觉几何。

## 当前正式资产

- Objects：`sphere_baseball`、`sphere_basketball`、`sphere_football`、`sphere_volleyball`、
  `food_apple`、`food_lime`、`food_lychee`、`special_coffee_cup`；
- Environments：`classroom`、`basketball_court`、`street`。

其中用户提供的篮球、足球和室内篮球场尚缺来源 URL、作者和许可证，只允许本地使用。
