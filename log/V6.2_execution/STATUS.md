# V6.2 执行状态

日期：2026-10-05。状态：`STAGE1_ENV_RUNNING`。只获准推进新版静态图阶段，尚未产生新布景图，不进入运镜/完整视频。

## 已完成

- 阅读 V6.1 实際评审包及渲染脚本，检查 8 张联系图、3 张用户点名单体图。
- 编制 V6.2 计划：球→原生收音机→唯一落体；地面加入胶带环、LEGO 厚包装与 Paper Mario 小盒。
- 确认旧渲染脚本未同步主场景/Fog 的新相机与投影，存在可见重影，要求修复而非关闭雾效。
- 两台 SSH 已成功；指定共享工作区可读；三个新资产的完整源文件位于服务器。
- 通过各自独立 tmux socket 运行资源预检，本机没有仿真/渲染。
- 第一台预检时 GPU 0/1/3 有其他计算进程；第二台预检时全部四张 A100 无计算进程。GPU 尚未启动渲染。
- 第二账号不能写第一账号新建的日志子目录，改用其项目内独立 tmp 子目录重试成功，没有改变共享目录权限。
- Blender 3.4.1 只读打开原 Hidden Alley 源文件崩溃，4.2.23 直接启动因 glibc 2.17 失败，均有记录。
- 在工作区建立隔离 Debian glibc 2.31 加载器，官方仓库元数据定位并校验包；**Blender 4.2.23 --version 已成功**。没有替换系统库或修改共享 Conda 环境，尚不能因此宣布渲染环境通过。

## 正在推进

1. 用隔离加载器只读打开真实源场景，完成原生收音机及附属件审计。
2. 核实兼容运行时下的实际材质/Fog 合成与 GPU 隔离，再布置和渲染新版静态图。
3. 原生收音机倾倒留桌、天线不碰坏、R 接力及胶带转动仍未验证，不能写 PASS。

## 关键记录

- `D:\workspace\project1_database\log\V6.2_execution\node11_probe.json`
- `D:\workspace\project1_database\log\V6.2_execution\node12_probe_retry.json`
- 服务器隔离加载器清单：`/data/raw/huzijian/project1_database/tools/runtime/v62_compat_debian231_r2/manifest.json`
- 服务器脚本：`/data/raw/huzijian/project1_database/tools/v62/`
- tmux sockets：`/data/raw/huzijian/project1_database/tmp/v62_node11_control.sock` 与 `/data/raw/huzijian/project1_database/tmp/v62_node12_control.sock`
- 第一轮网页所列 libc 包下载返回 404，保留日志；第二轮从官方 Packages 索引定位实际可用包，校验后通过版本试验。

所有历史失败与旧交付保留，未删除文件。一次提前下载尚未生成的 node12 报告在本地留下空文件 `node12_probe.json`；它不是有效证据，使用 `node12_probe_retry.json`。暂未对其作清理操作。
