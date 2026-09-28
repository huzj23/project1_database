# 03：真实资产、场景副本与碰撞构建

前置：01 已通过；读完 02。首先完成 Italian Flat 和主选盒/罐，其余场景处理随 06、07 推进。输出采用项目现有 `assets/objects/<id>`、`assets/environments/<id>` 结构；所有源文件保留，生成文件放运行副本或独立输出。

## 1. 事实与输入位置

本地基础根：`D:\workspace\project1_database\`；服务器基础根：`/data/raw/huzijian/project1_database/`。下表路径相对于这两个根，用于定位；调用工具时必须展开为绝对路径。

| 内容 | 已有位置/事实 |
|---|---|
| 84候选物体审核图 | `outcomes/v5_asset_review/objects/`，总览 `outcomes/v5_asset_review/index.html` |
| 原始138物体元数据 | 本地 `tmp/v5_candidate_inventory.json`；服务器 `models/gso/`，本地目前仅部分模型完整 |
| Italian Flat 源文件 | `models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend` |
| Hidden Alley 源文件 | `models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend` |
| The Shed 历史服务器位置 | `models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend`；执行前验证 |
| V5.4 场景审计 | `outcomes/v54_feasibility/italian_flat_interaction_audit.json`、`hidden_alley_interaction_audit.json` |
| 审计工具 | `tools/v54_audit_interaction_scene.py`，只读源文件，输出JSON |
| 场景灯光/贴图审计 | `outcomes/v5_asset_review/scenes/audits/` |

源 SHA-256 基准：

- Italian Flat：`0027fcbd73411cce7f49b3d86c22c03d18980e22641083da9d8ba82d9fc94e25`
- Hidden Alley：`3dd51c6dc7aad321e6cd4bada26785d87cdf376e649f20aa4f87ef5cf127e151`
- The Shed：`18b007e0f55c4bb3b5f746c698b6c524508253cb763f2b7b14345cbefb81c8d0`

如果哈希不符，先确认是原文件、打包文件还是运行副本，保留两者并说明差异；不要覆盖或假定损坏。

## 2. 选择最小物体子集

从已认可的盒/罐类别选：一个适合小桌的小盒、一个适合站立倾倒的薄长盒、一个尺寸清晰的封闭罐/瓶，另外各留一个备选。写 `approved_assets.json`，记录 exact asset_id、原图路径、实际尺寸、单/多部件语义、碰撞文件、视觉接受依据和物理适用性。

候选建议只作为检索线索，必须以 inventory 中完整 ID 和实际图核对：小包装约 0.12–0.18 m（如 Office Depot HP 71、Nescafe）；媒体盒/棋盘游戏盒可作多米诺；Borage 小瓶约 0.062×0.062×0.111 m、Creatine 罐约 0.129×0.129×0.184 m。Clue 盒长约 0.497 m，不能塞进约0.33 m边桌。不要只凭产品名推断扫描的是实物还是包装。

优先选择单一刚体语义、稳定平底、完整纹理、没有软线缆的模型。封口纸盒在本任务视作不可形变刚体；空软纸袋、敞开会拍动的纸板片、多个未连接散件不进入主链。原本应有活动零件的扫描资产不能因OBJ单文件就视为一体。

不对已批准盒子再重新做84件海选。最多检查6个盒候选和3个罐候选，选出满足几何/质量条件的主备资产。没有合适者记录具体原因后再扩大，不换成无纹理理想长方体交差。

## 3. 归一化和质量

读取源单位、物理尺寸、URDF mesh scale、视觉导入轴向；烘焙变换并记录 02 的矩阵。尺度校验至少使用模型bounds和一个场景已知量（桌高/瓶高）交叉检查。正常物品不能为了适配桌面任意缩小几十倍。

视觉模型精度与碰撞精度独立报告，扫描视觉不水密不等于不可用；碰撞代理必须可靠。质量不能直接使用 GSO 的体积数值。测量/厂家数据可作依据，否则按材质、尺寸、是否空箱/满罐估计，清楚标 `estimated` 并保留合理区间。包装盒质量必须是包装及声明内容物的质量，不能拿裸机质量冒充整盒。

对盒可用完整长宽高计算 `Ixx=m*(h²+d²)/12` 等；对低面凸体按体积/密度计算惯量。记录采用的近似。不要复制旧backend通用半轴平方除5的近似套在所有盒子上；重心、质量和惯量都要统一在同一刚体坐标。

## 4. 视觉与碰撞分离

- 真正长方体盒可用贴合其六面的 box 碰撞，视觉仍是真实扫描纹理；明显缺角/凸起影响接触的盒用低面凸代理。
- 封闭圆罐可用圆柱或低面凸包；瓶颈等几何会影响碰撞时使用多个凸部件。
- 开口杯、空心瓶、托盘不能用一个封口凸包填满内部。优先本轮只启用一个可靠封闭/带塞瓶；如选择杯或托盘，制作保持内部空间的凸分解。
- 动态网格为封闭凸体或 compound。静态地面/墙可以使用提取三角网格；不把整栋场景高模送入动态求解。
- 512三角面为普通代理起点；复杂compound可1024/2048并记录原因。静态区域允许更高但必须限制局部范围，面数不是唯一质量门槛。

检查：visual/collision叠加正交三视图；尺寸误差目标不超过1%；关键接触面偏差不超过 `min(2 mm, 最薄有效厚度*5%)`。不满足时改代理，不靠扩大碰撞margin掩盖。对于扫描毛刺可声明去噪仅作用碰撞代理，并保存差异。

默认碰撞margin选不大于最薄厚度5%，上限1 mm；实际支持情况通过API验证，不能写了配置就声称生效。边缘、薄板和凹部需要单独接触探针测试。

## 5. 场景分层与原生道具提取

运行副本至少分 `environment_static_visual`、`environment_static_collision`、`interaction_dynamic_visual`、`interaction_dynamic_collision`、`authored_lighting`、`source_archive`。分类不要求改源文件对象名，另存稳定 object_id 对照表。

先复制/实例化必要对象，再按 evaluated depsgraph 烘焙层级/修改器。道具激活后，原静态显示实例在运行视图中隐藏归档，原静态碰撞中也要排除该几何；对动态提取前后做初态像素/几何对比，防止重影或“撞到自己的静态副本”。不得从源 `.blend` 真正删对象来简化。

静态collision不仅有地面：对每个动态物体预测扫掠体加安全margin，凡可能相交的墙、桌腿、托盘、路沿和其他杂物均需有碰撞，或调整路径避开。凡在画面里会被碰到却只是visual的物体是失败项。软家具另建禁入区域/距离检查，不把它们伪装成硬物体来通过测试。

记录支撑面真实对象、三角面范围、法线、孔洞和坐标变换；box proxy只用于确为平直实体的局部结构。碰撞代理无渲染显示不等于允许凭空造地面。

Italian Flat 的放置区域可以有“预期被撞目标”，但触发物初始占地和接近路径必须 verified_clear，其他非目标障碍必须避开或建collision。这是对旧“全表面净空”规则的明确扩展，不能把整个拥挤桌面误标为空。

## 6. 本关验收与失败处理

产出：三件主选资产及备选的manifest、源哈希/许可、碰撞文件和尺寸报告；Italian Flat静态碰撞/动态道具草案；坐标变换单测；源副本差异清单；固定seed对齐图。

先验证源原样图，再验证新运行副本的初态图。导入造成光照/材质明显改变时优先保留场景 `.blend` 和作者节点，调整项目导入适配，不批量换简化材质。单物体导出GLB失败可保留OBJ/MTL或单体blend；接口统一由AssetManager解析。

若初始静置不稳，先排查碰撞平底/质心/尺度和重叠，再查摩擦。不得用极端阻尼或冻结目标来遮住几何错误。通过后进入04；06/07前补对应场景的同等报告。
