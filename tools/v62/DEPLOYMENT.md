# V6.2 服务器执行与接续

本地根：`D:\workspace\project1_database`。服务器根：`/data/raw/huzijian/project1_database`。仅在以上工作区工作，禁止删除、覆盖旧成果或修改其他任务；淘汰内容只能移到对应工作区 `remove`，实质删除由用户做。

## 环境

- 两台服务器：`wangzile@172.16.30.11`、`chenliang@172.16.30.12`。不在文档/脚本/Git 中记录密码；仅注入当前 SSH 客户端进程。
- 轻量本地 SSH 客户端：`D:\workspace\project1_database\tools\v62\remote_ops.py`。SFTP 路径限制、主机公钥指纹固定、拒绝覆盖、所有远端程序由项目内 tmux 启动。
- CPU Python：`/data/raw/huzijian/project1_database/tools/conda_env/bin/python`。不要安装/更新共享环境，也不要使用账户默认 Conda。
- Blender：`/data/raw/huzijian/project1_database/tools/runtime/blender-4.2.23-linux-x64/blender`。独立加载器位于 `/data/raw/huzijian/project1_database/tools/runtime/v62_compat_debian231_r2/lib/ld-linux-x86-64.so.2`。其包和 SHA256 见项目内 manifest；不要替换系统库。
- Blender 自带 Python、资源、缓存均显式绑定项目内路径；不要把 Conda 的 Python 解释器硬塞给 Blender。
- **后续使用** `/data/raw/huzijian/project1_database/tools/v62/blender42_scoped.sh`；对应本地 `D:\workspace\project1_database\tools\v62\blender42.sh`。它比已运行的旧 `blender42.sh` 额外显式指定 CUDA/OptiX/OpenGL/Mesa 专项缓存。前期脚本只显式指定 TMP/XDG/Blender 缓存，未单独核验驱动默认缓存位置；不能宣称那部分已完成目录审计，也不应去工作区外查找或清理。
- 原场景 Blender 4.0.36 文件已在此 4.2.23 环境成功打开、审计和实际渲染。不要再回退 3.4.1：该版本打开原源文件已实测崩溃。

## 账号、权限与设备

第二账号可读 `.blend`，但不能读部分原 GSO 文件、不能写 wangzile 新建的日志子目录。已用第一账号建立 **33 个输入文件副本**，位于 `/data/raw/huzijian/project1_database/tmp/v62_shared_inputs/models/`；只给新副本普通读取权限，未修改原素材权限。清单在其父目录 `manifest.json`。

第二账号计算输出：`/data/raw/huzijian/project1_database/tmp/v62_node12/`。原输出保留，归档脚本将指定成果复制到 `/data/raw/huzijian/project1_database/outcomes/v62/radio_mixed_domino/20261005_pilot4/`，逐文件核验哈希。

渲染前用 `/data/raw/huzijian/project1_database/tools/v62/check_idle_node.py` 做两次 GPU 查询。EEVEE/EGL 未证明受 CUDA 掩码控制，因此本轮只在**整台 GPU 均空闲**的第二节点启动，Cycles 绑定 UUID `GPU-76330662-90bb-222e-1f50-1808f9771d73`。不要把曾经空闲当成下次仍可用。第一节点其他人的 GPU 0/1/3 不可使用；本轮机制小样仅 CPU。

tmux 1.8 不支持 `new-session -c`。工作脚本内部必须先进入项目绝对路径。使用项目配置 `/data/raw/huzijian/project1_database/tools/v62/tmux.conf` 和独立 socket：

- `/data/raw/huzijian/project1_database/tmp/v62_node11_control.sock`
- `/data/raw/huzijian/project1_database/tmp/v62_node12_control.sock`

不要遍历或中断其他 tmux 会话；旧失败会话与日志保留。复制 launcher 后使用新会话名、新日志、新输出目录。禁止重跑会写到旧成果目录的原 launcher。

## 代码版本对应

本地当前 `pilot_render.py` 对应服务器 **`pilot_render_r4.py`**；本地当前 `mechanism_probe.py` 对应服务器 **`mechanism_probe_r3.py`**。历史名称保留，不覆盖部署，避免已运行进程读取变化的代码。

服务器仅有的中间版本已下载到本地 `D:\workspace\project1_database\tools\v62\server_history\`，包括初次错误、权限修复、支撑位置修复、相机/轴向修复和三轮机制小样。其 `manifest.json` 记录远端路径与 SHA256；失败版本是记录，不是推荐执行入口。

本地与 GitHub 的 Git 提交只包含本轮计划、代码、小型审计报告，不含密码、运行时、大模型或视频。服务器工作区根原先没有 `.git`，不要在那里强行 init/pull；代码另放到独立 Git 检出 `/data/raw/huzijian/project1_database/code_snapshots/v62_20261005/`，通过本地 Git bundle 传递同一提交。对应提交与是否克隆成功以执行状态/`code_snapshot.log` 为准。

## 当前停止点

详见 `D:\workspace\project1_database\log\V6.2_execution\STATUS.md` 和主计划。试拍只是局部视觉小样，不是完整 G1；机制 probe 的 `candidate_not_acceptance` **不是物理 PASS**。先完成共模、完整原生障碍物、接触门禁、整条长链及八图 G1，再等待用户确认。禁止擅自启动运镜视频或完整视频。
