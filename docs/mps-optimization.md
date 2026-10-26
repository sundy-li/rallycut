# 接入本地 BlurBall MPS 流水线优化

## 来源与边界

只读检查 `~/work/blurball`，包含本地提交 `108e4f3902d3665a8cdb6ab637c1b3946e929b4e` 及检查时尚未提交的 detector / runner / postprocessor 修改；最终核对时作者已将相同文件提交为 `f895ffdce459bf9ae0bfb5a0cb4ef5d1746ee5fc`，输入哈希未改变。输入文件 SHA-256 已记录到 `models/manifest.json`，**未修改该仓库**，运行 RallyCut / skill 也不依赖它。

网络定义与当前 vendored 模型逐字一致；本地与 RallyCut 官方权重 SHA-256 也相同。原先 RallyCut 已支持 MPS，这次真正移植 / 适配的是流式分工、批量归一化、CPU 后处理拆分和可选半精度，不是把已有 CPU 推理简单改名成 MPS。

## 实施

- `vision/inference_pipeline.py`：有界解码队列 → **主线程 GPU** → 有序 CPU 后处理队列，两侧队列各最多 2 个 batch。错误跨线程传播，取消时通知队列停止、关闭生成器 / 解码器；不会像无条件 Queue.put/get 或 join 那样挂死。
- `vision/pretrained.py`：先准备 uint8 RGB CHW，再一次性构造 batch、FP32 原地归一化。输入暂存降为原 FP32 的四分之一；保留已有 RGB / affine / letterbox 坐标，不直接复制本地入口的 BGR resize 路径。单元测试验证批量归一化与旧版逐位一致。
- 模型前向与 CPU connected components 拆分；空检测帧仍按原顺序进入轨迹关联，不能只保留“有球的帧”再改写时间。
- 默认 **MPS 优先 / FP32 / batch=4 / pipeline=true**。CPU 不要求 CUDA；MPS 失败不会静默改成另一种检测器。
- 显式 `--precision fp16` 仅 MPS 可用，模型 / 输入使用 FP16、logits 的 sigmoid 使用 FP32；它不是默认，也不是保证更快的开关。
- `--batch-size 1..8`、`--no-pipeline` 用于控制与诊断；增大 batch 不保证更快。
- 保留原始解码 PTS、去重和不完整三帧尾部处理。不得用 `int(fps)` 或重新编号的 CSV 行号替代原片时间轴。
- 权重大小 / SHA-256、`weights_only=True`、strict state_dict、人工编辑不覆盖和模型许可限制不变。
- 摘要保存设备、精度、batch、流水线模式与阶段计时，桌面列表中显示这些模式；Go 深拷贝性能元数据，避免快照相互修改。

## 同素材对照

两段先前已验证的真实 1080p HEVC 比赛片；固定相同权重、RGB、0.7 阈值、step=3、batch=4。各模式新进程、同精度前向预热；时间包含校准 / 模型初始化 / 解码 / 推理 / 后处理，**不含音轨提取**，音频融合在本轮性能对照中关闭。以下为后一次预热对照；重复测量存在温度 / 缓存 / 调度波动，不能外推整场耗时。

| 片段 / 帧数 | 原版 | 新版 FP32 顺序 | 新版 FP32 流水线 | 新版 FP16 流水线 |
|---|---:|---:|---:|---:|
| `bridge-smoke`，299 帧 | 3.982s | 3.461s | **2.353s** | 2.363s |
| `repro-first30`，900 帧 | 11.115s | 9.927s | **6.911s** | 6.974s |

默认 FP32 流水线在这次对照约为 **1.61–1.69×**；前一次测量为 1.56–1.60×。两轮均得到：

- 所有已评分帧的 frame_index / PTS 顺序完全一致（297 / 900 帧；短片末尾 2 帧保持不评分）。
- FP32 的检测数量、坐标、热图分数、保留轨迹与回合列表均与原版一致；最大坐标 / 分数差为 0。
- FP16 分别有 2 / 1 帧的检测数量发生变化，已匹配点的最大位置差约 1.84 个原始像素；短片的一个轨迹和部分回合字段发生变化。它是数值模式差异，不能声称等价或更准确。
- FP16 虽然缩短了前向耗时，整条流水线仍主要受 HEVC 解码 / 预处理限制，未获得额外整体收益，因此不设为默认。

额外前向微基准（不是完整管线）：FP32 batch4≈139 fps、batch8≈99 fps；FP16 batch4≈174 fps、batch8≈171 fps。这也是未直接复制 batch8 默认值的原因。温度 / 缓存影响下，不要把此数字当作长期吞吐承诺。

这只是**输出一致性与性能测试**，不是独立真值准确率评估。本次没有重新执行整段约 25 分钟的模型分析。

原始报告与逐帧结果在 `/tmp/rallycut-mps-opt/warm-comparison/`；首轮在 `comparison/`。`/tmp/blurball_test_clip.mp4` 的 DJI 数据轨让容器比实际可解码视频更长，触发原有提前 EOF 防护，未计入有效性能对照，也没有放宽防护来凑测试结果。

## 复现

固定旧版 `vision` 源码快照后：

```bash
.venv/bin/python scripts/benchmark_mps.py \
  --baseline /absolute/frozen-vision \
  --video /absolute/real-clip.mp4 \
  --output /tmp/rallycut-benchmark
```

`benchmark_mps.py` 保存逐帧检测并比较同源帧坐标、分数、轨迹和回合；输入不完整时明确失败，不能报告速度。

桌面默认即使用新流水线，重启后点击分析。skill 更新包：

```bash
just skill
python3 build/skills/rallycut-video-json/scripts/rallycut.py analyze \
  --input /absolute/match.mp4 --output /absolute/new.segments.json \
  --device mps --precision fp32 --batch-size 4
```

仅用于对照时加 `--no-pipeline`，仅经用户明确选择时用 `--precision fp16`。源码摘要已变化，旧模型分析缓存自动失效；新格式 `*-rallycut.json` 项目仍可打开，非空人工时间轴仍受保护；旧版项目文件不再兼容。
