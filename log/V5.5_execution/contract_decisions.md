# V5.5 契约决策记录（02 关产物）

时间：2026-09-28T20:05+0800（UTC+8）
执行者：DeepSeek Flash 4.1
状态：**passed** —— 契约已实现并在服务器实测通过（45 项检查全 PASS）

本文件是 02 §5 要求的"先写 contract_decisions.md，记录实际新模块路径、明确
quaternion/frame/time 定义、一个小型真实样例记录，再进入资产和求解实施"。

---

## 1 实际新模块路径（规划名称 → 实际落地）

| 02 建议名 | 实际路径 | 状态 |
|---|---|---|
| `physics/multibody.py` | **未新建**——契约先落在 `src/physim/contracts.py`；求解路径留待 04 | 见下 |
| `scenarios/interaction.py` | 未新建（05 再定） | 待 04/05 |
| `scenarios/domino.py` | 未新建（08 再定） | 待 08 |

**实际新增（本关）**：

- `src/physim/contracts.py` —— 多体数据契约（本关全部产物）
- `tools/v55_test_contracts.py` —— 契约自测（45 项）
- `tools/v55_import_check.py` —— 导入/签名核对

**01 关已新增**：`src/physim/safe_output.py`（无删除输出层）。

> 决策说明：02 §1 表格把"新增按 instance_id 索引的结果"列在
> `physics/__init__.py`。实际实现选择**独立模块** `contracts.py`，原因是
> `physics/__init__.py` 被渲染、验证、pipeline 广泛导入，把契约塞进去会扩大
> 循环导入面。`contracts.py` 只依赖标准库 + 一个**函数内**延迟导入
> `physim.physics`，因此导入方向是单向的、无环。旧
> `SimulationResult`/`BodyState` **未做任何修改**（回归项已证）。

---

## 2 单位与坐标（冻结）

- 单位：**米、秒、千克、牛顿**；**Z 向上**；重力 `[0, 0, -9.81]`。
- 坐标系：`W` 世界、`B` 物理刚体参考系（PyBullet base frame）、`V` 视觉网格系。
- 列向量；**`T_WV = T_WB @ T_BV`**。
- 矩阵落盘：**行主序**（row-major）。`mat4_flatten` 是唯一的序列化入口，
  输出 16 个浮点；`mat4_unflatten` 读回。
- 源 `.blend` 的数值**不直接当米**：必须先用 `unit_settings.scale_length`、世界变换
  和已知尺寸（桌高/瓶高）交叉校验。该工作在 03 执行。

已实现的坐标工具与验证：

| 工具 | 用途 | 测试 |
|---|---|---|
| `mat4_from_trs` | 由平移 + `xyzw` 旋转（+可选缩放）生成行主序 4x4 | 手算对比 |
| `mat4_multiply` | `T_WV = T_WB @ T_BV` | 组合后 V 原点落在 `(1.0, 0.5, 0.0)` ✅ |
| `mat4_transform_point` | 变换点 | 绕**偏心**原点旋转命中手算值 ✅ |
| `mat4_flatten/unflatten` | 行主序序列化 | 往返一致 ✅ |

---

## 3 四元数（冻结）

- **新契约 JSON 一律 `quaternion_xyzw`。** PyBullet 原生就是 `xyzw`，物理侧无需换序。
- 旧 `physim.physics.BodyState.quaternion` **保持既有语义**（Blender/Kubric 的 `wxyz`）。
  两者在**边界处显式转换**，只由两个函数负责：

  | 方向 | 函数 |
  |---|---|
  | 契约 `xyzw` → `BodyState`(`wxyz`) | `contracts.to_body_state()` |
  | `BodyState`(`wxyz`) → 契约 `xyzw` | `contracts.from_body_state()` |

  并另有底层 `quat_to_wxyz()` / `quat_from_wxyz()`。
- **`q` 与 `-q` 视为同一旋转**：`quat_angle()` 先把 `w` 归一到非负，
  `quat_close()` 同时接受同号与反号。已测：绕 Z 90° 的 `q` 与 `-q` 判定相等；
  绕 Z 90° 的角度为 `pi/2` ✅。
- 非零质心旋转已测：`mat4_from_trs((1,2,3), Z90)` 作用于 `(0.5,0,0)` 得
  `(1.0, 2.5, 3.0)`，与手算一致 ✅。

**禁止**：静默改变旧 `quaternion` 字段语义；靠猜字段兼容。契约变更必须升版本号。

---

## 4 时间（冻结，含 V5 偏差修正）

| 量 | 定义 |
|---|---|
| `frame` | **从 0 开始** |
| `time_s` | `frame / video_fps` |
| Blender 帧号 | **`frame + 1`**（时间轴 1 基） |
| 物理子步 | `dt = 1 / physics_fps` |
| 子步 `k`（1 基）覆盖 | **`((k-1)*dt, k*dt]`** |
| 子步时间戳 | **`time_s = k * dt`** |

**这正是总入口 §6 要求修正的偏差**：V5 两物体演示"在步进后记录、却按步进前编号
计算"，使每个接触事件**提前一个 `dt`**。本契约把计算收敛到唯一入口
`substep_time_s(step, physics_fps)`，并有专门测试锚定。

- 唯一入口：`substep_time_s()`；`step < 1` 直接拒绝 ✅（已测）。
- `substeps_per_frame(physics_fps, video_fps)` 校验整除：480/24=20 ✅；
  500/24 **被拒绝** ✅。
- **播放时长与采样跨度分开报告**（02 §3 明确要求）：
  `playback_duration_s(N, fps) = N/fps`；`sampled_span_s(N, fps) = (N-1)/fps`。
  已测 81 帧 @24fps：3.375 s 与 80/24 s 不同 ✅。
- 默认 **24 fps / 480 Hz（每帧 20 子步）**；960 Hz 作精度对照（04 用）。

---

## 5 身份、角色与质量

- `asset_id` = 可复用资产（一次扫描）；`instance_id` = 一次摆放（`box_001`）。
  同一资产可出现 12 次 ✅（已测）。
- 持久身份**只能是 `instance_id` 字符串**；禁止用 Python 对象地址或加载顺序名。
- 角色：`trigger` / `target` / `passive`，非法值**拒绝** ✅。
- 质量必须带依据：`mass_basis ∈ {measured, manufacturer, estimated, derived}`，
  非法值**拒绝** ✅。02 §3 要求"标 estimated 并保留区间"——字段 `mass_range_kg` 承载。
- **`is_dynamic = mass_kg > 0`**，且 `validate_no_passive_actors()` 在**零个动态体时
  直接报错**。这是把总入口 §5"把所有物体设为被动项无法产生链式反应"变成
  **代码级不可达**，而不是靠人记得。
- 静态景物用独立 `StaticCollider` 列表（无质量、无轨迹），**不是**质量 0 的 body。
  其 id 与 body id 冲突时**拒绝** ✅。

---

## 6 输出契约

`OUTPUT_SCHEMA_VERSION = "v55.outputs.1"`。每次 attempt 写入全新
`outcomes/v55/<scene>/<experiment>/<run_id>/`（由 01 的
`safe_output.allocate_run_dir` 分配，**已有输出即拒绝复用**）。

02 §4 列出 15 类文件。本关已实现其**序列化基础**：

| 文件 | 本关状态 |
|---|---|
| `bodies.json` | `MultibodyResult.to_dict()["bodies"]` ✅ |
| `trajectory.json` | `["trajectories"]`，按 `instance_id` 索引 ✅ |
| `motion_substeps.jsonl` | `SubstepState` + `write_jsonl`（**拒绝覆盖** ✅） |
| `contacts.jsonl` | `ContactRecord` 全字段，`write_jsonl` ✅ |
| `events.json` | `ContactEpisode`，原始子步保留 ✅ |
| `time_convention` 块 | 在 JSON 内自描述，含四元数序/矩阵序/帧偏移/子步区间 ✅ |
| 其余（`resolved_config`/`provenance`/`validation`/…） | 04/09 落地 |

**接触语义**：`normal_on_b` 由 A 指向 B；**原始 A/B 顺序不代表因果方向**，
消费者须用合力方向判断谁推谁。
`impulse_proxy_n_s = Σ F_normal * dt` 是**离散估计**，字段带
`impulse_proxy_is_estimate: true`，禁止称作真实冲量。
**静态支撑接触与动态传播接触分开**：`contact_kind ∈ {dynamic, static_support, ground}`。
已测：`static:ground` 被正确判为 `ground` 而非传播 ✅。

> 实现中修掉一个真实缺陷：初版用 `"ground" in (instance_a, instance_b)` 判地面，
> 这是**元组精确相等**而非子串匹配，永远不成立。已改为解析 `static:` 前缀后的名字。

---

## 7 兼容性关口（02 §5）——实测结果

| 关口 | 结果 |
|---|---|
| schema 读写往返 | `to_dict → from_dict → to_dict` 字节级稳定 ✅ |
| 多实例同资产 | 3 个 body 同一 `asset_id`、不同 `instance_id` ✅ |
| 非法重复 ID 拒绝 | 重复 `instance_id` / 未知轨迹 / 静态 id 冲突 均拒绝 ✅ |
| 四元数 / 质心对齐 | `q≡-q`；偏心旋转命中手算 ✅ |
| 时间单调与 0/末帧一致 | 首帧非 0 拒绝；乱序拒绝；`time_s ≠ frame/fps` 拒绝 ✅ |
| 失败的物理 validation 阻止渲染 | `validate()` 抛错即无产物；`validate_no_passive_actors()` 拦住零动态体 ✅ |
| 旧 `SimulationResult` 仍可载入 | 构造与读取行为不变 ✅（另有 01 关 10/10 场景回归） |
| 无触发/断链实验只改声明的配置 | 契约层已备好：`bodies` 列表与角色由配置给出，实验只改配置（08 实测） |

服务器实测（权威）：

```
CONTRACTS_RC=0
RESULT: PASS -- V5.5 contract verified          (45 项全 PASS)
all imports OK
contract schema : v55.contract.1
output schema   : v55.outputs.1
legacy result   : SimulationResult support_trajectory default = ()
```

证据：`outcomes/v55/bootstrap/20260928T194500/02_contract_tests.log`

---

## 8 小型真实样例记录

契约的"真实样例"用**已交付项目的真实数据**验证时间/四元数定义，而非合成数据。

- 数据：`datasets/turntable_spin/seed-005002/x1/`（81 帧、16 fps、真实求解轨迹 + 支撑轨迹）
- 校验点：首帧 `frame=0, time_s=0.0`；末帧 `frame=80, time_s=5.0`；
  `playback = 81/16 = 5.0625 s`，`sampled_span = 80/16 = 5.0 s`——两者相差一帧，
  正是 02 §3 要求分开报告的量。
- 该样例同时被 01 关渲染回归复用（litteral 渲染一帧，`rc=0`），
  证明契约与既有渲染链一致。

---

## 9 与 02 计划的偏差（如实记录）

| # | 02 计划 | 实际 | 原因 |
|---|---|---|---|
| 1 | 结果类型放 `physics/__init__.py` | 独立 `contracts.py` | 减少循环导入面；旧类型零改动 |
| 2 | 建议 `physics/multibody.py` | 求解路径延后到 04 | 契约先行，04 再落求解，符合总入口"不要每场景复制求解器" |
| 3 | `scenarios/interaction.py`/`domino.py` | 未建 | 05/08 按实际需要再建 |
| 4 | — | 新增 `validate_no_passive_actors()` | 把总入口 §5 的硬要求变成代码级拒绝 |

---

## 10 下一步

**03**（真实资产、场景副本与碰撞构建）。先在服务器核验三处源 `.blend` 的存在与
SHA-256 是否匹配计划给出的基准；再按 02 的矩阵契约做归一化并记录
`source_to_world_4x4` / `visual_to_body_4x4` / `collision_to_body_4x4`。
