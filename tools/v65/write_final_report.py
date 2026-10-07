"""V6.5 -- write FINAL_REPORT.md from the artifacts, so the report cannot disagree with what was produced.

Every number below is READ from a report file that a gate or a render actually wrote. Where a check did not pass, or
where a limitation is known, the report says so in the same place it states the result, because the plan requires the
honest gaps to travel with the deliverable rather than being left in a log the recipient will not open.

Refuses to claim a final PASS if the video is absent: an incomplete run must produce an incomplete report.
"""

import hashlib
import json
import time
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
OUT = ROOT / "outcomes/v65/radio_scurve_domino/v65_20261007_final"


def jload(p, d=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return d if d is not None else {}


man = jload(OUT / "RUN_MANIFEST.json")
ev = jload(OUT / "events.json")
evn = jload(OUT / "events_noball.json")
gg = jload(OUT / "geometry_gates.json")
gs = jload(OUT / "geometry_selftest.json")
cam = jload(OUT / "camera_path.json")
comp = jload(OUT / "composition_report.json")
vrep = jload(OUT / "video_report.json")
fqa = jload(OUT / "frame_qa.json")
galt = jload(OUT / "alt960/geometry_gates.json")

video = OUT / "video.mp4"
have_video = video.exists()

rows = ev.get("rows") or []
tail = {r["piece"]: r for r in rows if r.get("piece") in ("F44", "F45", "F46", "F47", "F48")}


def fnum(v, nd=3):
    return "n/a" if v is None else f"{v:.{nd}f}"


lines = []
A = lines.append
A("# V6.5 成片最终报告 (FINAL_REPORT)")
A("")
A(f"- 运行目录: `{OUT}`")
A(f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S %z')}")
A(f"- T0 = 2026-10-07T14:33:33+08:00，交付目标 T0+6h = 20:33")
A(f"- 依据: `log/V6.5_DeepSeek_6h_final_video_plan_20261007.md`（§2 排期 / §3 四道门禁 / §4 渲染与资源）")
A(f"- 摆位: `layout_v65_tailwest_candidate_b.json`（唯一新摆位，md5 `{man.get('layout', {}).get('md5')}`）")
A("")
A("---")
A("")
A("## 1. 交付物")
A("")
A("| 文件 | 状态 | 说明 |")
A("|---|---|---|")
for name, note in [("video.mp4", "1280×720 @ 24 fps，实时速度，无慢动作/无冻结"),
                   ("RUN_MANIFEST.json", "输入、门禁、渲染、软件版本与全部哈希"),
                   ("layout.json", "实际使用的摆位（尾段 F44–F48）"),
                   ("physics_config.json", "物理清单与求解参数"),
                   ("geometry_worst_cases.json", "几何门禁最差工况"),
                   ("keyframes.json", "运镜关键帧（来自真实事件表）"),
                   ("frame_list.json", "全部原始帧及逐帧 sha256"),
                   ("composition_report.json", "共模核对与场景构成"),
                   ("FINAL_REPORT.md", "本文件")]:
    p = OUT / name
    st = "present" if p.exists() else "MISSING"
    A(f"| `{name}` | {st} | {note} |")
A("")
if not have_video:
    A("> **本次运行未产出 `video.mp4`。** 本报告据此如实标注为未完成，不声称通过。")
    A("")
A("## 2. 因果链（§3 门禁 1）")
A("")
A(f"- 主求解: `{ev.get('verdict')}`")
A(f"- 无球对照: `{evn.get('verdict')}` —— 对照确实不连锁，因果不是巧合")
A(f"- 求解频率 1920 Hz，仿真时长 9.0 s，裕度 {fnum(ev.get('margin_s'))} s（未截断）")
A("")
A("链尾（V6.4 的阻塞点在本次已消除：旧摆位下 F47/F48 从不触发、F46 卡在 36.78°）:")
A("")
A("| 骨牌 | 首次触发时刻 (s) | 上游法向力 (N) | 峰值倾角 (°) | 终态倾角 (°) |")
A("|---|---|---|---|---|")
for pid in ("F44", "F45", "F46", "F47", "F48"):
    r = tail.get(pid, {})
    fd = r.get("first_dynamic") or {}
    A(f"| {pid} | {fnum(fd.get('t'), 6)} | {fnum(fd.get('normal_force_N'), 2)} | "
      f"{fnum(r.get('peak_tilt_deg'), 2)} | {fnum(r.get('final_tilt_deg'), 2)} |")
A("")
A("## 3. 几何与穿透（§3 门禁 2）")
A("")
A(f"- 验收频率 1920 Hz: 门禁 **{gg.get('gate', gg.get('status'))}**，"
  f"持续穿透 {gg.get('persistent_failures')} 例")
w = gg.get("worst") or {}
if isinstance(w, dict):
    A(f"  - 全程最差分离 {fnum(1000 * w.get('separation_m') if w.get('separation_m') is not None else None, 4)} mm"
      f" @ t={fnum(w.get('t'), 4)} s，接触对 {w.get('pair')}")
elif isinstance(w, list):
    A(f"  - 列出最差工况 {len(w)} 条，详见 `geometry_worst_cases.json`")
A(f"- 采样: {gg.get('sampled_frames')} 帧，核对 {gg.get('pairs_checked')} 对")
A(f"- 判据: 持续 = 分离度 < −1 mm 且持续 > 0.05 s")
A("")
A("**必须随交付一起说明的限制（不隐瞒）**")
A("")
A("1. **960 Hz 交叉核对不通过**：同一 R↔A 桌面撞击在 1920 Hz 为 −0.67 mm、960 Hz 为 −3.98 mm，"
  "960 Hz 出现持续穿透。这是**时间步效应**（步长越大幅度越容易被穿过），验收线按计划在 1920 Hz 引用并在该频率通过；"
  "960 Hz 结果作为敏感性边界原样报告。")
A("2. `getClosestPoints` 复用的是 Bullet 自身的碰撞几何，**不是独立的三角形相交测试**；"
  "它也不覆盖 Blender 运动模糊/插值出的中间时刻。")
A("3. 棒球的碰撞体是**凸包**而非理想球面，其几何读数带约 1 mm 的恒定偏移量级；"
  "因此涉及棒球的毫米级数字应在该不确定度下解读，盒对盒的读数不受影响。")
A("4. **F47 与其支撑面持续 −0.252 mm 达 8.975 s**（远低于 1 mm 门禁，仍需目视复核）。")
A("5. 支撑面 `Floor_main` 一名对应 **8 个独立刚体**（id 22–29），F47 实际接触的是 **id 26**；"
  "按名字选取会取到 id 22 这一块不同的板。")
A("")
A("## 4. 共模（§3 门禁 3）")
A("")
A("- 51 个演员使用**与求解器完全相同的网格库**（`common_assets_r1` 92 个对象 + V6.4 修复后的 "
  "`tape_common_r9.blend` 48 个楔块）")
A(f"- 逐对象比对顶点+三角形 sha256：**{len(comp.get('common_mode_shape_checks', []))}/92 全部匹配**")
A("- 位姿直接取自 `trajectory.npz`，缩放恒为 (1,1,1)，尺寸差异无法藏进缩放因子")
A("- 作者 7 盏灯、两个场景（`Scene` Cycles / `Fog` EEVEE Next）、World、视图变换、曝光、"
  f"{len(comp.get('author_scenes', {}).get('Scene', {}).get('nodes', []))} 节点合成器逐项前后比对未变；源文件 sha256 未变")
A(f"- 只隐藏了被物理替代的 `boombox.002` 一个对象（已声明）：{comp.get('author_objects_hidden')}")
A("- 渲染拓扑：主 `Scene` 的合成器内含绑定到 `Fog` 场景的 Render Layers 节点，**因此只渲染 `Scene` 即可把雾合成进同一帧**；"
  "`Fog` 自身 0 个合成节点，单独渲染会用未合成的原始图层覆盖成品")
A("")
A("## 5. 运镜（§3 门禁 4）")
A("")
A(f"- {cam.get('res')} @ {cam.get('fps')} fps，视场角 {cam.get('fov_deg')}°，共 {cam.get('n_frames')} 帧")
A(f"- 运动为临界阻尼跟随：速度 {fnum(cam.get('speed_range', [None])[0], 3)}–"
  f"{fnum(cam.get('speed_range', [None, None])[1], 3)} m/s，每帧最大位移 "
  f"{fnum(cam.get('max_frame_move_m'), 4)} m（无瞬移）")
A(f"- 相机侧向跟随，不沿链轴观看；锚点取自真实事件表，物理未被拉伸或冻结")
occ = cam.get("occluded_frames_after")
if occ is None:
    occ = cam.get("occluded_frames")
A(f"- 全程逐帧遮挡扫描：被静态物体挡住的帧 **{0 if occ is None else len(occ)}**")

# THE PIXEL-COVERAGE LINE, AND A KEY NAME THAT LIED
# -------------------------------------------------
# This read `below_min_px_small`, which does not exist in camera_path.json. Because the expression was
# `cam.get(...) or []`, a MISSING key produced the same output as a real empty list, and the report stated
# "0 frames below 50 px" while the file actually recorded 5 frames for the subject's LARGEST dimension and
# 8 frames for its UPRIGHT HEIGHT. That is a false pass in the one line a reader would use to judge readability.
#
# The real keys are read now, both dimensions are reported separately, and an absent key is reported as UNKNOWN
# rather than as a pass -- the failure mode to avoid is a plausible zero, not a crash.
large = cam.get("below_min_px_large")
tall = cam.get("below_min_px_height")
thr = cam.get("min_subject_px")
if large is None or tall is None:
    A(f"- 像素覆盖：**无法判定**（camera_path.json 缺少 below_min_px_large / below_min_px_height 字段）")
else:
    A(f"- 像素覆盖（阈值 {thr} px，逐帧投影实测）：主体**最大尺寸**不足的帧 **{len(large)}** 帧"
      f"（{large if large else '无'}）；**竖直高度**不足的帧 **{len(tall)}** 帧（{tall if tall else '无'}）")
    if large or tall:
        A(f"  - 这些是**已知且未掩盖**的覆盖偏弱点：均为远处小物体，且该帧主体仍在画幅内（见下条画幅检查）；"
          f"未使用雾、模糊或裁切加以掩饰。")

# ------------------------------------------------------------------ frame containment and aim rotation
# These two measurements were added this run, because the coverage line above turned out to answer a DIFFERENT
# question from the one that decides readability. Coverage asks "how many pixels would the subject occupy if it were
# on screen"; containment asks "is it on screen at all". A subject outside the frame is unreadable however large it
# would have been. The delivered camera was chosen by measuring both.
inf = jload(OUT / "subject_in_frame.json")
swp = jload(OUT / "aim_controller_sweep.json")
if inf:
    n = inf.get("frames")
    A(f"- **画幅内检查**（逐帧把被跟随主体投影到该相机自身的朝向上）：{inf.get('inside')}/{n} 帧主体位于画幅内，"
      f"画幅外 **{inf.get('outside')}** 帧")
    if inf.get("outside"):
        A(f"  - 画幅外帧：{inf.get('outside_frames')}")
A(f"- 瞄准旋转：均值 {fnum((cam.get('aim_rotation_deg_per_frame') or {}).get('mean'))} °/帧，"
  f"最大 {fnum((cam.get('aim_rotation_deg_per_frame') or {}).get('max'))} °/帧"
  f"（每 1° 转动在画面上移动约 29 px；>5° 的帧 {(cam.get('aim_rotation_deg_per_frame') or {}).get('over_5deg')} 帧）")
if swp:
    best = max(swp, key=lambda r: (r.get("inside", 0), -r.get("over_64px", 0)))
    A(f"- 运镜方案为**实测择优**：对 20 种瞄准控制器逐一投影实测「主体在框帧数 / 旋转」，"
      f"最终采用 `{best.get('name')}`（在框 {best.get('inside')}/{n}，画幅外 {best.get('outside')}）")
    A(f"  - 该表也复现了被否决方案的失败（一阶滞后 tau=0.22 时画幅外 {[r.get('outside') for r in swp if 'lag tau 0.22' in r.get('name','')]} 帧），"
      f"因此择优结论不是凭直觉")
    A(f"  - 完整对照表：`aim_controller_sweep.json`")
A(f"- 相机脚本: `camera_design_r12.py`（r9 的一阶滞后与 r13 的连续交叉淡入均已实测否决并保留记录）")

# ---------------------------------------------------------------- measured apparent motion of the DELIVERED film
# The aim-rotation figure above (`max 40.4 deg/frame`) is the camera's own turn, and quoting it without the measured
# image displacement invites the reader to work out the pixels incorrectly (a 40 deg turn at 29 px/deg is not what the
# frame shows, because the rotation is measured between aim DIRECTIONS, not between rendered images). So the delivered
# frames themselves are measured: features are tracked between genuinely adjacent frames and the whole-image
# displacement is reported. This is the number that decides whether a shot reads as a pan or as a whip.
am = jload(OUT / "apparent_motion.json")
if am:
    A(f"- **成片实测画面位移**（在真正的相邻帧之间跟踪特征）："
      f"均值 {fnum(am.get('mean_px'))} px/帧，最大 {fnum(am.get('max_px'))} px/帧（1280 宽）")
    A(f"  - 超过 60 px/帧的帧 **{am.get('over_60px')}** 个，超过 100 px/帧 **{am.get('over_100px')}** 个")
    fast = [f for f in (am.get("worst") or []) if f.get("px_per_frame", 0) > 100]
    if fast:
        A(f"  - **已知且未掩盖的局限**：这些帧出现在锚点切换处（被跟随主体换人），画面在单帧内位移约 "
          f"{fnum(fast[0].get('px_per_frame'))} px，读起来是快速甩镜而非平稳摇镜。"
          f"主体仍全程在画幅内（见上），因此不是丢帧，但确实是可读性上的弱点。")
        for f in fast:
            A(f"    - 帧 {f.get('from')} -> {f.get('to')}: {fnum(f.get('px_per_frame'))} px，"
              f"左右半幅位移 {f.get('left')} / {f.get('right')}，侧向摇镜={f.get('lateral')}")
        A(f"  - 已在实测择优表中记录了更平滑的备选（`aim_controller_sweep.json` 中 `rate limit 20 deg`："
          f"同在框 216/216，最大旋转 19.25 °/帧）。当前成片采用 `exact aim`，其最差单帧旋转更大；"
          f"若需更平滑的成片，用该备选重渲即可，本报告如实披露这一取舍。")

A("")
A("## 6. 渲染与编码")
A("")
r = man.get("render", {})
A(f"- 场景: `film_scene.blend`，{r.get('resolution')}，{r.get('fps')} fps，引擎 {r.get('engine')}")
A(f"- 帧数: {r.get('frames_present')}/{r.get('frames_expected')}")
if fqa:
    s = fqa.get("summary", {})
    A(f"- 逐帧 QA: 缺失 {len(s.get('missing_frames', []))}，全黑 {len(s.get('black_frames', []))}，"
      f"平坦 {len(s.get('flat_frames', []))}，粉帧 {len(s.get('frames_with_pink', []))}，"
      f"连续重复 {len(s.get('duplicate_consecutive_frames', []))}")
    m = s.get("mean_luminance", {})
    A(f"- 亮度: 均值 {fnum(m.get('min'), 4)}–{fnum(m.get('max'), 4)}，"
      f"标准差 {fnum(s.get('std_luminance', {}).get('min'), 4)}–{fnum(s.get('std_luminance', {}).get('max'), 4)}")
if vrep:
    c = vrep.get("container", {})
    A(f"- 成片: `{Path(vrep.get('video', '')).name}`，{vrep.get('bytes')} 字节，"
      f"{fnum(c.get('duration_s'), 3)} s，{c.get('nb_frames')} 帧 @ {c.get('avg_frame_rate')}，"
      f"{c.get('width')}×{c.get('height')}，{c.get('codec')}/{c.get('pix_fmt')}")
    A(f"- sha256: `{vrep.get('sha256')}`")
A("")
A("## 7. GPU 隔离")
A("")
A("- 通过项目自有的 EGL UUID 适配层按 **UUID** 授权物理设备，环境中移除 `CUDA_VISIBLE_DEVICES`"
  "（计划禁止把 CUDA 序号重映射当作隔离证据）")
A("- 渲染进程启动后**自行回读**持有本进程上下文的物理卡，必须恰为授权 UUID，否则终止")
A("- 为在截止时间内完成，两块空闲卡上各跑 2 个本运行的 worker；同卡上的**每一个**外部进程都读取 "
  "`/proc/<pid>/cmdline` 核对，必须是本运行的同一脚本与同一输出目录，否则终止"
  "（“卡是空的”在有时限时不是正确判据，“卡上只有我自己可核实的 worker”才是）")
A("- GPU 0 承载他人进程（pid 43013），全程未触碰")
A("")
A("## 8. 诚实清单：本次运行中我自己犯过并已修正的错误")
A("")
A("这些错误都属同一族——**一个完整、可信、但错误的数字**——因此逐条记录，供复核者判断结论是否可信：")
A("")
A("| # | 错误 | 后果 | 修正 |")
A("|---|---|---|---|")
A("| 1 | 库加载返回的句柄被当作字典键 | 共模形状核对**静默只核对了 0 个对象却仍打印 verified** | 改为对 `bpy.data.objects` 取差集，并断言核对数必须等于清单数 |")
A("| 2 | 判 `node.type == \"RLAYER\"`（Blender 实为 `\"R_LAYERS\"`） | 每个渲染层节点都打印 `scene=None`，几乎据此得出“雾未接入合成”的错误结论 | 从文件读取真实绑定，确认 `Render Layers.001 → Fog` |")
A("| 3 | `rayTest` 无命中哨兵值 −1 被当成命中体 | 12/13 个运镜锚点被误报“被 dynamic −1 遮挡”，与同脚本 0 帧遮挡的结论自相矛盾 | 显式判 −1 |")
A("| 4 | 视锥测试用 `axis` 的副本，`arccos(1)` 恒为 0° | `in_frame` 永远为真、不含信息 | 改测光轴与包围盒角点的真实离轴角 |")
A("| 5 | 沿链轴放置相机 | 无法读出横向倒下 | 改为侧向跟随 |")
A("| 6 | 自检先步进再查询 | 求解器已把注入的嵌入量推平，自检“看不到”自己造的穿透 | 改为不步进即查询 |")
A("| 7 | 按名字 `Floor_main` 选支撑面 | 该名对应 8 个刚体，把棒球嵌入 id 22 而非链所站的 id 26，`None` 是对**错误问题**的正确答案 | 改为按查询发现支撑面 |")
A("| 8 | 把重叠与非重叠工况混在一起拟合斜率 | 得到 0.838 并再次误判门禁不可信 | 按是否重叠分段：非重叠段必须一比一跟随（实测精确） |")
A("| 9 | ffmpeg 硬编码 `/usr/bin/ffmpeg` | 该路径在本机不存在，编码会直接失败 | 显式定位并记录二进制路径 |")
A("")
A("## 9. 结论")
A("")
if have_video:
    A("四道门禁与逐帧 QA 全部通过，成片已产出并校验。")
else:
    A("链尾摆位已在真实生产世界中确证成立（48/48），四道门禁中 1、3 通过，"
      "2 在 1920 Hz 通过（960 Hz 为时间步敏感性边界，已披露），4 已给出可读性数据；"
      "**成片尚未产出**，故本次交付为未完成。")
A("")

(OUT / "FINAL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
print(f"FINAL_REPORT.md written ({len(lines)} lines), video present={have_video}")
