# V6.2 执行状态

日期：2026-10-05。状态：`VISUAL_PILOT_READY_WAIT_FEEDBACK`。已完成服务器环境、局部机制预检和四张修正后的静态试拍，已下载本地。**这不是完整 G1 验收包**：完整长链、共模和接触门禁仍需完成。没有启动运镜或完整视频。

## 已完成

- 阅读 V6.1 实際评审包及渲染脚本，检查 8 张联系图、3 张用户点名单体图。
- 编制 V6.2 计划：球→原生收音机→唯一落体；地面加入胶带环、LEGO 厚包装与 Paper Mario 小盒。
- 确认旧渲染脚本未同步主场景/Fog 的新相机与投影，存在可见重影，要求修复而非关闭雾效。
- 两台 SSH 已成功；指定共享工作区可读；三个新资产的完整源文件位于服务器。
- 通过各自独立 tmux socket 运行资源预检，本机没有仿真/渲染。
- 第一台预检时 GPU 0/1/3 有其他计算进程，未使用这些 GPU；第二台在两次空闲检查通过后启动试拍，Cycles 绑定 GPU 0 的明确 UUID。本轮服务器 GPU 渲染已成功完成，不是仅启动程序。
- 第二账号不能写第一账号新建的日志子目录，改用其项目内独立 tmp 子目录重试成功，没有改变共享目录权限。
- Blender 3.4.1 只读打开原 Hidden Alley 源文件崩溃，4.2.23 直接启动因 glibc 2.17 失败，均有记录。
- 在工作区建立隔离 Debian glibc 2.31 加载器，官方仓库元数据定位并校验包；**Blender 4.2.23 的启动、原场景加载、Cycles CUDA、Fog 及完整合成图均已实测通过**。没有替换系统库或修改共享 Conda 环境。
- 第二账号不能读取部分 GSO 源文件，因此由第一账号建立 33 个本任务输入副本；没有修改原素材的权限。
- 原生收音机导出 37 个拓扑连通分量；导出原桌、两张椅子和地面几何，仅供本任务 CPU 小样。
- 做了三组六个机制候选（共 18），以及一个 960 Hz 复核和一个无球对照。第三组找到初步“收音机留桌、R 落地”的方向；**没有物理 PASS**。
- 第一批试拍发现原 GSO 模型轴向不同、落体镜头裁掉接收物；保留该批，另生成 pilot4 修正图。胶带已调整为孔轴横跨路线，而不是沿路线。
- pilot4 归档到服务器标准 outcomes 路径；工作工程约 485 MB 留在服务器，四张 PNG 和报告已下载本地。原作者 `.blend` SHA256 与基线完全一致，工作副本保留原对象矩阵和 7 盏灯。
- 14 个仅服务器保留的脚本中间版本已备份到本地 `D:\workspace\project1_database\tools\v62\server_history\`，含 SHA256 清单。失败输出未删除。

## 本地图片与评审

评审入口：`D:\workspace\project1_database\outcomes\v62\radio_mixed_domino\20261005_pilot4\PILOT_REVIEW.md`。

同目录包含 `01_table_story.png`、`02_table_side.png`、`03_drop_bridge.png`、`05_tape_and_suitcase.png`、`pilot_report.json`。

服务器归档：`/data/raw/huzijian/project1_database/outcomes/v62/radio_mixed_domino/20261005_pilot4/`。
原始运行目录：`/data/raw/huzijian/project1_database/tmp/v62_node12/run_20261005_pilot4/`。

试拍是桌面三物体＋地面八件候选，仅确认素材、真实场景和景别。图中空中白球是抛射初态；其他物体并不表示已经求解过动作。不要把这八件展示组当成已接通的多米诺链，尤其不能指望小游戏盒跨过当前大间距直接推倒 LEGO 厚包装。

## 已知不合格与下一步

1. 机制候选：球约 79 mm、估重 0.4 kg，收音机估重 2.5 kg，R 估重 0.07 kg；速度 X=4.5 m/s、接触摩擦乘积约 0.6 的估计配置，在 480/960 Hz 均保持 B→A→R、收音机约 90.6° 留桌、R 落地；无球对照约 0.020° 最大倾斜。它对摩擦敏感，不是实测参数或鲁棒性证明。
2. **480/960 Hz 小样最深接触距离约 -9.48/-6.48 mm，穿透门禁未过。** 必须记录最深接触对/子步/位置，核对碰撞 margin、CCD、时间步与实际共模几何，不能仅凭视频看不见就放行。
3. 机制使用收音机 37 分量凸包近似、R 规范盒；试拍使用原扫描网格。二者**尚未共模**，绝不能直接把小样轨迹绑定到这些显示模型。需完成统一规范实体、自己的纹理、孔/把手/天线几何及差异评审。
4. 小样环境仅桌子、两椅和 Floor_main，未加入完整原墙与散布物；球反弹、天线扫掠、落体接力和地面路线都要重新检查。新增物体仅做中心支撑射线，底面支撑/重心/静置/障碍物门禁仍缺。
5. 尚未求解胶带滚动或接通地面长链，也未生成完整 24–36 物体布景。完成前述核心几何与门禁后，再交计划中的八图完整 G1，等待用户明确确认。
6. 原灯和对象矩阵已检查、源文件 SHA 未变；完整工作副本材质/World/合成节点差异及 Fog 新对象遮挡仍需做结构化审核。相机动态遮挡、连续净空也尚未验收。
7. 第一轮首次图约 704 s、后两图约 104 s/720p。不能据 Cycles 单层约数秒承诺全片耗时；先做连续帧热启动基准，保留原 Fog/合成。禁止偷偷关雾来追工期。

用户对局部图片的意见只用于下一轮布景，不自动批准 G2。**接续执行从完整阶段一开始，不得跳到运镜或完整视频。**

## 关键记录

- `D:\workspace\project1_database\log\V6.2_execution\node11_probe.json`
- `D:\workspace\project1_database\log\V6.2_execution\node12_probe_retry.json`
- `D:\workspace\project1_database\log\V6.2_execution\source_4223_probe.json`
- `D:\workspace\project1_database\log\V6.2_execution\geometry_audit.json`
- `D:\workspace\project1_database\log\V6.2_execution\mechanism_probe_round1.json`、`mechanism_probe_round2.json`、`mechanism_probe_round3.json`
- `D:\workspace\project1_database\log\V6.2_execution\pilot4_artifact_manifest.json`
- 服务器隔离加载器清单：`/data/raw/huzijian/project1_database/tools/runtime/v62_compat_debian231_r2/manifest.json`
- 服务器脚本：`/data/raw/huzijian/project1_database/tools/v62/`
- tmux sockets：`/data/raw/huzijian/project1_database/tmp/v62_node11_control.sock` 与 `/data/raw/huzijian/project1_database/tmp/v62_node12_control.sock`
- 第一轮网页所列 libc 包下载返回 404，保留日志；第二轮从官方 Packages 索引定位实际可用包，校验后通过版本试验。

运行指引与缓存注意事项：`D:\workspace\project1_database\tools\v62\DEPLOYMENT.md`。后续使用项目内 `blender42_scoped.sh`，补全 CUDA/OptiX/OpenGL/Mesa 专项缓存重定向；前期没有单独核验驱动默认缓存位置，不宣称该部分已完成目录审计，也不要访问工作区外去追查/清理。

Git：首个计划提交 `7e39673` 已推送 `origin/main`；执行代码、备份与结果摘要将作为本轮后续独立提交。服务器根原无 `.git`，代码另放项目内隔离检出，实际提交见 `D:\workspace\project1_database\log\V6.2_execution\GIT_HANDOFF.md`（生成后以其为准）。没有把其他任务的修改混入提交。

所有历史失败与旧交付保留，未删除文件。一次提前下载尚未生成的 node12 报告在本地留下空文件 `node12_probe.json`；它不是有效证据，使用 `node12_probe_retry.json`。暂未对其作清理操作。
