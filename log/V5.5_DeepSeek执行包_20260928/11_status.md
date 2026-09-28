# 11：V5.5 初始状态和断点入口

登记时间：2026-09-28。本文件是计划包初始快照，不是实施报告。DeepSeek接手后按10将最新状态更新为真实记录，旧快照由Git保留。

> **2026-09-28 更新（执行者）**：01 已完成并通过，实测记录见
> `log/V5.5_execution/01_20260928T195000.md`，事件见 `log/V5.5_execution/events.jsonl`。
> 下面"已知完成"一节保留规划时的原始快照；最新事实以本更新块为准。

## 执行进度（实测，覆盖下方规划快照）

| 阶段 | 状态 | 证据 |
|---|---|---|
| 01 接管/边界/无删除/备份 | **passed** | `log/V5.5_execution/01_20260928T195000.md` |
| 02 数据契约 | **passed**（服务器 45/45 检查） | `log/V5.5_execution/02_20260928T200500.md`、`contract_decisions.md` |
| 03 资产与碰撞 | **passed**（源核验 + 尺度 + 4/4 碰撞代理） | `log/V5.5_execution/03_20260928T204500.md`、`outcomes/v55/assets/collision_proxies.json` |
| 04 多刚体求解 | not_started | 下一关 |
| 05 Italian Flat | not_started | |
| 06 Hidden Alley | not_started | |
| 07 The Shed | not_started | |
| 08 12 盒多米诺 | not_started | |
| 09 渲染交付 | not_started | |

### 02 关实测关键事实

- 新增 `src/physim/contracts.py`：单位/坐标、`xyzw` 四元数（`wxyz` 边界显式转换）、
  0 基帧与 `blender_frame = frame+1`、子步 `k` 覆盖 `((k-1)dt, k·dt]` 且报 `k·dt`
  （**修正 V5 的提前一个 dt 偏差**）、`instance_id` 身份、角色、静态碰撞体分离。
- `validate_no_passive_actors()` 把"全是被动项出不了链"变成**代码级拒绝**。
- 旧 `SimulationResult`/`BodyState` **零改动**；45 项契约检查服务器全 PASS（rc=0）。

### 03 关实测关键事实（替换原规划的"待核验"）

- **计划 §1 的 SHA-256 基准已过期**：Italian Flat 相符；Hidden Alley 实际
  `be124788…`、The Shed 实际 `fe6294a8…`。两包 `unzip -t` 均通过、解包成员长度与
  文件大小完全相等、对象计数与 V5 资产评审记录相符 → **文件正确，基准过期**。
  不覆盖、不重下（符合 03 §1）。
- **Hidden Alley 服务器不可读的根因**（由 .blend 头部字节确定，非猜测）：
  源文件由 **Blender 4.00** 写入（`BLENDER-v400REND`），服务器唯一可运行的
  **3.4.1 在 `open_mainfile` 内部段错误（rc=139）**；项目自带 4.2.23 因需
  glibc ≥2.26（宿主 2.17）**无法启动**。意大利 Flat 为 2.93、The Shed 为 3.4，均可读。
- **"另存兼容副本"路线已证伪**：Blender 不能降版写入，另存产物仍是 4.2 格式。
  半成品已**移入** `remove/v55_partial_uploads/`（移动非删除）。
- **正确架构已实测**：物理路径**从不导入 `bpy`**。服务器 pybullet 202010061
  真实求解通过（0.2 kg 盒 0.500→0.050 m 正确落定），本地 4.2.23 负责回放。
- **本地 tmux 要求已满足**：WSL 提供 **tmux 3.4**，可驱动 Windows Blender；
  两场景已在 tmux 会话内真实渲染（960×540），并经**定量**校验（std 40.1/70.7、
  254/329 色阶）。01 §21 的"本地无 tmux"冲突**不成立**。
- 四项计划候选资产尺寸**全部核实**；`Clue_Board` 实测 **0.497 m**，确认过大；
  四者 **`watertight=false`**，均需自建闭合碰撞代理。
- **待处理**：Hidden Alley `scale_length = 10.0`（另两场景 1.0），源数值不是米；
  服务器 conda 环境**无 `kubric` 模块**，04 需选定依赖路线。

### 01 关实测关键事实（替换原规划的"待核验"）

- 服务器连通：`gpu0001` / `wangzile`，conda python **3.10.18**，104 核，内存 503 GB（可用 369 GB）。
- **服务器 Blender 3.4.1 可用**，但必须先加**项目自带** `tools/runtime/lib` 到
  `LD_LIBRARY_PATH`（系统缺 `libxkbcommon.so.0`）。**未升级系统库。**
- 服务器 `remove/` 已创建并核验：`drwxrwxrwx wangzile:wangzile`，`readlink -f` 在工作区内。
- 上次中断的 `tools/v54_init_remove.sh` **确实不存在**——上传未落地。
- **无删除链路已改造完成**：`purge_stale_frames` 由 `unlink` 改为移入 `remove/`；
  新增 `src/physim/safe_output.py`。AST 审计 41 个文件：**0 处文件删除调用**。
- 真实渲染回归 **rc=0**；哨兵帧被移走且 **sha256 不变**；既有 10 个场景配置 **10/10 ok**。
- 服务器代码备份结论：主工程与本地**内容差异 0**；149 处差异**全部是 CRLF/LF**，
  vendored `phyco-sim` 两侧同一 commit `bd8a3b4eb54fa1ad008250e2033a1f8369bff6d3`。
- **服务器 tmux 是 1.8**：不支持 `-c`、不继承父环境、`new-session` 只接受**单个命令词**。
  必须使用 `tools/v55_launch.sh` 生成单文件包装脚本，不要手写多参数 `tmux new-session`。

## 已知完成

- V5.0资产清单、V5.1计划、V5.2旧视频和V5.3的84物体/4场景单帧已在log记录。
- 用户认可当前场景和素材方向，尤其Italian Flat、Hidden Alley及盒/罐/键鼠视觉；需要排除有线键鼠的软线运动。
- V5.4可行性分析已提交到Git，基线提交`13cb95a`。
- Italian Flat/Hidden Alley源已本地保存并做过无修改只读审计，审计JSON在 `outcomes/v54_feasibility/`。
- Italian Flat软家具未配置软体；两场景都没有显式刚体/布料/collision设置。
- Hidden Alley木板组三组的网格连通分量分别为6、5、6；物理拆分和初态对照尚未实施。
- 本地 `D:\workspace\project1_database\remove\`存在，Git忽略。
- 本计划包本轮仅撰写文档，不启动服务器渲染或实施仿真。

## 未确认或未开始

| 项目 | 初始状态 | DeepSeek下一动作 |
|---|---|---|
| 服务器当前连接 | 用户称已恢复，本轮未验证 | 按01核验 |
| 上次中断的脚本上传 | 可能未完成或部分完成 | 查存在与hash，不覆盖未知文件 |
| 服务器remove | 未获stat成功证据 | tmux创建并核验 |
| 无删除运行适配 | 未实施；已发现旧purge有unlink | 01优先修实际调用链 |
| 服务器独有代码备份 | V5.0/V5.2有历史备份，最新差异未知 | 01生成差异清单与隔离备份 |
| The Shed源完整本地备份/物理审计 | 尚未证实完成 | 03/07补齐 |
| 选定盒/罐碰撞代理 | 候选视觉已审查，具体物理未通过 | 03明确ID并验证 |
| 通用N刚体结果/求解/渲染 | 未实现 | 02/04 |
| Italian Flat交互 | 未实现 | 05 |
| Hidden Alley交互 | 未实现 | 06 |
| The Shed两级链 | 未实现 | 07 |
| 12盒多米诺及因果对照 | 未实现 | 08 |
| 四段最终视频/回放工程 | 未生成 | 09 |

## 当前禁止误用的历史能力

`src/physim/render/blender_backend.py` 的 `purge_stale_frames` 会删除帧，不能在未修复情况下运行；多份历史shell清理/重跑脚本含删除语句。`tools/ssh_ctl.py` 不会阻止所有工作区内删除，因此通过工具路径检查不代表符合用户规则。

`tools/v5_render_rigid_video.py` 中的48帧/16fps、高俯视相机、两资产硬编码不能作为新视频规格。转盘每子步驱动支撑的控制方式不能作为多米诺模板。

Hidden Alley本地Blender4.2的兼容路线已验证过，服务器3.4不能默认替代；本地计算如何满足tmux应按01/06在实际环境确认。所有凭据仍只用于用户授权的当前SSH进程。

> **2026-09-28 执行者更新（03 关）**：上述"本地计算如何满足 tmux"**已解决**——
> WSL 提供 tmux 3.4，已在 tmux 会话内完成真实渲染。服务器 3.4 **确认不能**读 Hidden Alley
> （4.0 文件，段错误），已改用 06 §4 的"服务器求解 + 本地 4.2 回放"分离架构，两侧均实测通过。

## 第一次接手的具体下一步

读取总入口、01、02、09；执行01的只读接管和安全运行改造；输出第一份 `log/V5.5_execution/01_<timestamp>.md`。只有取得实际证据才修改本状态表。无需让用户再复述场景、物体和最终目标。
