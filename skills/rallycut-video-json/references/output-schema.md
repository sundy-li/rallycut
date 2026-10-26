# 精简候选 JSON v1

下面仅是结构示例，**不是识别结果，不得用作真实输出或填补零候选**：

```json
{
  "schema_version": 1,
  "kind": "rallycut.segments",
  "origin": "fresh_analysis",
  "source": {
    "path": "/absolute/match.mp4",
    "name": "match.mp4",
    "fingerprint": "content-sha256",
    "duration": 90.0,
    "width": 1920,
    "height": 1080,
    "fps": 29.97,
    "has_audio": true,
    "codec": "hevc",
    "rotation": 0,
    "bit_rate": 8233650
  },
  "model": "blurball-pretrained-v1",
  "review_required": true,
  "segments": [
    {
      "id": "visual-00001",
      "start": 12.3,
      "end": 20.1,
      "duration": 7.8,
      "start_timecode": "00:00:12.300",
      "end_timecode": "00:00:20.100",
      "confidence": 0.65,
      "score": 48.2,
      "selected": true,
      "edited": false,
      "evidence": "visual+audio",
      "review_required": true
    }
  ],
  "summary": {
    "method": "blurball-pretrained-v1",
    "decoded_frames": 2697,
    "sampled_frames": 2697,
    "track_count": 12,
    "elapsed_seconds": 35.2,
    "table_bounds": [0.1, 0.3, 0.9, 0.5],
    "scene_changes": 0,
    "audio_impacts": 20,
    "weights_sha256": "3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f",
    "device": "mps",
    "detection_frames": 300,
    "duplicate_frames": 0,
    "warnings": ["回合候选尚需复核"],
    "candidate_count": 1,
    "output_count": 1,
    "min_duration": 0
  }
}
```

## 语义

- `start` / `end` / `duration` / `source.duration` 全部为**秒**，不是帧号。时间码只是展示值，以数值字段为准。
- 区间为候选回合，不代表视频全覆盖分割，也不说明其余时间可安全删除；片段不额外叠加剪辑缓冲。
- `segments` 按开始时间排序；起止时间必须在原片范围内。允许零候选。
- `confidence` 是回合启发式证据强度，`score` 是粗排分数；均不是独立评估的准确率。
- `selected` 保留分析 / 当前项目选择状态；**列表包含所有满足最小时长的候选**，不因 `selected == false` 自动丢弃。
- `origin == fresh_analysis` 表示本次实际解码和推理；`saved_project_timeline` 表示读取并验证现有项目，保留人工时间轴。
- 项目复用时 `summary.manual_timeline` 反映是否包含人工调整；`elapsed_seconds` 是原分析耗时，不是本次转换耗时。
- `candidate_count` 为过滤前候选数，`output_count` 为当前结果数；`--min-duration` 不重新计算模型分数。
- 可选 `tracks` 只在 `--include-tracks` 时输出，结构为 `{id,points:[{t,x,y,confidence}],off_play?}`。坐标归一化到 0–1；这些是保留的候选短轨迹，不是全部逐帧检测。`off_play=true` 表示该轨迹远离本视频的对打区域（地上 / 场边 / 邻场的球，`summary.play_area_version`），只是显示提示：轨迹仍完整保留，回合规则不读这个标记。
- 新分析的摘要增加 `device`、`precision`（默认 `fp32`）、`batch_size`（默认 4）、`pipeline`、`implementation` 和 `pipeline_timings`。阶段计时包括 `producer_seconds` / `forward_seconds` / `postprocess_seconds` / `wall_seconds`，流水线下存在重叠，**不能把阶段时间相加当总耗时**。旧项目可能没有这些可选字段。
- 新增 `processing_fps`（完成画面帧数/流水线壁钟）、`analysis_fps`（含加载/校准/融合的核心平均，不含外部音轨提取/原片校验）、`decoder`、`hardware_decode`、`decode_format`。不要拿它们与源 `source.fps` 混淆；它们也不是 GPU-only benchmark。旧项目可能无性能记录。
- 进度 JSONL 可包含 `performance`：`stage: inference | finalizing`、`processed_frames`、`elapsed_seconds`、`recent_fps`、`average_fps`，仅描述当前真实画面阶段。项目转换不能生成一套新的实时性能数据。
- `summary.table_mode` 为 `optional`（默认，非阻塞辅助）、`off`、`precalibrate`（显式旧搜索）；`geometry_available` 表示曾获得可用几何。`table_bounds` 可为空、null 或缺省，不代表错误，不能填 `[0,0,1,1]` 冒充桌面；`table_segments` 逐时段记录几何空缺，缺失时不启用几何死球规则。
- 只有显式预校准才有后段球桌跳搜摘要：`calibration_jump_samples/jump_windows/jump_budget/search_extent_seconds`（均带 `calibration_` 前缀），策略为 `*_then_jump`，并保留 `calibration_first_timestamp/last_timestamp`。初始窗口 `calibration_search_seconds` 不等于整片覆盖范围；不要将“最远检查到”说成“此前所有帧都检查过”。
- `summary.activity_rule_version=perspective-activity-v2` 表示可用斜视几何时启用活动分段（v1 为旧规则）；v2 在实际确认时间结束，不回溯慢球窗口，局部持续恢复撤销待结束。`ball_settled/activity_gap` 仅为球路放缓/观测中断，`live_ball_evidence` 为活动启动证据，不得宣称触网或出界。它们的保护边界与其他回合边界一样保留；分段规则不删模型点/轨迹，输入路径变化须另做 A/B，不能套用原始点一致结论。无几何时不套用此活动规则。
- `activity_rule_version=side-transit-v4+frame-serve-v8+perspective-activity-v2`（`implementation=full-frame-v17`）：可信侧视几何（`side-color-rim`、宽高比 > 4）按过台分段（以 `transit_gap` 结束）；其他时段（含斜视框、无几何）在球沿画面横向往返时按自校准画面坐标的抛球发球 / 击球分段（以 `stroke_gap` 结束），看到发球前颠球时回合从颠球开始，第一拍快球前来回的轻打（软发球、搓球）算回合开头，击球后长时间慢速漂移（球在滚 / 被拿走）视为死球，没有抛球且只有一段球飞行、别无其他运动的（回合间把球打回 / 打走）不算回合，`start_reason=serve_prep`；该规则不能运行时斜视框回退 `perspective-activity-v2`。这些结束原因都不是触网 / 出界判定。
- 默认回合状态为 `dead-ball-v1`。`summary.rally_events` 提供死球/重新发球证据，包含回溯 `time` 和确认时刻 `confirmed_at`，不是裁判真值。`net_region_source` 可为 `unavailable`，此时不能声称判定了触网。
- 片段可带 `end_reason/end_event_time/end_confidence` 与下一段 `boundary_before/start_reason`。必须保留这些边界；不能按前后缓冲或声音连续性重新合并回去。剪辑上下文与识别时间不同，明确展示两者。
- `summary.warnings` 必须向用户如实概括，不能因结果非空而省略限制。

## 标准输出

输出到文件时 stdout 是一条完成摘要：

```json
{"status":"completed","output":"/absolute/match.segments.json","segments":1,"review_required":true,"origin":"fresh_analysis"}
```

`--output -` 时 stdout 为完整 JSON，不附加摘要。stderr 可能包含多条 JSON 进度 / 错误，不要与 stdout 拼成一个 JSON 文档。不要把新格式直接当作桌面 `*-rallycut.json` 项目打开，两者 schema 不同。
