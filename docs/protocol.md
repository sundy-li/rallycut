# 算法协议 v1

UTF-8 JSON Lines；stdin 一条请求，stdout 只允许协议事件，stderr 用于诊断。默认生产检测器是 `blurball-pretrained-v1`；`classical-av-v1` 仅用于显式对照，不再支持 `mock-v1`，也不允许自动模型降级。

```json
{"protocol_version":1,"type":"analyze","job_id":"unique-id","video_path":"/absolute/match.mp4","audio_path":"/temporary/mono-16k.wav","duration":60.5,"config":{"detector":"blurball-pretrained-v1"}}
```

- 默认模型要求固定 SHA-256 的 BlurBall 官方权重和 PyTorch；缺失时 `error`，不在运行时下载。支持 MPS / CPU，3 帧连续输入，不通过复制补帧。
- 下方 `classical-av-v1` 结果例子仍可用于显式旧基线；默认 BlurBall 结果将 `model` / `summary.method` 改为 `blurball-pretrained-v1`，并增加 `summary.weights_sha256`（固定官方权重摘要）、`device`、`detection_frames`、`duplicate_frames`。Go 校验权重和请求的检测器一致。
- `duration` 来自 FFprobe；视频时间取实际解码器 PTS（默认 OpenCV，实验 VideoToolbox 使用 PyAV 的 PTS/time_base），不按固定帧率推算。
- `audio_path` 可省略；有音轨时 Go 提取临时单声道 16kHz PCM WAV，任务结束 / 取消后清理。Python worker 不再启动子进程，取消时不会遗留 FFmpeg 子孙进程。
- `progress` 可选 `performance`（`stage` 为 `inference` / `finalizing`、`processed_frames`、`elapsed_seconds`、`recent_fps`、`average_fps`）。它计算实际完成分析帧的墙钟吞吐，不是素材 FPS。缺字段的旧协议仍兼容；Go 校验后随现有 progress 更新，不额外增加事件/fsync。Go `Job.elapsed_seconds` 另计含准备的后台任务墙钟。
- 默认 `config.table_mode=optional`，无前置标定、无 ROI 检测门限；`off` 完全无几何；`precalibrate` 显式运行旧校准/跳搜，失败警告后继续全帧检测。`table_bounds` 空/null/缺省是合法成功结果；非空仍须有效矩形，不能伪造全画面为桌面。几何时段记录在 `table_segments`，无几何不生成触网/出界事件。
- `config` 可选 `net_region`（已确认网面两端 `[LX,LT,LB,RX,RT,RB]`，归一化坐标）。没有可信网面时不猜触网。结果增加 `summary.rally_events/rally_state_version/net_region_source`，回合增加 `end_reason/end_event_time/end_confidence/boundary_before/start_reason`；流式候选也必须保留，不能在音频融合或缓冲导出时重新合并边界。详见 [dead-ball-rules.md](dead-ball-rules.md)。
- `config` 可选 `decoder`（默认 `opencv`；`videotoolbox` 是 macOS + 可选 PyAV 的实验路径，禁止名义硬解实际软件回退，颜色转换差异需复核）、`precision`（`fp32` 默认 / `fp16` 仅 MPS）、`batch_size`（1–8，默认 4）、`pipeline`（默认 true）、`calibration_seconds`（初始窗口默认 600）、`calibration_jump_samples`（失败后后段跳搜预算，默认 96，0 关闭，最大 384）。后段每个局部窗口单独多帧确认，禁止跨分钟拼票、错误 seek 后顺扫整片；详见 [table-jump-search.md](table-jump-search.md)。GPU 前向和 CPU 传回在主线程，解码 / 后处理通过有界队列有序重叠；任何阶段失败均终止任务，不发布半成品。
- 缺少模型依赖、解码失败、无效时间戳明确报错，不退回模拟。球桌几何缺失/不支持不是默认分析失败；几何规则明确降级。

事件按顺序输出：

```json
{"protocol_version":1,"job_id":"unique-id","type":"progress","progress":0.35,"message":"真实画面分析 21 / 60 秒"}
{"protocol_version":1,"job_id":"unique-id","type":"result","result":{"protocol_version":1,"model":"classical-av-v1","rallies":[],"tracks":[],"summary":{"method":"classical-av-v1","decoded_frames":1800,"sampled_frames":1800,"track_count":0,"elapsed_seconds":10.2,"table_bounds":[0.1,0.4,0.9,0.5],"scene_changes":0,"audio_impacts":0,"warnings":["没有发现足够的连续球轨迹，不生成占位回合。"]}}}
```

`result` 必须是最后一条事件。错误事件：

```json
{"protocol_version":1,"job_id":"unique-id","type":"error","message":"缺少视觉依赖，请在项目目录运行 just setup"}
```

## 数据约束

- `rallies` 中每项：`id,start,end,confidence,score,selected,edited,evidence`。
- 时间为原视频时间轴上的秒，满足 `0 <= start < end <= duration`；ID 不重复。
- `evidence` 为 `visual` 或 `visual+audio`；不会输出只有音频证据的回合。
- `confidence` 为 0–1 的**启发式证据强度**，不是模型概率 / 准确率；`score` 为 0–100 的粗排分数。
- `tracks` 每项 `{id,points:[{t,x,y,confidence}]}`；`x,y` 为 0–1 归一化原画面坐标，`t` 严格递增且位于视频时长内，每段 3–60 点。
- `summary` 记录实际解码/评分帧数、候选轨迹数、音频瞬态数、可选球桌矩形和警告，新增 `table_mode/geometry_available/unscored_frames`。旧预校准字段只在显式模式成功时存在，默认 `calibration_strategy=not_required`。球桌预校准另记录 `calibration_method` / `calibration_samples` / `calibration_last_timestamp`；后段跳搜另记录 `calibration_jump_samples/jump_windows/jump_budget/search_extent_seconds`（均带 `calibration_` 前缀）及 `*_then_jump` 策略；检查到的最远位置不是连续覆盖。`calibration_first_timestamp/last_timestamp` 给出选中支撑的实际 PTS 范围。预校准不消耗正式分析帧，推理从原片 0 秒重新开始。无候选的结果是合法结果，不用假片段填充。
- Go 校验协议、任务 ID、模型、时间、坐标、摘要和非空回合的轨迹证据，限制单行结果为 32 MiB。候选中的明确 `table_bounds=[]` 即使不带新轨迹也必须转发，用于切镜/丢失几何后的清除；UI 不得回填上次分析/上一镜头 ROI。

## 缓存、取消和编辑

- 缓存键包含视频内容 SHA-256、协议、算法 ID、权重 SHA-256 和内嵌 worker / 神经网络 / 视觉 / 声音源代码摘要，不命中旧模拟缓存；无逐帧 checkpoint。
- Go context 取消 / 超时直接终止当前 FFmpeg 或 Python；解析错误也终止 worker，不保存残缺结果。
- 原始候选和轨迹单独保存。重新分析（含无缓存重跑）时，未经人工修改的机器回合按本次结果整体替换；人工添加（I/O、添加回合）和人工修正（改边界、拆分、合并、标记无效 / 收藏）的回合保留；与其重叠的新机器候选也保留为独立的机器回合（两个来源分别显示，ID 冲突时加 `-rN` 后缀），导出时按下述重叠策略选用；被取消勾选的机器回合若与新候选 IoU ≥ 0.5，新候选保持不勾选。被人工删除的机器回合不做记忆，重跑后可能重新出现。当前回合列表为空且存在机器候选时，直接采用机器时间轴（包括人工删空）。导出时 `export_settings.overlap`（`merge` 默认 / `sequential` 先开始的保留 / `human` / `machine`）只决定人工与分析回合重叠时谁胜出，败者整段不导出（`timeline.ResolveOverlaps`，前端 `resolveOverlaps` 镜像同一规则用于预估时长）；同类重叠总是由 `timeline.Segments` 合并。UI 的“只用机器结果”经确认后调用 `UseAnalysisCandidates` 整表替换（会话内可撤销）。
