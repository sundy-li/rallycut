# RallyCut — Coding Agent 工作指南

适用于本仓库。与用户沟通使用中文；代码、路径、命令和标识符保持原文。先检查实际代码和工作区变更，不将旧计划或历史报告当成当前实现。

## 最新算法方向：检测不依赖强制球桌标定

用户最新确认：**专用球检测模型直接对整帧推理，不需要先找到球桌。** 不要继续把“前 600 秒校准 + 后段跳搜成功”作为默认分析的启动门槛。

当前默认已迁移为 `table_mode=optional`：无前置 `calibrate()`、无 ROI 检测门限；正常解码中可选获取几何，失败仍继续球检测。Go / headless / 项目协议支持无球桌，轨迹开关不依赖桌框；整段 `0043` 已做新鲜推理及原始检测逐帧 A/B。详见 `docs/full-frame-detection.md`。维护时不得退回旧门槛：

- `--table-mode off` 完全禁用几何；`precalibrate` 显式运行旧 600 秒 / 后段跳搜，失败警告后继续检测，不是模型固有要求。
- 桌面几何只作可选辅助：可信时用于球桌叠加、端线 / 触网等规则；缺失时明确降级，不能拿全画面矩形假装球桌。
- 球检测不依赖球桌，**不等于**无几何依据也能可靠判断触网 / 出界。没有证据时不得编造死球事件。
- 切镜用逐帧不可变 `ShotSnapshot`，不能跨线程读取提前变化的镜头对象；切镜清空几何，模型三帧输入、轨迹和回合均不跨镜头。手持晃动 / 摇镜不是切镜（补偿整体平移后仍大幅变化才算），几何在同一镜头内按整体平移跟随，见 `docs/camera-motion-cuts.md`。
- 空 `table_bounds=[]` 是合法结果与明确清除信号；UI 不得补用上次分析或上一镜头 ROI。非空矩形仍严格校验。
- 相关逻辑变更须同步 Go / Python 校验、摘要、UI、skill 资源和测试；区分模型原始点、经过跟踪筛选的点与回合候选，不将数量变化说成准确率提升。

`~/work/blurball` 是用户维护的算法参考仓库。只读检查最新提交和未提交修改，未经请求不修改它；适配代码不得让桌面包 / skill 运行时依赖这个本机路径。预处理、模型结构、精度或跟踪行为变化需做同片 A/B，不盲目整份替换。

## 项目地图

- `main.go`、`wails.json`：Wails v2 桌面入口和资源服务。
- `frontend/src/`：React / TypeScript 工作台；API 类型在 `api/`，时间轴与组件有单测。
- `backend/`：Go 项目持久化、单任务调度、媒体服务、Python 协议、时间轴和 FFmpeg 导出。
- `vision/`：共享推理实现；`worker.py` 是 JSONL 入口，`headless.py` 是无桌面 CLI。
- `vision/pretrained.py`、`neural_analysis.py`、`inference_pipeline.py`：模型适配、分析管线、有界流水线。
- `vision/rally_state.py`、`audio_features.py`：死球 / 再发球状态、视觉与声音融合；这些仍是规则。
- `models/manifest.json`：模型、权重来源 / 哈希、许可和推理配置记录。
- `skills/rallycut-video-json/`：skill 源模板；`scripts/build_skill.py` 从共享实现组装完整发行包。
- `tests/`、`vision/tests/`：集成、UI、原生桌面、独立 skill 与视觉回归。
- `docs/`：协议、架构、实际验证与限制；`plan.md` 是初始规划，不能当完成清单。

## 开发与验证命令

以 `justfile` 为准，当前没有 `Makefile`。桌面目标首先是 macOS / Apple Silicon。

```bash
just doctor             # 检查外部命令与开发环境，不等于完整模型验收
just setup              # Go / npm / Python 3.12 + OpenCV / NumPy
just setup-model        # 显式安装 PyTorch 并下载 / 校验官方权重
just dev                # 原生 Wails 开发；不只是浏览器预览
just dev-web            # 仅前端预览，没有 Go 本地文件能力
just test               # 前端构建、Go race、Python、skill、前端单测
just test-go
just test-skill
just fmt
just skill              # build/skills/rallycut-video-json/ 与同名 .skill
just build              # 生产构建并复制到 build/release/RallyCut.app
just run                # 启动独立生产版
```

常用局部检查：

```bash
.venv/bin/python -m unittest discover -s vision/tests -v
npm --prefix frontend test
go test -race ./backend/...
python3 scripts/check_runtime_imports.py --source vision \
  --installed build/skills/rallycut-video-json/assets/runtime
```

UI 回归入口是 `tests/ui/test_workbench.py`，需 Playwright / Chrome 和其约定的本地 Vite 端口。原生检查是 `tests/desktop/test_launch.py` / `test_preview.py`，要求 macOS。按实际任务选测；文档-only 修改无需启动桌面或重跑模型。不要把浏览器绑定 fixture 测试当作真实原生 / 模型验收。

## 共享运行时与交付

- **只维护一份算法**：修改 `vision/`，不要直接修改 `build/skills/` 或应用数据目录下解包出的 worker。
- 新增 / 重命名本地 Python 依赖时，同时更新 `vision/embed.go` 和 `scripts/build_skill.py` 的资源清单。检查导入闭包，避免源码能跑但发行包缺模块。
- worker 以源码 digest 隔离安装，模块原子写入；源码 / 配置 / 权重变化隔离旧缓存。新增可变推理参数进入缓存路径时必须纳入缓存键。
- `build/bin/RallyCut.app` 可能被 `wails dev` 覆盖为开发二进制，不能作为稳定独立版。用 `just build` 发布、`just run` 启动 `build/release`。
- `just run` 不会自动重建已有旧包。修改后先构建，并提醒用户退出旧窗口；不得杀掉用户无关进程。
- skill 必须能复制到仓库外运行，不依赖 Go / Node / Wails。权重单独显式安装，分析不自动联网。
- 固定清单的 Windows 预制环境在完整验证成功后保存本机 readiness 记录；后续启动先纯文件轻量核对，命中直接 ready，不重复启动 Python／FFmpeg／模型前向、不闪准备页。缺记录、关键文件／版本变化或显式复检才完整检测。内部命令统一经 `backend/childproc`，Windows 不创建控制台；用户主动打开的文件对话框和资源管理器保留可见行为。详见 `docs/startup-ready-cache.md`。
- 桌面首次启动先异步、本地检测；缺依赖必须由用户明确点击后才准备，不能恢复 Startup / useEffect 自动安装。Python、FFmpeg / FFprobe、分析依赖与模型全部自检通过才放行；前后端与快捷键均设门禁。平台资源与哈希在 `backend/setup/artifacts.json`，下载到私有目录，不改全局 PATH / 系统 Python。Intel Mac 使用兼容的 torch 2.2.2 / NumPy 1.26.4，不能装不存在的 torch 2.8 Intel wheel。状态 revision 防止迟到 RPC 覆盖新事件；下载显示真实字节，pip 等显示阶段进度，未就绪不显示 100%。详见 `docs/first-run-setup.md`。

## 视频与模型约束

- 时间取解码 PTS / time_base，统一为原片时间轴的秒；禁止 `frame_index / 30`、截断 FPS 或以 seek 目标伪造实际时间。
- 保留 RGB、512×288 等比变换及反变换、ImageNet 归一化语义。颜色转换 / 缩放 / 精度变化先测输入与输出一致性。
- 当前默认 MPS 优先、CPU 可用，FP32 / batch=4 / 有界流水线；不要求 CUDA。更大 batch 或 FP16 不一定更快，FP16 仅显式选择。
- VideoToolbox **解码**为显式实验路径：PyAV 与 OpenCV 颜色转换不完全一致，可能改变候选；不能默默切换。必须核验硬解确实启用，不能静默软件回退后仍标“硬解”。
- 权重按固定大小 / SHA-256 校验，`weights_only=True`、严格 `state_dict` 加载。缺模型 / 依赖或推理失败必须报错，不退回 mock 或假定时间窗口。
- 网络代码与 notices 保留来源；权重独立再分发许可未明确，不得打进应用 / skill / Git，不能把公开下载等同于可商业分发。
- 素材 FPS、GPU 前向 FPS、画面流水线 FPS、含准备的任务均速分别记录；并行阶段耗时不能相加当总耗时。

## 分段、编辑与导出

- 参数方向已确认：发球前 / 回合结束后保留秒数，以及最多保留多少个回合。用户已澄清“回合板”指**回合数量，不是击球板数**。原生已有 `pre_roll/post_roll`，但 skill 参数和数量限制尚未统一完成，不要重复追问或声称已交付。
- 球仍可见不代表回合仍有效：接球、捡球、回送不能自动连成同一回合。死球与再次发球要有可回放的证据。`rally_transits.py` 在可信侧视几何时按快速低位过台分段（`side-transit-v4`，见 `docs/side-transit-segmentation.md`）；其他时段（斜视框 / 移动镜头 / 无球桌）在球沿画面横向往返时由 `rally_serves.py` 按本视频自校准尺度的抛球发球 / 击球分段，看到发球前颠球则从颠球开始（`frame-serve-v8`，`start_reason=serve_prep`，见 `docs/spectator-frame-serves.md`）；该规则不能运行时斜视框才回退 `rally_activity.py` 的斜视活动规则；`ball_settled/activity_gap/transit_gap/stroke_gap` 不是触网/出界裁判事件，不得误报。结束需落在确认的观测时间，不能回溯到慢速窗口起点；局部持续恢复应撤销待结束，静止/准备碎片不能仅靠邻桌音频生成回合。见 `docs/activity-end-confirmation.md`。
- 保留 `rally_events`、`end_reason/end_event_time/end_confidence`、`boundary_before/start_reason`；音频融合、流式候选和导出缓冲不能抹掉保护边界。
- 识别边界与剪辑前后缓冲分开。显式手动合并 / 边界修正可覆盖自动判断。用户已确认重分析（含无缓存重跑）规则：未经人工修改的机器回合整体替换；人工添加（`manual-` ID）和人工修正（`edited=true`）的回合必须保留；与之重叠的新机器候选**也保留**（用户确认：人工与机器是两个独立来源，都要在列表显示），导出时由 `export_settings.overlap`（重叠对话框：人工覆盖分析 / 分析覆盖人工 / 合并 / 先后）决定用哪份。规则在 `Project.ApplyAnalysis`，不要退回“非空人工时间轴整表冻结”，也不要再丢弃重叠候选。只要当前回合列表为空且存在机器候选，就自动采用机器时间轴，包括人工删空，无需额外确认。
- 项目 / 缓存 JSON 可原子更新；独立分析 JSON 和视频导出默认拒绝覆盖原片或已有输出，取消与失败不发布半成品。重启恢复为 interrupted，不能伪装已完成。
- 同时只运行一个分析或导出；Go 子进程使用参数数组 / context，取消后回收，不拼 shell 字符串。流水线线程异常需传播并停止，不无限阻塞队列。
- macOS 编码用 `h264_videotoolbox` / `hevc_videotoolbox` 时采用码率，不混入软件 preset / CRF；硬件失败整批软件重做，不能混拼编码器。
- 原片预览走受项目 ID 限制的媒体路由，支持 Range / HEAD；开发模式须绕过 Vite SPA fallback。不要把 HTML 响应误报成 WebView 不支持编码。
- 球轨迹与球桌叠加是独立开关；没有球桌只禁用相应显示，不能影响轨迹预览。远离本视频对打区域的轨迹带 `off_play=true`（`vision/play_area.py`，自校准、不依赖球桌），只是不画，不删除、不参与回合规则，见 `docs/play-area.md`。

## 测试证据与协作

- 用户私有视频、权重、项目、截图不提交 Git、不上传。唯一例外是用户明确批准的产品展示：`site/public/media/rallycut-demo.mp4`（30 秒内）、其预览 GIF 和封面，以及用户提供用于 README / Pages 的工作台录屏 `site/public/media/rallycut-workbench.mp4`（只剪去开头 1 秒、转码，不改操作顺序）、其预览 GIF 与视频封面；不能扩大为原片、项目或其他素材。完整私有素材回归通过显式环境变量启用，普通 CI 不得依赖它们或 `/tmp` 既有产物。
- 回合准确率回测用私有标注库 `rallycut-labels`（`RALLYCUT_LABELS_DIR`）：`just eval cache` 一次新鲜推理写 L0 检测缓存并核对重放一致，`just eval run [--compare <基线> --gate]` 在缓存上重放当前 L1/L2 规则并按统一口径打分（`vision/evaluation.py` `score_labels`）。`neural_analysis.TrackingStage` 是新鲜分析与重放共用的唯一下游入口，不得另写简化重放；改 L0 相关代码（见 `detection_cache.L0_SOURCES`）后缓存自动失效。见 `docs/evaluation.md`。
- 用户新标注的项目用 `just eval import <项目.json> --id <id>` 导入（只取 `manual-*` 与 `edited=true`；部分标注用 `--covered`），再 `eval cache --video <id>`；**第一次 `eval run` 是独立成绩，先原样报告**，之后才看错误、调规则。规则改动在全部视频上 `--compare --gate`，只保留不让任何视频变差的改动，参数取平台区，拒绝的尝试写进文档。
- 用户已确认的标注口径（起点颠球或抛球都算对、擦网重发可选、发球失误算回合、递球 / 捡球不算、只比已标注范围）、当前基线、每个视频已查明的剩余错误和已拒绝的规则尝试都在 `docs/evaluation.md`，开始优化前先读，不要重复排查或重复尝试。新结论（用户回答、口径、被拒绝的尝试）要随手写回该文档或对应规则文档。
- `0043` 的 17–18 秒右侧出界接球、34 秒左侧台下接球是用户报告的难例；不能在算法中硬编码文件名 / 时间点。更改分段时保留正例及正常对拉、擦网继续、低位救球等反例，见 `docs/dead-ball-rules.md`。
- 新鲜推理、已保存项目转换、检测回放、合成视频、UI fixture 是不同证据，报告时明确区分。`from-project` 不会重新套新算法切旧结果。
- 候选数量、置信分数与两个错例通过都不等于整场准确率；没有独立人工真值，不宣称达到 `plan.md` 的准确率目标。
- 共享工作区可能被用户 / 其他 agent 同时修改。编辑前重读相关片段、保留无关修改；不重置仓库、不无意提交生成包。与本次任务相关的依赖清单缺项要一起修复。
- 说明修改文件、实际跑过的验证及未验证范围；后台任务完成前不能写“已通过”。

进一步阅读：`README.md`、`docs/architecture.md`、`docs/protocol.md`、`docs/dead-ball-rules.md`、`docs/throughput.md`、`docs/licenses.md`、`skills/rallycut-video-json/SKILL.md`。历史标定文档记录旧实现，不能覆盖本文件顶部的最新产品方向。
