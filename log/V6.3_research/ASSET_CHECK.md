# V6.3 素材核查记录

核查日期：2026-10-05 至 2026-10-06。范围：项目本地与指定服务器工作区、用户给出的 HF 地址及资产登记的原始来源。本轮核查未启动渲染/求解；没有删除文件、没有读取 HF token。

## 1. HF 球体的登记位置

本地：`D:\workspace\project1_database\code\physics-video-sim\physics-video-sim-main\assets\objects\`。

服务器：`/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main/assets/objects/`。

两端已逐项检查 `sphere_baseball`、`sphere_basketball`、`sphere_football`、`sphere_volleyball`，目前均仅有 `asset.yaml` 和 `license` 子目录，没有清单指向的 `visual/model.glb` 或源模型/贴图。另在本地项目的 models、tmp、code 文件清单中查找球名，未定位到这四个完整 GLB。没有访问工作区外目录，也没有以此断言所有历史备份绝对不存在。

| 登记资产 | 清单尺寸/质量 | 来源与选择意见 |
|---|---|---|
| sphere_baseball | 0.073518×0.075169×0.075330 m；0.142–0.149 kg | Poly Haven，CC0；首选恢复 |
| sphere_basketball | 约直径 0.24 m；0.58–0.65 kg | 用户提供旧 GLB，许可 UNKNOWN；充气球刚体近似需另评审 |
| sphere_football | 约直径 0.22 m；0.410–0.450 kg | 用户提供旧 GLB，许可 UNKNOWN；不作为直接质量替换 |
| sphere_volleyball | 约直径 0.21 m；0.260–0.280 kg | 用户提供旧 GLB，来源/许可 UNKNOWN |

用户给出的 HF URL 未认证访问返回 401。历史 V4.3 文档曾使用 `physics-video-lab/physics-video-assets`，备份 manifest 的 repository 字段则仍为 `TLEphage/physics-video-assets`。这不能证明当前远程仓库的迁移状态。

## 2. 历史 HF 清单确实有完整球模型记录

只读取得服务器文件 `/data/raw/huzijian/project1_database/tmp/hf_backup/REMOTE_assets_manifest.json`，本地备份为 `D:\workspace\project1_database\log\V6.3_research\hf_manifest_snapshot.json`。

备份 45,904 bytes；SHA256：`ebd2c9655387902d219660181fd2c2b2e6e4cba5cc45ad7db3b2c215c29925a3`。该文件是历史远端清单，不是本轮联网列出的当前 HF 文件表。

| 历史 GLB | bytes | SHA256 |
|---|---:|---|
| sphere_baseball | 9,181,032 | 9592ac503a8f56406cb1cb98af191eb381731de9291cad9a57d50af06efb4e19 |
| sphere_basketball | 1,688,088 | 6d35ff2207e5de03887cc05f5bf7a153ee9afb2463ccf5355dfa16b96e412453 |
| sphere_football | 5,591,016 | 92ed6abfbfd130e88351a5f8a4ad78473fad0cad64fdfc47db8a56f08e821d64 |
| sphere_volleyball | 29,230,964 | 82f8a973fecc01b4ed26ca1b8899580df386ca729f48e05a6b13c7aa040c8e31 |

棒球清单另有 `baseball_01_diff_4k.jpg`、`baseball_01_nor_gl_4k.jpg`、`baseball_01_rough_4k.jpg`，分别约 2.04、4.41、2.43 MB，以及 glTF/bin 和原始包。服务器同目录的 REMOTE_README.md 自述为 private working archive，按资产单独许可，UNKNOWN 项不得公开分发。

原始来源 [Poly Haven Baseball 01](https://polyhaven.com/a/baseball_01) 本轮可打开，与本地来源登记一致。下载入口及配套贴图可见；这里只核查了页面，没有声称已经下载、导入、烘焙或实渲通过。

## 3. 当前白球是什么

项目内已有 `/data/raw/huzijian/project1_database/models/phyco_sim_objs/pool_table/white_ball.obj` 及本地对应文件；不是完全没有模型。本地 white_ball.mtl 为纯色材质，未见图像贴图引用；8_ball.mtl 也为黑/白材质分区，不能据此称为高质量图像贴图球。V6.2 试拍还另赋近纯色材质，因此用户指出其视觉表现差是有依据的。

## 4. 新增中间规格盒子核查

服务器完整目录：

- `/data/raw/huzijian/project1_database/models/gso/New_Super_Mario_BrosWii_Wii_Game/`
- `/data/raw/huzijian/project1_database/models/gso/House_of_Cards_The_Complete_First_Season_4_Discs_DVD/`

两者均列有 visual_geometry.obj、visual_geometry.mtl、texture.png、collision_geometry.obj、object.urdf、data.json。Wii 贴图 13,808,759 bytes，DVD 贴图 14,025,849 bytes。只证实文件存在与 metadata 可读，未做本轮贴图导入、方向或渲染质量验收。

Wii 源 XYZ 尺寸约 0.137079×0.191721×0.016727 m；DVD 源 XYZ 约 0.143493×0.023612×0.190930 m。它们能填补 12.5 cm 高小游戏盒到 27 cm 高中型盒之间的规格缺口，但质量、惯量、接力效果尚未实测。

本地还核查：

- `D:\workspace\project1_database\models\gso\LEGO_Star_Wars_Advent_Calendar\data.json`：源 XYZ 约 0.385183×0.076815×0.263711 m。
- `D:\workspace\project1_database\models\gso\Supernatural_Ouija_Board_Game\data.json`：源 XYZ 约 0.406508×0.057236×0.274949 m。
- `D:\workspace\project1_database\models\gso\Mad_Gab_Refresh_Card_Game\data.json`：约 0.156 m 近立方体，不默认适合薄骨牌连续传播。

这些 metadata 中的 mass 与 volume 数值相同，不能视为真实产品重量。共模、自己的贴图和局部接力验证仍是正式使用前置条件。

## 5. 本轮研究边界

本研究备忘写成时，尚未下载完整资产或运行新物理搜索；48 件、6–8 m 当时是设计任务，不是已实现结果。用户随后批准“完成计划并生成新版静态图”，同源棒球恢复、共同几何、实际布置及测试已继续推进，最新状态见 `D:\workspace\project1_database\log\V6.3_execution\STATUS.md`。旧局部小样、旧 0.4 kg 白球参数和新球资产不能互相充当通过证据。
