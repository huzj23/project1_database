# 02：多物体数据契约与代码改造边界

前置：01 的安全接管。此文定义拟新增接口，不声称这些类/文件现在存在。实施前读主工程 `AGENTS.md`、`assets/README.md`、`docs/REFERENCE_PROJECTS.md`。代码根为本地 `D:\workspace\project1_database\code\physics-video-sim\physics-video-sim-main\`，服务器对应 `/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/`。

## 1. 真实代码入口

| 已有文件/接口 | 目前边界 | 本轮应做的最小扩展 |
|---|---|---|
| `src/physim/assets/__init__.py`：AssetManager、AssetSpec | 单资产解析 | 解析多个已注册资产；实例 ID 与资产 ID 分离 |
| `src/physim/maps/__init__.py`：MapManager、MapSpec、SurfaceSpec | 单支撑 surface 与环境 | 增加局部静态碰撞集合、动态场景道具和禁入区引用 |
| `src/physim/scenarios/__init__.py`：ScenarioSample、create_scenario | 一个 actor；转盘 support 特例 | 新增通用多刚体 sample 协议，旧接口保留 |
| `src/physim/physics/__init__.py`：BodyState、SimulationResult | trajectory + support_trajectory | 新增按 instance_id 索引的结果；不要把 N 个物体塞入 support 字段 |
| `src/physim/physics/pybullet_backend.py`：PyBulletBackend | PhyCo/Kubric 单actor路径与驱动转盘 | 新增普通 N 刚体步进路径，复用同一资产/碰撞解析 |
| `src/physim/validation/__init__.py` | 单主体运动验证 | 增加接触传播、禁入、静置和反事实验证 |
| `src/physim/camera/__init__.py` | 单轨迹构图 | 合并所有物体扫掠包围盒与关键事件，增加遮挡检查 |
| `src/physim/render/blender_backend.py` | 单actor回放；会清旧帧 | 安全输出目录、多对象回放、作者场景动态部件映射 |
| `src/physim/pipeline.py`、`src/physim/io/__init__.py` | 现有流水线/保存 | 接受多体结果，保存完整证据，保持旧任务兼容 |

新增场景建议名 `rigid_interaction`、`domino_chain`。可以新增 `physics/multibody.py`、`scenarios/interaction.py`、`scenarios/domino.py` 等项目侧模块，实际路径记录进交接。不得每个场景复制一份求解器/渲染器；不得修改 `third_party`。主工程文档中“环境合成一个 mesh”的旧规则须作明确扩展：静态环境可以保持整体，参与运动的道具必须独立，采用可复用场景适配策略，并在工程文档记录原因。

`tools/v5_simulate_rigid_objects.py` 与 `tools/v5_render_rigid_video.py` 仅作演示参考；它们的硬编码和默认相机不作为新实现基线。多物体物理使用现有 PhyCo/Kubric PyBullet 客户端；如包装层无法导出全部子步接触，可在项目 backend 内调用其原生 client，并记录边界，不能另建不受统一契约管理的求解流程。

## 2. 单位和坐标

统一米、秒、千克、牛顿；Z 向上；重力 `[0,0,-9.81]`。源 `.blend` 中数值不能在未验证 `unit_settings.scale_length`、世界变换和已知尺寸前直接当米。

物体归一化指转成真实米制、确定原点与轴向，不是所有物体缩为单位立方体。场景与物体不得各自独立居中后丢失相对位置。保存 `source_to_world_4x4`、`visual_to_body_4x4`、`collision_to_body_4x4`、质心/惯性坐标和原场景对象绑定。

数学约定：列向量；`T_WV = T_WB * T_BV`。B 是约定的物理刚体参考系，V 是视觉局部系。PyBullet/URDF 的 base pose 和 inertial frame 语义必须通过偏心测试核实，然后显式转换成 B；不能假设视觉原点、URDF link 原点和质心相同。矩阵落盘约定为行列表（row-major serialization），不改变数学乘法约定。

对负尺度、镜像、父子层级、实例和旋转应用变换时保留法线、UV和材质；模型几何只烘焙一次，禁止 visual 和 collision 重复缩放。

新多体 JSON 统一字段 `quaternion_xyzw`。进入 Blender `mathutils.Quaternion` 和既有 Kubric `wxyz` 接口时显式换序。旧文件的 `quaternion` 字段不能静默改义。测试包括 identity、绕Z 90°、非零质心旋转和四元数 q/-q 等价。

## 3. 身份、时间和配置

同一真实盒模型可出现 12 次：`asset_id` 相同，`instance_id` 为 `box_001`…`box_012`，PyBullet body ID 与 Blender 对象映射必须记录。不要使用 Python 对象地址或随加载顺序变化的名称作为持久身份。

配置包含：schema_version、run_id、seed、map_id、surface_id、原始资产哈希、runtime版本、所有 bodies、所有 static_colliders、单次 trigger、期望传播顺序、求解参数、相机、验证阈值、输出策略。配置只给初始条件，不给目标逐帧轨迹。

每个 body 包含：instance_id、asset_id/原场景 object_id、role（trigger/target/passive）、质量及其依据、惯量/质心、碰撞引用、变换、初始线角速度、摩擦、恢复、阻尼。动静态由质量/求解角色决定；纯视觉物体必须在碰撞覆盖清单中明确“不可触及”。

frame 从 0 开始，`time_s = frame / video_fps`，渲染 Blender 帧号 `frame + 1`。记录状态从 t=0 开始；每步推进后记录接触：第 k 次物理步覆盖 `((k-1)dt, kdt]`，接触报告使用 `step=k`、`time_s=k*dt`。不得沿用 V5 接触日志少一个 dt 的时间算法。

默认 24 fps / 480 Hz，每视频帧 20 子步；960 Hz 为精度对照。明确给 client 设置 time step，不能只设置 Kubric step_rate。帧数 N 的视频播放时长为 N/fps，末状态采样时间为 (N-1)/fps；两者在报告中分开。

settle 为前置求解，保存持续时间和结果；正式 t=0 从 settled state 开始。目标预静置后不能每帧冻结；掉落触发物在正式初态放置，或者在预静置期间不参与该诊断世界，不能在目标接触后临时切换动态。

## 4. 输出契约

每次尝试写入全新 `outcomes/v55/<scene>/<experiment>/<run_id>/`，相同结构两侧对应。不要在这里直接写固定 `final.mp4` 覆盖历史结果。

```text
resolved_config.json          完整参数和所有绝对输入路径
provenance.json               source/runtime/code hashes、版本、license
bodies.json                   持久ID、角色、mass、COM、visual/collision绑定
trajectory.json               每个instance的逐帧状态
motion_substeps.jsonl          动态刚体各子步状态，支持接触前运动判定
contacts.jsonl                每子步全部有效接触，不限前100条
events.json                   接触episode、启动、倾倒与区间
causality.json                期望链的证据、旁路检查、对照结果
validation.json               每项pass/fail/unknown、阈值、实测值、原因
scene_delta.json              动态提取、摆放、显隐、灯光/World/材质差异
camera.json                   位姿、投影、遮挡和关键帧可见性
status.json                   running/failed/complete；退出码、时间、日志
commands.txt                  可复现的绝对路径命令，无密码
previews/                     起点/首次接触/中段/终点图
frames/                       无损帧，保留
video.mp4                     后续渲染成片
replay.blend                  回放工程或明确绑定轨迹的自包含工程
```

轨迹每行至少包含 instance_id/frame/time_s/position_m/quaternion_xyzw/linear_velocity_m_s/angular_velocity_rad_s。是否压缩由体积决定，须提供读回入口，不能丢子步因果证据。

接触每行包含 step/time_s、两个 instance_id/link_id、双方接触点、normal_on_b、signed_distance_m、normal_force_n、两切向力和方向。原始 contact A/B 顺序不能当作因果方向。`impulse_proxy_n_s = Σ F_normal * dt` 是离散估计，字段名和报告注明估计；不能把峰值力直接叫冲量。

接触 episode 聚合相同 body pair 的相邻子步，可容忍一个空子步但记录规则；保留全部原始子步，支持复核。静态支撑接触和动态传播接触分开，地面接触不能被算成链条传递。

## 5. 接口关口和兼容性

至少验证：schema读写往返；多实例同资产；非法重复ID拒绝；四元数/质心对齐；时间单调与0/末帧一致；失败的 physics validation 阻止渲染；旧 `SimulationResult` 和所有已注册场景仍可载入；无触发/断链实验只改声明的配置。

执行者先写 `log/V5.5_execution/contract_decisions.md`，记录实际新模块路径、明确 quaternion/frame/time 定义、一个小型真实样例记录，再进入资产和求解实施。契约变更必须版本化并更新消费者，禁止靠猜测字段兼容。
