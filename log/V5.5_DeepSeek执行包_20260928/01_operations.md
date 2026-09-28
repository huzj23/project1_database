# 01：接管、边界、无删除运行和备份

前置：读 [总入口](../V5.5_DeepSeek执行总入口_真实场景多米诺链_20260928.md)。本关不跑物理或渲染；先使后续作业可安全恢复。输出记录放 `log/V5.5_execution/`，大报告放 `outcomes/v55/bootstrap/<run_id>/`。

## 1. 接管状态

规划时 Git 基线为 `13cb95a`，远端为 `https://github.com/huzj23/project1_database.git`。执行时读取实际 HEAD/远端，不重置到此哈希。保留用户未提交修改；按文件审查后提交自己负责的变更，不执行整树覆盖同步。

服务器连接曾超时，用户后来说明已恢复；最后一次脚本上传被中断，不能推断上传成功或目录已创建。先核验 `/data/raw/huzijian/project1_database/tools/v54_init_remove.sh` 的存在和哈希、已有项目 tmux 会话及目录，再决定补传或执行。若目标同名脚本存在且内容不同，上传为唯一新名字。

本地 `remove` 已确认存在。服务器 `remove` 未获成功证据。只在指定目录下创建，使用 tmux 作业执行 `mkdir -p` 和 `stat`；创建成功后将日志同步到本地。

## 2. 凭据和路径

既有辅助工具为 `D:\workspace\project1_database\tools\ssh_ctl.py`，账户 `wangzile`，主机信息从该工具读取，不在计划外猜测。用户授权本任务读取 `D:\workspace\project1_database\log\key.txt` 的对应密码，只在当前 SSH 客户端进程内使用。

检查凭据文件格式时不打印内容。通过子进程专属环境或当前 SSH 程序内存注入密码，结束后释放；不写入脚本、参数、日志、全局环境、tmux 环境或 Git。不要假定文件全部内容一定就是单个密码，使用已有成功解析方式。

所有本地和远程资产路径须 resolve 后落在指定根目录内；遇到符号链接、junction、外链 `.blend` 库、贴图或 URDF 路径也要解析最终目标。工作区内链接指向工作区外不算合法。系统 `tmux`、shell 等基础工具只用作执行器，不借用其他人的 Python/Conda、Blender、模型、缓存；Python/Blender 项目依赖使用工作区中的运行时。

Windows 不保证有原生 tmux。服务器计算必须通过 tmux；本地编辑/传输是控制面操作。Hidden Alley 若需本地渲染，先检查是否已有可合法使用的本地 tmux 环境。没有时单独报告这一执行方式冲突；不要悄悄把“所有计算用 tmux”改成直接本地后台运行，也不要因此阻断可在服务器完成的阶段。

## 3. tmux 运行规范

建议新建项目专用 tmux socket，绝对路径如 `/data/raw/huzijian/project1_database/tmp/tmux_v55.sock`，避免默认 socket 和其他人的会话/临时目录。项目 session 统一 `p1_v55_<stage>_<run_id>`。不要 `kill-server`、批量 kill 或操作非本任务会话。

先创建并核验 `tmp`、`remove`、`outcomes/v55`。固定启动脚本由本地编写/检查后上传；SSH 仅运行短的 tmux 命令，避免 PowerShell 多层引号。启动器记录：绝对脚本路径、哈希、cwd、session、socket、PID、开始时间、日志、退出码；作业结束写 `status.json`。看见 `tmux new-session` 成功只表示已启动，不能宣布计算完成。

模板中的脚本和参数由执行者先实现、检查，再调用；不要复制不存在的 CLI。形态如下，`RUN_ID` 由执行者替换为已确认的唯一目录名：

```text
/usr/bin/tmux -S /data/raw/huzijian/project1_database/tmp/tmux_v55.sock new-session -d -s p1_v55_bootstrap_RUN_ID -c /data/raw/huzijian/project1_database /usr/bin/bash /data/raw/huzijian/project1_database/tools/v55_bootstrap_RUN_ID.sh
```

远程诊断命令也放进本任务 tmux 的脚本，结果写工作区再 SFTP 读取。tmux 启动/查任务状态本身是控制命令。禁止直接交互式 SSH 长时间占用前台跑渲染。

## 4. 环境和资源检查

历史环境脚本 `tools/server_env.sh` 有 `CUDA_VISIBLE_DEVICES` 的默认 GPU 0 赋值，也会尝试复制工作区外的证书。新任务不要无审查直接 source。为 V55 编写项目侧最小环境包装：只保留核验过的项目 runtime/lib/ca 配置，显式最后设置 `CUDA_VISIBLE_DEVICES=""`、`KUBRIC_USE_GPU=false`、各数值库线程上限 8、Blender `--threads 8`，渲染器设备 `CPU`。

TEMP/TMP/TMPDIR、Blender 用户配置/脚本、XDG cache、Python cache 和工具缓存都指定到本次工作区内目录；禁用会自动清理文件的临时目录封装。选择 Python 时注意主工程要求 Python 3.10，而本地系统控制用 Python 3.9 不能当成主工程运行时。

通过 tmux 只读查询 GPU 利用率/显存/进程、CPU、可用内存、磁盘和已有本任务作业。记录 GPU ID 不打印他人进程完整命令或访问其文件。V55 默认 CPU，无需等 GPU；若未来改 GPU，必须确认分配权和渲染进程实际设备，不能把一次空闲快照当作独占承诺。

重型任务初始并发为 1，单任务最多 8 线程。单帧测试后估计全片时间、峰值内存和磁盘（保留至少估算输出两倍空间及 10 GiB 余量）。磁盘不足时移动同盘文件到 `remove` 不能释放容量，应报告具体缺口由用户处理，不自作删除。

## 5. 首先消除自动删除路径

实际发现：`src/physim/render/blender_backend.py::purge_stale_frames` 对 PNG/EXR 调用 `f.unlink()`，`build_scene()` 会调用它。`tools/clean_run.sh`、`launch_batch.sh`、`stop_real_batch.sh`、`make_share_package.py` 等历史工具含文件删除，禁止原样复用。

在当前使用链中实现：

1. 每次运行创建独立 `run_id/attempt_id` 输出和 scratch 目录，禁止混读上一轮帧。
2. 如检测到目录已有输出，默认选择新目录或报错；不要调用旧 purge。确需清理时，经路径核验后整批移动至 `remove/<timestamp>/<原相对路径>`，不覆盖。
3. 检查实际调用到的上游 renderer、IO、打包器、测试夹具是否使用 `TemporaryDirectory`、`unlink`、`rmtree`、自动缓存淘汰。通过项目适配层禁用自动删除；未经审计不启动。
4. 修改需要的项目入口，不批量重写全部历史文件。文档中登记仍禁止使用的入口。
5. 文件移动记录 original/destination、reason、timestamp、size、hash、run_id，移动前写计划、移动后核验哈希。仅允许同工作区内不覆盖的 rename/move，不使用跨盘 copy-delete 伪装移动。

Blender 运行副本中的对象分组/显示控制与磁盘删除不同，但原文件依旧不能覆盖。优先保留原对象并隐藏归档；动态对象提取后必须避免原对象还作为静态障碍重复碰撞。

验证要求：放一个本次生成的哨兵帧文件，执行新目录分配/清理入口后旧文件必须仍在原位置或 `remove` 且哈希一致；第二次运行不复用第一次帧。测试本身也不能通过框架 teardown 删除临时目录，应使用持久化工作区 fixture。

## 6. 服务器代码与资产备份

先生成服务器指定根内文件清单（路径、大小、mtime、SHA-256），对比本地相同路径。服务器独有/不同的脚本、配置、补丁和小型碰撞资产先下载到 `D:\workspace\project1_database\tmp\v55_server_backup\<run_id>\`。不要覆盖本地改动，差异审阅后有选择地整合到 Git。

The Shed 的源 `.blend` 和依赖、所选 GSO 完整源包（visual、texture、URDF、collision）应有本地备份及哈希。无需为准备一条链一次性复制所有 138 个大模型。大资产和输出沿用 Git 忽略；源码、资产 manifest、许可证记录、紧凑证据摘要进入 Git。Git 忽略不等于已经备份，二者单独记录。

## 7. 本关通过条件

`bootstrap_report` 必须明确：两侧 remove 状态、所有路径边界、SSH 上传中断的核验结果、运行时版本、GPU/CPU策略、无删除调用链、代码差异备份、源资产待办、tmux运行证据、Git HEAD。不得空填 PASS。通过后更新 11 状态并进入 02；服务器不通时可继续本地契约/代码审查，但远端状态保持未知。
