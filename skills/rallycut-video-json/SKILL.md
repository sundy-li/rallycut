---
name: rallycut-video-json
description: 将本地乒乓球比赛视频识别为回合候选 JSON，或将已有 RallyCut 项目转换为精简片段 JSON。用于“视频切分成 JSON”“识别乒乓球回合”“输出片段起止时间”“不启动桌面应用分析视频”等请求。使用专用 BlurBall 预训练模型；完全本地运行，不需要 Go、Node 或 Wails。
---

# RallyCut 视频 → JSON

使用本 skill 内置的 CLI，不要重新编写检测器，不要用固定时间窗口伪造识别结果。默认直接整帧检测乒乓球，不要求先标定球桌；不是通用场景切镜头工具。无几何时不猜测触网 / 出界，回合候选仍需复核。

## 路径与环境

将 `SKILL_DIR` 设为本文件所在目录的绝对路径；所有脚本路径相对此目录，不依赖 agent 当前工作目录。给视频和输出路径加引号；不要把文件名或 JSON 文本当成 shell 指令。

用户已提供 `*-rallycut.json` 时直接走“复用已分析项目”，不必先安装推理环境。分析新视频时先执行只读检查：

```bash
python3 "$SKILL_DIR/scripts/rallycut.py" doctor
```

若未准备环境，阅读 [环境准备](references/setup.md)。经用户允许后显式安装：

```bash
python3 "$SKILL_DIR/scripts/rallycut.py" setup --download-model
```

安装需要 `uv`，运行需要 FFmpeg / FFprobe。推理默认 MPS 优先，无 MPS 时用 CPU；不得在缺权重时静默换成模拟或传统视觉结果。权重独立再分发许可未确认，不打包权重、不上传用户视频。

## 新视频分析

```bash
python3 "$SKILL_DIR/scripts/rallycut.py" analyze \
  --input "/absolute/path/match.mp4" \
  --output "/absolute/path/match.segments.json"
```

- 默认输出精简候选，不剪切、不覆盖原片，也不生成 MP4。
- 标准错误输出 JSONL 进度（带可选 `performance`：已完成帧数、最近/平均画面 FPS，不是原片标称帧率）；标准输出返回完成摘要。`--output -` 则只向 stdout 输出完整结果 JSON。
- 仅在用户需要时加 `--include-tracks`；默认不把大量坐标塞进 agent 上下文。
- 可用 `--min-duration 6` 过滤短候选、`--device cpu` 强制 CPU、`--timeout 3600` 延长任务上限。默认 `--table-mode optional`：正常解码中可选获取桌面几何，不等待、不阻塞、不过滤模型点；`--table-mode off` 完全禁用几何。只有显式 `--table-mode precalibrate` 才运行旧的 600 秒预校准 / 后段跳搜（`--calibration-seconds` / `--calibration-jump-samples` 控制预算，失败也继续整帧检测）。球桌缺失不能拿全画面矩形代替；切镜后不能套用旧几何。分钟级素材可能执行数分钟；使用 agent 后台任务并等待完成，不能将进度消息当完成结果。
- 默认启用有界解码 / MPS 推理 / CPU 后处理流水线，采用 `--precision fp32 --batch-size 4`，无 CUDA 依赖。`--no-pipeline` 可用于顺序对照；仅在用户愿意接受阈值附近结果变化时使用 `--precision fp16`（只支持 MPS，且整条流程不保证更快）。不要擅自把批大小增大到 8 当作优化。
- 默认 `dead-ball-v1`：将疑似出界/台下停滞/手持与再次发球分开；单次回送球不是下一回合，音频不能跨死球区间。保留 `end_reason/end_event_time/end_confidence/boundary_before/start_reason` 和摘要的 `rally_events`。这些仍是规则候选，不代表裁判结论。
- 触网结束仅在网面位置可信时启用；可经用户确认提供 `--net-region LX LT LB RX RT RB` 六个 0–1 坐标。禁止猜网线或把球桌 bbox 中心直接当球网。没有真实触网证据时明确说明，不宣称已解决全部下网。
- 默认 `--decoder opencv`。仅明确要求硬解实验时，在 macOS 执行 `setup --with-decoder` 后加 `--decoder videotoolbox`；必须确认摘要 `hardware_decode: true`。实验色彩转换可能改变轨迹/边界且不保证更快，不能无提示切换或宣称逐位一致。缺依赖/未启用硬解时明确报错，去掉参数回到默认路径。
- 取消时终止运行命令；CLI 清理自有 FFmpeg 进程和临时音频，不发布残缺 JSON。输出已存在时拒绝覆盖，改用新文件名。

## 复用已分析项目

用户已有 `*-rallycut.json` 时，优先避免重复推理；此转换仅需系统 Python 3 + FFprobe，不必安装 PyTorch 或下载权重：

```bash
python3 "$SKILL_DIR/scripts/rallycut.py" from-project \
  --project "/absolute/path/20261024-152433-rallycut.json" \
  --output "/absolute/path/match.segments.json"
```

该命令验证原视频内容指纹，输出当前项目时间轴（含人工修正），并标记 `origin: saved_project_timeline`。它不会应用新死球规则重新切分旧结果；需要修复旧分段时必须重新 `analyze` 或使用已经重新分析的新项目。不能把它描述为重新识别。只接受带已校验 BlurBall 权重来源的项目，拒绝模拟 / 旧传统视觉项目。原片缺失或已变化时明确报错。

## 验收与回复

1. 确认进程退出码为 0，并读取 stdout 完成摘要。
2. 检查结果 `kind == rallycut.segments`、时间单位为秒、时间范围在原片内、`review_required == true`。格式细节见 [输出规范](references/output-schema.md)。
3. 向用户提供 JSON 文件路径、候选数量、采用的新分析 / 项目复用方式，以及关键警告。不要只展示内部轨迹数量。
4. 始终称其为**回合候选**：球检测是预训练模型，回合切分仍含轨迹 / 声音规则；置信度不是准确率，零候选也是真实可接受结果。无独立标注时不能声称准确率、召回率或每个回合均正确。
5. 若用户要真正剪出视频，此 skill 只提供时间表；另行确认编码、缓冲和输出位置，再使用视频导出工具，不能擅自删除原片或执行大批量编码。
