# project1_database

真实三维场景、真实物体与真物理求解器驱动的物理视频生成项目。

当前主线以 `code/physics-video-sim/physics-video-sim-main/` 为代码根，固定管线为：

```text
sample -> simulate (PyBullet) -> validate -> camera -> render (Blender) -> save
```

项目约束：

- 被仿真运动必须来自求解器积分，禁止逐帧规定轨迹；
- 交付样本只使用有真实视觉模型的物体与三维场景；
- Blender 只回放 PyBullet 结果，不运行第二套物理；
- 保留场景作者灯光、World 和原始几何，不在场景外私自增加补丁地面或临时灯光；
- 先做物理、碰撞、相机和画面占比预检，再做正式渲染。

## 目录分工

- `code/physics-video-sim/physics-video-sim-main/`：主代码、配置、资产清单、碰撞代理和测试；
- `log/`：计划、调研、冻结登记、验证与交接记录；
- `tools/`：服务器同步、验证、打包和诊断工具；
- HF 私有仓库 `physics-video-lab/physics-video-assets`：大型 `source/`、`visual/`、纹理和 `.blend` 资产；
- `outcomes/`、`models/`、`target/`：本地大文件与生成结果，不进入 Git。

当前资产基线见 `log/V5.0_调研结果文档_当前资产整理清单_20260927.md`，近期工作计划见
`log/V5.1_计划文档_真实资产扩展与可交互场景实施计划_20260927.md`。

## 凭据

服务器与 HF 凭据只允许通过环境变量或本机未跟踪的 `.env` 提供。变量名示例见
`.env.example`；禁止把真实密码、token 或私钥提交到 Git。
