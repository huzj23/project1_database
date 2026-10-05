# V6.3 复现与续接说明

唯一数据根：本地 `D:\workspace\project1_database\`；服务器 `/data/raw/huzijian/project1_database/`。

所有重计算在服务器项目环境、项目 tmux socket 中执行。本地只进行编辑、Git、SSH/SFTP 和审图。不得在源码里写密码；SSH 口令仅由当前客户端进程临时读取后清除。不得访问其他项目或用户目录。系统程序仅用于正常执行和资源元数据查询。

## 1. 已冻结的输入链

- 原场景：`/data/raw/huzijian/project1_database/models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend`
- 棒球原始来源：`/data/raw/huzijian/project1_database/models/asset_recovery/v63/sphere_baseball/20261006_original4k/`
- 自有 GSO 输入副本：`/data/raw/huzijian/project1_database/tmp/v63_shared_inputs/models/gso/`
- 共同形状与原图表面库：`/data/raw/huzijian/project1_database/tmp/v63_node11/common_assets_r1/`
- 原生静态碰撞：`/data/raw/huzijian/project1_database/tmp/v63_node11/survey_r1/`
- 当前静置通过布局：`/data/raw/huzijian/project1_database/tmp/v63_node11/layout_r6/layout.json`
- 桌面局部机制：`/data/raw/huzijian/project1_database/tmp/v63_node11/baseball_probe_r3/`
- 有限首块输入接力诊断：`/data/raw/huzijian/project1_database/tmp/v63_node11/relay_probe_r2/`

路径中 `tmp` 不等于可删除：这些都是此次工程依赖和证据。任何退出使用的文件只能按用户要求移入项目 remove，且先检查引用并记录迁移；本轮没有删除或搬走这些文件。

## 2. 运行环境与有效设备路径

CPU Python：`/data/raw/huzijian/project1_database/tools/conda_env/bin/python`。

Blender 4.2.23：项目内 `tools/runtime/blender-4.2.23-linux-x64/`；通过 `/data/raw/huzijian/project1_database/tools/v62/blender42_scoped.sh` 启动，所有临时、用户配置和缓存重定向到本次项目 scratch。不要退回打不开原场景的 Blender 3.4。

软件 OpenGL：`/data/raw/huzijian/project1_database/tools/v63/blender42_cpu_gl_r3.sh`；项目内 Mesa 22.3.6 / LLVM 15 / glibc 2.36 支持 llvmpipe，未安装或替换系统库。小场景通过，但完整 Fog 首帧过慢，不作为本批静态图的推荐路径。

本批推荐实际路径是 **Cycles CPU + 原生 EEVEE Fog 单卡 GPU**。不能把 CUDA_VISIBLE_DEVICES 当作 EGL 的隔离保证：

1. 预检两次目标卡的 UUID、显存、利用率及包含图形进程的进程表；存在其他任务则拒绝启动。
2. 进程内 EGL 适配层只为目标 UUID 创建 platform-device display，不修改系统驱动或全局设置。
3. EGL 设备关联查询时不设置 CUDA_VISIBLE_DEVICES，避免 CUDA 序号重映射歧义；Cycles 强制 CPU，禁止枚举并启用全部 CUDA 卡。
4. 在微型场景建立上下文后，使用 nvidia-smi 的实际进程→GPU UUID 读回检查，必须只有预检的目标 UUID。不能只采信渲染器打印的“预期 GPU”。
5. 每帧前后复查；目标卡出现其他进程或设备不匹配立即停止后续帧，保留已有文件。

首个 CUDA+EGL 组合小测试失败（CUDA context 报错），且没有完整的实际设备读回，**不是隔离通过证据，禁止复用 r1 组合路径**。有效证据是 `/data/raw/huzijian/project1_database/tmp/v63_node12/gpu_scope_probe_r2/verified_device.json`；其中 EGL 实际上下文只在 `GPU-665e9626-9862-7424-fc4a-dc90d61079fa`。这个 UUID 是本次占用快照，不是未来永久可用的预留卡。

适配层依据：[Khronos EGL_NV_device_cuda](https://registry.khronos.org/EGL/extensions/NV/EGL_NV_device_cuda.txt)、[EGL_EXT_platform_device](https://registry.khronos.org/EGL/extensions/EXT/EGL_EXT_platform_device.txt)。必须保留实际设备读回测试，不可仅凭扩展文档推断隔离成功。

## 3. tmux 与版本化运行

两个控制 socket：

- `/data/raw/huzijian/project1_database/tmp/v63_node11_control.sock`
- `/data/raw/huzijian/project1_database/tmp/v63_node12_control.sock`

本地 SSH 工具：`D:\workspace\project1_database\tools\v62\remote_ops.py`。只允许项目内路径，拒绝覆盖上传/下载目标，验证已有 SSH 主机指纹；远端运行一律通过绝对路径 tmux launcher。

**已保存的 launcher 是历史运行实例，不是可直接重跑覆盖的通用入口。** 重跑前复制为新修订，分配新的输出/scratch/日志名，检查绝对路径，再提交 Git。`exist_ok=False`/独占创建是保护措施，失败时不要删除旧目录来绕开。

服务器只停过自己经命令行与输出目录双重核验的三个软件渲染进程，没有杀其他任务，没有删除文件；记录在各节点 `tmp/v63_nodeXX/stopped_cpu_renders_r1.json`。

## 4. 代码与证据

源代码基线提交：`b526375`，已推送 `https://github.com/huzj23/project1_database`。

服务器新增/历史脚本已备份到 `D:\workspace\project1_database\tools\v63\server_history\20261006_r1\`，共 77 份；逐文件 SHA256 见同目录 BACKUP_MANIFEST.json。历史脚本包括失败分支，不意味着都可作为当前入口。

共同几何的 NPZ 与 Blender 库逐顶点/三角拓扑哈希一致；这并不独自证明求解器 margin、所有子帧穿透、惯量或全链响应已合格。详见 STATUS 和主计划。不要把 `composition_report` 中的静态网格一致性升级为全物理 PASS。

本地 dirty worktree 中的 V5.6/V5.7 等其他修改均保留；不要对整个仓库 reset/clean。大模型、运行时、视频和凭据不提交 Git。
