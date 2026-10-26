# 前 600 秒找不到主球桌后的分层跳搜

> 历史流程，现仅在 `--table-mode precalibrate` 显式启用。默认已改为[整帧检测](full-frame-detection.md)，不等待本搜索；搜索失败也不阻止模型检测。

## 策略

1. 保留原初始窗口：默认 600 视频秒，前 30 秒每秒取一帧，其后每 5 秒一帧。稳定时提前结束，不必扫描满 600。
2. 仍找不到且存在足够后段时长，重新打开用于校准的 capture，进入跳搜。先看初始窗口后不远处、余下区间中点和末尾，再按广度优先二分填补大空隙（四分点、八分点等）。不会沿一个小区间一直细找而漏掉远处。
3. 每个锚点先看邻近 `-1 / 0 / +1` 秒。发现可疑候选但未确认时，再看 `-2 / +2` 秒。至少 3 个不同实际 PTS、足够时间跨度、相同主桌且无多桌歧义才确认。
4. 一致性只在当前局部窗口投票，不把前 600 秒或相隔几分钟的弱命中拼起来。网面证据也只使用当前命中窗口。
5. 稳定后返回近似 ROI；正式推理仍重新打开视频，从原片 0 秒开始，不丢掉开头回合。

## 预算与失败

- 默认额外最多 **96 次新采样**；没有细查时最多 32 个锚点，有细查时窗口数相应减少。
- `--calibration-jump-samples 0..384` 可调，0 禁用后段跳搜，最大 384 请求 / 128 窗口。请求缓存避免重复 seek；同一实际 PTS 不能算多个观察。
- 后段设 60 秒检查预算，在底层读取之间及局部收集后检查；不能保证强制中断单次长时间阻塞的 C 解码调用。外层任务超时/取消仍有效。
- 初始窗口 seek 不支持时保留旧的顺序重校准；**后段**无法可靠跳转则明确失败，不偷偷顺扫整段几小时视频，不新启动 FFmpeg 子进程。
- 读出的 PTS 必须与目标足够接近，按真实时间做一致性判断，不能以计划位置伪造观察。尾部邻域向内平移，避免三个请求被夹成同一个尾帧。
- 帧预算 / 时间预算 / 锚点用尽时说明原因。`最远检查到 X 秒` 不表示 `0–X` 连续覆盖；不保证检出任意短暂镜头。
- 找到晚期球桌不证明前段机位相同。摘要保留校准来源时间并警告可能需要分场景 / 人工标定，不把未知场景强行认成同一个球桌。

## 用法

默认不运行本流程。需要显式旧搜索时，CLI / skill：

```bash
python3 "$SKILL_DIR/scripts/rallycut.py" analyze \
  --input /path/match.mp4 --output /path/result.json \
  --table-mode precalibrate --calibration-seconds 600 --calibration-jump-samples 96
```

`calibration-seconds` 现在是**初始窗口**。若要严格只检查前 30 秒，应同时使用 `--calibration-seconds 30 --calibration-jump-samples 0`。

## 摘要与缓存

沿用初始窗口的 `calibration_search_seconds`；`calibration_sampled_frames` 计总检查量，策略可为：

- `seek_sparse` / `sequential_fallback`：初始窗口找到。
- `seek_sparse_then_jump` / `sequential_fallback_then_jump`：经后段局部确认找到。

另保留 `calibration_jump_samples`、`calibration_jump_windows`、`calibration_jump_budget`、`calibration_search_extent_seconds`，原支撑 `first_evidence / last_evidence` 仍是真实 PTS。新 helper 已加入 Go 内嵌与独立 skill，源码摘要自动隔离旧成功缓存；检测权重不变。

## 验证

### 确定性测试

覆盖分层次序、巨大时间区间的有限计划、尾部三时刻、局部三点确认、五点细查、单帧偶然命中、同帧重复、不能跨分钟凑票、多桌歧义、帧/墙钟预算、取消释放、seek 错误不顺扫全片、原早停兼容及神经推理从第 0 帧开始。

### 明确合成的视频解码回归

本机生成 900 秒 / 5fps 视频：前 700 秒纯黑，仅在 700–720 秒放入用户 `0044` 原片第 8 秒的桌面画面，后段再黑。这是**校准调度合成例，不是真实比赛、也不是模型准确率测量**。

真实 OpenCV / FFmpeg 解码结果：

- 初始 145 次检查未找到。
- 7 个后段窗口、21 次新采样后，在真实 PTS 711.4 / 712.4 / 713.4 秒形成稳定确认。
- 总共 166 次检查，返回 `perspective-rims` 主桌区域；没有顺扫 900 秒中间全部帧。
- 此低帧率、静态低码率合成例约 0.47 秒，不可作为实际 HEVC / 4K 的耗时承诺。
- `/tmp/rallycut-jump-search/synthetic-delayed-table-900s.mp4` 与 `synthetic-result.json` 保存原始结果。

```bash
RALLYCUT_JUMP_SYNTHETIC_VIDEO=/tmp/rallycut-jump-search/synthetic-delayed-table-900s.mp4 \
  .venv/bin/python -m unittest discover -s vision/tests -p 'test_table*.py' -v
```

另回归已有 0044 原片：开头稳定时仍提前结束，`jump_samples=0`，没有让常见素材每次都遍历后段。没有新完整比赛准确率验收。
