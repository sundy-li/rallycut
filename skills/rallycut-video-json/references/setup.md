# 环境准备与故障处理

## 安装位置

本 skill 的已打包目录包含 `assets/runtime`，不依赖 RallyCut 仓库。将完整目录放入 agent 支持的 skills 目录即可，例如 `~/.agents/skills/rallycut-video-json/`；其他 agent 采用其自己的 skills 路径。`.skill` 文件是 ZIP，可用支持该格式的安装器，或先解压再放置完整目录。不要只复制 SKILL.md。

仓库维护者用 `just skill` 生成 `build/skills/rallycut-video-json/` 和同目录 `.skill` 包。仓库里的 `skills/rallycut-video-json/` 是源模板，不含重复生成的运行时。

## 依赖

`from-project` 转换已有已验证项目只需系统 Python 3 和 FFprobe，无须 uv / PyTorch / 本地权重。以下安装依赖针对新视频 `analyze`。

- 引导命令使用系统 Python 3；`uv` 准备隔离的 Python 3.12 环境。
- `uv` 仅在显式 `setup` 时使用；安装说明：https://docs.astral.sh/uv/ 。
- FFmpeg（含 FFprobe），例如 macOS `brew install ffmpeg uv`，Debian/Ubuntu 使用其包管理器安装 FFmpeg；不要未经授权执行系统级安装。
- `setup` 安装固定版本的 NumPy、OpenCV-headless 和 PyTorch；`setup --download-model` 额外从作者官方地址下载约 6 MB 权重并校验 SHA-256。安装过程不上传视频。
- `doctor` / `analyze` 不联网，不自动安装依赖或下载模型。
- 默认使用 Apple MPS，否则 CPU。当前实测平台为 macOS Apple Silicon；其他平台需运行 doctor / CPU 验证，不能承诺相同速度。

默认缓存位于 macOS `~/Library/Caches/rallycut-video-json/`，其他系统 `$XDG_CACHE_HOME/rallycut-video-json/` 或 `~/.cache/rallycut-video-json/`。运行时按随包源码摘要隔离，权重缓存复用。更新 skill 后可再次显式 setup，准备新版本环境。

## 显式环境变量

- `RALLYCUT_SKILL_HOME`：缓存根目录。
- `RALLYCUT_SKILL_PYTHON`：直接使用一个已有的 Python 可执行文件，须安装相应依赖；不会自动发现本机 RallyCut 仓库。
- `RALLYCUT_MODEL_PATH`：官方固定权重路径；仍执行 SHA-256 校验，不能用任意同名 checkpoint 替换。
- `RALLYCUT_FFMPEG` / `RALLYCUT_FFPROBE`：可执行文件路径。
- `RALLYCUT_INFERENCE_DEVICE`：`auto` / `mps` / `cpu`；其优先级高于 CLI `--device`。

只有用户显式要求复用现有环境时才设这些变量。普通安装不需要它们。

## 失败处理

- **未准备运行时**：显式执行 setup；不要改写 manifest 或跳过校验。
- **缺权重 / 校验失败**：检查 `RALLYCUT_MODEL_PATH`，或执行 setup --download-model。已有校验失败文件不会自动替换，先报告，不擅自删除。
- **未定位球桌**：是合法结果，默认不前置搜索。保留检测/轨迹与候选 JSON，无桌时只降级桌框及几何死球规则；`--table-mode off` 完全跳过几何。不得把全画面矩形当作桌面，也不能无证据声称触网或出界。
- **旧预校准 / 跳搜**：仅 `--table-mode precalibrate` 显式启用。600 秒初始窗口与后段预算可调，失败记录警告后继续整帧检测，不是模型启动条件。默认不进行这些 seek。推理仍需真实 PTS，不能用固定帧率或 seek 目标伪造。
- **可选硬解**：macOS 用 `setup --with-decoder` 安装 `av==16.1.0`，再显式加 `--decoder videotoolbox`；默认安装/doctor 不要求 PyAV。结果必须明确 `hardware_decode: true`。不支持的硬件、缺失 PTS 或未验证的旋转视频会报错，去掉选项改回 OpenCV；不静默回退。硬解色彩转换与默认路径不完全一致，也不保证整体更快，不应对已复核项目擅自切换。
- **推理模式**：默认 `--device auto --precision fp32 --batch-size 4`，优先 MPS，否则 CPU。`--no-pipeline` 关闭解码 / 推理 / 后处理重叠；`--precision fp16` 仅 MPS 可用，CPU 明确报错，不静默忽略。批大小允许 1–8，但越大不一定越快；短片实测 FP32 流水线比 FP16 更快且保持原输出。
- **MPS 不可用 / 内存不足**：经用户同意用 CPU；检查并移除冲突的 `RALLYCUT_INFERENCE_DEVICE` 后传 `--device cpu`。
- **时间戳非单调 / 提前 EOF / 源视频变化**：不输出残缺结果；先核查文件完整性，不按固定 FPS 伪造时间轴。
- **项目复用失败**：原视频必须存在且指纹一致；只支持 BlurBall 项目，不能将旧 mock JSON 重新命名来通过。
- **结果路径已存在**：换新路径；CLI 没有隐式覆盖或强制覆盖开关。

退出码：0 成功；1 运行 / 依赖 / 校验失败；2 参数错误；130 取消。进度写 stderr，完成摘要 / 结果 JSON 写 stdout。

## 许可边界

保留的网络源码及 HRNet notices 随运行时分发。官方 BlurBall 权重单独再分发条款尚未明确：包内没有权重，不宣称商业再分发已获授权。不得在未经用户同意时将视频发送到任何远程推理服务。
