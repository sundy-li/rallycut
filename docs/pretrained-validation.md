# BlurBall 专用预训练模型：接入与 DJI 实测

## 结论与边界

已把默认分析从传统 `classical-av-v1` 切到 **`blurball-pretrained-v1`**。这里确实加载官方训练权重、执行神经网络推理，不是把规则换个名字。

在用户提供的 DJI 原片上，专用模型能定位抽样中的真实小球，包括球网附近的小球、白墙前的运动模糊球、靠近镜头的高位模糊球以及黑沙发前低对比度球。旧传统管线在同一组可确认球帧中没有留下正确的轨迹点。

**不能据此宣称整场 100% 准确。** 本轮只有少量助理目视标注，且一次根据预测提示放大图像后纠正了漏标，明确不是盲测、不是用户确认真值，也不是独立测试集。回合切分仍为规则；147 个候选不等于 147 个正确回合。

## 固定来源、安全与许可

- 代码：https://github.com/cogsys-tuebingen/blurball
- 固定提交：`2f0f5496f7ba4b5b1a36790749935121b2ce972d`
- 论文：https://arxiv.org/abs/2509.18387 （CVSports / CVPRW 2026）
- 权重：作者 README 链接的 Nextcloud `blurball_best`，6,156,034 bytes。
- SHA-256：`3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f`
- 原始网络定义保存在 `vision/vendor/blurball/network.py`，保留 MIT、Microsoft / HRNet notices，另附来源说明。
- **源码 MIT 不等于权重独立再分发许可已明确**。官方共享目录没有单独的权重许可文件。本轮仅为用户请求的本地验证显式下载，不把权重放入 Git、Go embed 或应用包；商业 / 捆绑发布须向作者确认条款。
- 私有视频全程本机处理，没有上传网站、模型仓库或推理服务。
- 使用固定大小 / SHA-256 校验、`torch.load(weights_only=True, map_location='cpu')`、`load_state_dict(strict=True)`；不执行仓库安装脚本、不启用不安全 pickle 回退、不自动下载替代模型。

## 推理实现

- Python 3.12 + PyTorch 2.8.0，macOS 优先 MPS，支持显式 CPU。
- 3 个连续真实帧输入、3 个对应热图输出；step=3，4 个窗口一批。
- BGR 转 RGB、ImageNet 均值 / 标准差、等比 512×288 仿射变换；逆变换回原画面归一化坐标。DJI 原片是 16:9，无额外裁剪变形。
- 训练数据加载器使用 RGB；没有照抄上游独立视频脚本的 BGR 直接送入路径。
- 概率热图阈值 0.7，连通域加权中心定位；热图分数没有校准为准确率。
- 解码时间戳来自实际 PTS；重复帧不喂给多帧模型，末尾不足 3 帧时不通过重复画面补齐。
- 模型候选关联成短轨迹，过滤静止物体和远离球桌区域的点；不再用传统的白度 / 边缘过滤冒充球身份模型。
- 回合仍由轨迹间断状态机与击球声辅助融合；不能把声音单独变成回合。
- 不支持的输入、缺少 PyTorch / 权重、校验失败均显式报错，不自动退回旧规则。旧规则只通过 CLI `--detector classical-av-v1` 显式选择。
- JSONL 结果包含权重摘要、设备、检出帧数。Go 校验模型与请求一致、权重摘要一致；缓存键包含源码摘要和权重摘要，旧模拟 / 规则缓存不复用。

## 整场运行记录

输入：`DJI_20261020161432_0041_D.MP4`，1920×1080，30000/1001 fps，HEVC + AAC，FFprobe 时长 1465.9645 秒。

| 项目 | 实测 |
| --- | ---: |
| 解码 / 模型已评分帧数 | 43,935 / 43,935 |
| 推理设备 | MPS |
| 核心推理 / 跟踪时间 | 522.55 秒，约 8 分 43 秒 |
| ROI 内检出帧数 | 12,307 |
| 已保留候选短轨迹 | 708 |
| 完整音轨声音瞬态 | 1,087 |
| 最终回合候选 | 147 |
| 候选覆盖时长（不含导出缓冲） | 744.695 秒 |

这是吞吐 / 输出统计，**不是精确率或召回率**。首次整场推理保留了逐帧原始检测，随后用完整音轨重放融合；核心网络没有重跑或根据标签调参。最终项目使用完整音轨结果，而非开发时的 180 秒音轨样本。522.55 秒不包括下载 / 环境安装，也不等于完整桌面任务壁钟时间。

另使用原片 26–36 秒的本地转码样本，通过正式 **Go → FFmpeg 音频提取 → 内嵌 Python worker → Go 协议校验 → 项目保存** 跑通，299 帧、11 条轨迹、2 个候选回合。该测试验证部署链路，不把转码样本当原片检测评估。

## 固定抽样目视核对

先固定 24 个时间点，覆盖片头、前 3 分钟、5/6/8/10/12/14/16/18/20/22/24 分钟，再保存无预测标记的原图进行目视核对。

标签在 `tests/fixtures/dji-point-review.json`：

- 6 帧能确认目标球坐标：30、135、360、480、720、1080 秒。
- 11 帧未见目标在打球；地面静止球不作为在打目标。
- 7 帧因持球、遮挡、微小或不清楚而标为 `uncertain`，排除；不是偷偷当作负样本。
- 480 秒最初漏看了黑沙发前的模糊球；预测提示后放大图像确认存在，已公开记录纠标，因此此次样本明确**非盲测**。
- 同一组时间戳、16 原始像素定位容差下，新管线保留轨迹命中 6 帧；旧管线命中 0 帧、错误位置点 2 个。新管线在 11 个可判断未见球帧无预测点。
- 仅作故障排查型样本，不把脚本输出的 `precision=1, recall=1` 当整场结论。必须补充更多未看过预测的标注与逐回合真值，才能计算可信指标。

## 本次可直接查看的产物（本机临时目录，不提交原片）

```text
/tmp/rallycut-blurball/
  DJI-BlurBall.rallycut.json              旧格式历史产物；当前版本不再兼容
  full-analysis.json                    最终完整音轨融合结果
  full-predictions.jsonl                逐帧原始模型输出
  comparison.mp4                        约 50 秒静音左右对照
  comparison.json                       对照视频源片段 / 帧数 / 口径说明
  point-evaluation.json                 原始检测的小样本核对
  classical-tracked-point-evaluation.json
  blurball-tracked-point-evaluation.json
  raw/*.jpg                            无预测标记的抽样原图
```

`comparison.mp4` 左侧是旧传统管线**已保留轨迹点**，右侧是 BlurBall **原始热图检测**，并非等价后处理；用于直观看错漏，不直接拿左右数量比较指标。等价轨迹口径的脚本核对另存上面的两个 JSON。

## 复现

```bash
just setup
just setup-model           # 显式下载，仅本地验证

# 正式管线；原片只读，输出使用新文件名
 go run ./cmd/analyze \
   -input '/absolute/path/match.mp4' \
   -output '/tmp/blurball-analysis.json' \
   -project '/tmp/20261024-152433-rallycut.json'

# 真权重测试：校验、严格载入、有限输出、黑画面不制造球
RALLYCUT_RUN_MODEL_TESTS=1 .venv/bin/python -m unittest discover -s vision/tests -v

# 对已有逐帧结果复算点定位指标，不需要再跑模型
.venv/bin/python vision/evaluate_points.py \
  --labels tests/fixtures/dji-point-review.json \
  --predictions /tmp/rallycut-blurball/full-predictions.jsonl \
  --output /tmp/recomputed-point-evaluation.json
```

模型下载位于 `models/weights/blurball_best.pth`。可设置 `RALLYCUT_MODEL_PATH` / `RALLYCUT_INFERENCE_DEVICE=cpu`；指定其他权重仍会被固定 SHA-256 校验拒绝。Finder 启动时会沿 Python venv 路径查找模型，不要求当前目录是仓库。

## 下一步

1. 用户复核并补充独立球坐标 / 可见性标签，不把模型预测直接当标签。
2. 按每一分标注起止时间，统计漏回合、误保留空白和边界误差。
3. 对发球 / 持球 / 捡球、遮挡和背景邻桌优化时序状态机，优先修正回合切分，而不是仅提高热图数量。
4. 在独立验证集上比较 step=1 重叠推理与当前 step=3，再决定是否接受更高开销；不得用这 24 帧调参后仍当作测试集。
