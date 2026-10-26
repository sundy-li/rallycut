# 处理 FPS、预处理优化与 VideoToolbox A/B

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
