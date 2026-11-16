# 处理 FPS、预处理优化与 VideoToolbox A/B

## 2026-11：实时预览限额与 Apple silicon Core ML

同一场 50 分钟观众视角比赛（1080p H.264，93,081 个分析帧），M5 Max，同一驱动脚本模拟桌面 worker（含实时候选回调与 JSON 序列化，不含声音融合与 Go 指纹校验）。每行是一次新进程整场运行；单次测量，温度与后台负载会带来几个百分点波动。

| 版本 | 墙钟 | 画面 FPS | 前向 | 解码线程 | 后处理线程 | 实时预览重算 |
|---|---:|---:|---:|---:|---:|---|
| 旧：每 2 秒视频全量重算预览，MPS FP32 | 586.9 s | 158.8 | 585.6 s | 496.3 s | 273.9 s | 1,108 次请求全部重算 |
| 新：预览按耗时限额，MPS FP32 | 543.3 s | 171.8 | 531.6 s | 518.9 s | 63.2 s | 135 次，共 17.1 s |
| 新：预览限额 + Core ML FP16 | 426.4 s | 219.5 | 166.5 s | 424.0 s | 44.2 s | 156 次，共 13.2 s |
| 新：再把 Core ML 放进子进程（`coreml_process.py`） | 237.6 s | 394.5 | 162.5 s | 235.8 s | 33.7 s | 116 次，共 7.5 s |

- **预览限额**（`neural_analysis.LiveRefresh`）：`TrackingStage.rallies()` 每次从头重分全部轨迹，用 L0 缓存重放整场测得单次从约 30 ms 涨到约 190 ms，每 2 秒视频调用一次累计约 175 s 纯 Python CPU。现在每次重算后等待其耗时的 30 倍再重算，期间重发上一份预览；新轨迹与球桌框照常即时发送。整场墙钟 586.9 → 543.3 s（约 7%），后处理线程 274 → 63 s。最终回合由 `finish()` 一次算出，新旧回合列表逐项相同（97 个）。
- **Core ML**：前向 531.6 → 166.5 s（3.2 倍），整场 543.3 → 426.4 s。此后墙钟由解码线程决定：单独解码 + 缩放约 1.9 ms/帧，流水线里约 4.5 ms/帧，下一步应查解码线程的争用（GIL、主线程 `prepare_input` 的 float64 归一化）或按关键帧分段并行解码；本次未改。
- **Core ML 子进程**：进程内 coremltools `predict()` 与解码线程争 GIL。前 120 秒实测：模型换成同样时长的 `sleep` 时解码线程约 521 帧/秒，真跑 Core ML 只有 327；模型放到另一进程时约 440–476。现在 `backends.create_backend` 默认启动子进程：父进程把 uint8 RGB 窗口写入共享内存，子进程用同一个 `pretrained.normalize_input` 归一化、同一个 `CoreMLBackend` 推理，所以热图与进程内逐位相同（两段 120 秒片段的原始检测点逐字节相同；整场 97 个回合与 1,321 条轨迹相同；6 个标注视频重新 `eval cache --runtime coreml` 后，原始检测点与进程内 Core ML 缓存逐帧相同，MPS 与 Core ML 两套回测仍与 v17 一致）。子进程在 stdin 关闭时退出；父进程被强杀时子进程退出、共享内存由 resource tracker 回收（已实测）。`RALLYCUT_COREML_INPROCESS=1` 可回到进程内；子进程启动失败时自动退回进程内。
- 合计同一场比赛 586.9 → 237.6 s（-60%）。DJI HEVC 片段（0044 前 120 秒）只从 149 提到 169 帧/秒：HEVC 软件解码本身约 211 帧/秒，已是瓶颈。桌面版此前实际记录为 749 s（含声音、指纹与界面开销），新版桌面整场未实测。

### 为什么没有用 Rust（2026-11 评估）

剩下的耗时都在已经是原生代码的库里：FFmpeg 解码（H.264 1080p 约 1.4 ms/帧，HEVC 约 4.7 ms/帧，已多线程）、OpenCV 缩放（0.45 ms/帧）、Core ML 前向。逐帧 Python 胶水（切镜监视 0.13 ms/帧、跟踪 `observe` 整场 0.2 s）占比很小；实时预览的二次方开销已经按耗时限额解决。用 Rust 重写这些部分不会让 FFmpeg / Core ML 更快，反而要给 macOS universal、Windows 和 skill 各编一份原生扩展，并维护第二份算法。真正的收益来自让原生调用不互相等待（子进程）。以后若要再提速，方向是 HEVC 硬件解码（颜色转换与 OpenCV 不同，需完整回测）或按关键帧分段并行（切镜 / 跟踪状态跨段衔接需要设计），与语言无关。

Core ML 是否等价，以全部 6 个标注视频的新鲜推理为准（`just eval cache --runtime torch` 与 `--runtime coreml` 各一次，再 `eval run [--backend coreml] --compare v17 --gate`）：

- 两个后端的打分与 v17 完全相同：244 / 3 / 11，F1 0.972，每个视频各项为 +0。
- 检测层面不是逐位一致：各视频 0.04–0.10% 的帧检出点数不同，已匹配点最大偏移约 2 px（fzd 有一处 20.6 px）。
- 回合候选：0043、he 完全相同；其余视频 1–4 个候选边界移动，多数 ≤0.2 s，fzd 有一个起点提前 4.8 s（39:54，标注范围外）、0044 有一个移动 1.0 s（17:04，范围外）。标注范围内没有任何变化。
- 结论：Apple silicon 桌面版默认使用通过校验的本机 Core ML 包；它是 FP16 数值模式，不宣称与 MPS 逐位相同，标注范围外的结果仍需人工复核。

## 这次交付

- 素材栏明确标为“素材 29.97 fps”，不再让它看起来像分析速度。
- 任务进度显示最近 / 平均画面处理 FPS、已完成分析帧数；另有**任务均速**，把指纹校验、音轨提取、加载和校准也算进墙钟。
- 完成记录保留 `processing_fps`、`analysis_fps`、分阶段耗时、解码器身份。旧项目缺字段时显示“未记录”或根据已有合法计时计算，不编造实时数据。
- 先仿射缩放 BGR，再在 512×288 上转 RGB。随机图、不同纵横比/4K/奇数尺寸及真实短片的输入和默认 FP32 检测输出均已验证一致。
- VideoToolbox **仅为显式实验选项**；默认仍为 OpenCV。不会把软件回退谎报成硬解。
- 桌面 worker 现在按源码 digest 隔离目录并原子安装，避免开发版/旧独立版互相覆盖 Python 文件。

## FPS 口径

| 名称 | 分子 | 分母 |
|---|---|---|
| 素材 FPS | 原片帧数 | 原片时间；只是 ffprobe 元数据 |
| 最近画面 FPS | 两次采样之间完成后处理的分析帧数 | 实际单调时钟间隔 |
| 平均画面 FPS | 完成解码/预处理/推理/后处理的分析帧数 | 画面流水线墙钟；含首批 GPU 开销，不含模型加载/校准/提音轨 |
| 分析平均 | 完成的分析帧数 | Python 核心流程墙钟；含加载、校准、声音融合，不含 Go 指纹校验及外部提音轨 |
| 任务均速 | 当前完成的分析帧数 | 后台任务启动后的墙钟；包含准备与进度存盘开销 |

跳过重复帧、末尾不完整三帧窗口不算已完成分析帧。空检测帧仍然计数。命中缓存时没有新的推理统计，不能用缓存读取时间伪造超高模型 FPS。取消/完成后冻结最后统计，不继续显示一个跳动的“当前 FPS”。阶段时间有重叠，不能相加当总耗时。

## 剩余时间与首屏读数

`预计还需` 由进度（`timestamp/duration*0.94`）与任务墙钟线性外推，含准备阶段；进度低于 2% 或任务不到 15 秒时不显示，避免两帧样本给出离谱时间。格式只到分钟（`约 55 分钟` / `约 1 小时 20 分钟`），不承诺秒级精度。

第一个采样发生在模型加载之后、只有 1 帧，直接显示会变成“0.1 FPS”并让慢机器看起来卡死。因此 `已处理 < 20 帧` 或流水线不足 5 秒时，速度显示为“统计中…”，不显示最近 FPS 与均速。Windows CPU 推理（尤其 ARM 虚拟机里的 x64 程序）本来就比 Apple 芯片慢一个数量级，界面只陈述实测值，不美化。

性能字段随原有 JSONL progress 发送，不额外产生事件/项目 fsync；缺失字段的旧 worker 协议仍兼容。

## 默认预处理：有局部收益，不声称大幅提速

1080p 的 BGR→RGB 从 1920×1080 改到 512×288，颜色转换像素量约缩小 14 倍，但解码没变，整体不是 14 倍。原仿射采样网格、插值和 RGB 归一化不变。

交替微基准（单线程 OpenCV，同 10 帧，300 次/轮）：

| 次序 | 原路径 | 新路径 |
|---|---:|---:|
| 第一轮 | 0.496 ms/帧 | 0.479 ms/帧 |
| 反向复测 | 0.491 ms/帧 | 0.476 ms/帧 |

端到端短样本受解码/温度/后台任务影响，没有稳定额外加速，不将此次小改包装成新的倍数提升。默认 FP32 两段对照的坐标、热图分数、保留轨迹和回合均与冻结基线一致；这只是输出一致性，不是人工真值准确率。

## VideoToolbox 实验与决策

可复现脚本：

```bash
uv pip install --python .venv/bin/python -r vision/requirements-decode.txt
.venv/bin/python scripts/benchmark_decode.py \
  --video /path/to/first.mp4 --video /path/to/second.mp4 \
  --output /tmp/rallycut-decoder-ab
```

对照 OpenCV、PyAV 软件解码及 PyAV VideoToolbox。硬解使用 `allow_software_fallback=False` 并核验 `codec_context.is_hwaccel`、`videotoolbox_vld` surface；使用真实 PTS / time_base，绝不拿帧号除以 30。当前旋转输入未验证，实验模式拒绝并提示用默认 OpenCV。

脚本为隔离解码影响复用同一份球桌校准；**应比较 `pipeline_timings.wall_seconds` / `processing_fps`，不能把脚本中复用校准后的核心计时当完整桌面任务用时**。音轨提取不在实验计时中。

| 实际 HEVC 样本 | OpenCV 画面 FPS | VideoToolbox 画面 FPS |
|---|---:|---:|
| 约 10 秒，第一轮 | 147.38 | 157.67 |
| 约 30 秒，第一轮 | 145.86 | 184.46 |
| 约 10 秒，最终复测 | 142.46 | 135.27 |
| 约 30 秒，最终复测 | 151.43 | 144.78 |

第一轮有收益，复测未稳定重现，不能宣传硬解固定提升。软件 PyAV 的 30 秒样本反而只有约 78–85 FPS，证明“换库”不等于变快。

质量检查：两条解码路径帧数一致，PTS 最大误差约 `7.1e-15s`；但 PyAV 与 OpenCV 使用不同 FFmpeg/色彩转换，抽样 BGR 像素平均绝对差约 0.077–0.166（0–255 尺度）。两段分别有 5 / 7 个已评分帧的检测数量变化，匹配点最大偏差约 2.05 / 3.86 个原始像素，轨迹均有变化，10 秒片段回合边界也有变化。没有独立标注，不能据此断言变好或变坏。

**结论：保留 OpenCV 默认；VideoToolbox 显式 opt-in，标记实验/需复核。** 不把硬件识别、RGB 近似和 FPS 提升混为一谈，不改变默认 FP32 精度与完整时序。

## CLI / skill 使用

```bash
# 默认，稳定的已验证输入语义
.venv/bin/python vision/headless.py analyze --input /path/match.mp4 --output /path/result.json

# 显式实验（macOS + 可选 PyAV）
.venv/bin/python vision/headless.py analyze --input /path/match.mp4 \
  --output /path/result-hw.json --decoder videotoolbox

# 独立 skill
python3 "$SKILL_DIR/scripts/rallycut.py" setup --with-decoder
python3 "$SKILL_DIR/scripts/rallycut.py" analyze --input /path/match.mp4 \
  --output /path/result-hw.json --decoder videotoolbox
```

结果中必须有 `decoder: videotoolbox` / `hardware_decode: true` 才能称为已启用硬解。失败时明确报错，用户可去掉选项重试默认 OpenCV，不静默换成软件却仍标硬件。可选 PyAV 不影响默认 doctor/安装，不随 skill 打包二进制依赖或权重。原片只读、不上传、不生成有损代理。

完整原始测试数据留在本机 `/tmp/rallycut-throughput/`，仓库中的 `docs/reports/throughput.json` 只保留脱敏摘要。短样本不能保证整场速度；本次未重跑整段 25 分钟比赛。
