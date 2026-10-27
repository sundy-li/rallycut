# 首次启动：检测、确认与环境准备

本页说明当前源码中的新流程。**尚未重新发布安装包；公开下载的 `v0.1.0-alpha.2` 仍按原安装指南操作。** 网站和旧 Release 不会因源码修改自动更新。

## 用户看到的流程

1. 安装并打开 RallyCut，显示“正在检查运行环境”。此时只运行本地检测，不下载、不安装。
2. 已具备全部依赖时，直接进入项目列表；不是直接打开上次的剪辑工作台。
3. 缺少依赖时，显示当前平台、已就绪与缺少的项目，以及下载、空间和隐私说明。
4. 用户点击 **“开始准备环境”** 后，应用自动准备缺少项：Python → 视频处理工具 → 视觉依赖 → 模型 → 自检。
5. 自检全部通过才显示 100%，自动进入项目列表。失败留在准备页，显示原因，支持“重试准备环境”或“重新检测”。

**环境没有准备好，不能新建、打开、导入或进入剪辑界面。** 页面没有跳过按钮；快捷键和原生菜单也不会绕过门禁。后端同样检查状态，而不只是前端隐藏工作台。

## 安装到哪里

都放在用户的 RallyCut 数据目录中，不需要管理员权限，不替换系统 Python，不修改全局 PATH，不向 Windows 注册系统 Python：

```text
runtime/
  python/       自动下载的独立 Python（仅在缺少兼容解释器时）
  venv/         应用自己的 Python 依赖
  tools/        固定版本 uv，用于安装独立 Python
  bin/          自动下载的 FFmpeg / FFprobe
  notices/      视频工具的许可证与来源说明
  downloads/    已校验的下载缓存，重试可复用
  cache/        准备工具的私有缓存
models/weights/ 模型权重，不随安装包捆绑
```

macOS 默认在 `~/Library/Application Support/RallyCut`；Windows 在当前用户配置目录下的 `RallyCut`。`RALLYCUT_DATA_DIR` 可以显式覆盖。开发者显式的 `RALLYCUT_PYTHON3`、`RALLYCUT_FFMPEG`、`RALLYCUT_FFPROBE` 继续优先；错误覆盖会导致自检失败，不能静默忽略配置。

若本机已有兼容的 Python 3.10–3.12，可复用它创建私有 venv；完全缺少时，下载固定的 Python 3.12.12。已有完整、可用的开发环境可以通过检测，不必重复安装。视频工具也优先复用可运行的现有安装，之后统一通过 `media.Binary` 查找，不依赖 Finder / Explorer 提供开发者 PATH。

## 平台差异

| 目标 | 运行时 | 视觉依赖 |
| --- | --- | --- |
| macOS Apple Silicon | arm64 | NumPy 2.2.6、PyTorch 2.8.0 |
| macOS Intel | x86_64 | NumPy 1.26.4、PyTorch 2.2.2：上游不提供 Intel Mac 的 PyTorch 2.8 wheel |
| Windows x64 | amd64 | NumPy 2.2.6、PyTorch 2.8.0，另安装 Windows 的 DirectML 依赖；是否实际启用加速仍取决于模型产物与驱动 |

OpenCV 固定 4.11.0.86。不支持的系统／架构会明确失败，不安装不匹配的二进制。Windows WebView2 是原生窗口的启动前提：缺少／过旧时，Wails 默认引导器先显示中文确认提示，用户允许后由微软引导安装器处理，取消则不启动。它发生在应用窗口之前，**不能把它说成应用内进度条的一部分**；应用内的准备页处理其余依赖。

## 下载、进度与失败处理

- uv 0.9.5 与平台视频工具由 `backend/setup/artifacts.json` 固定 URL、体积和 SHA-256；下载大小与哈希不匹配时不执行。Python 的独立发行包由 uv 的固定下载清单获取、校验。
- FFmpeg / FFprobe 使用 `eugeneware/ffmpeg-static` 的 b6.1.1 平台构建，不是将其说成 FFmpeg 项目官方二进制；许可证与构建来源说明也按哈希保存。详见 [licenses.md](licenses.md)。
- Python wheels 从包索引安装；核心依赖固定版本，Windows DirectML 沿用版本范围，传递依赖尚未做完整 hash lock，不声称全部 wheel 已固定哈希。
- 模型从清单中的原始来源下载，检查体积、SHA-256 与 PyTorch / NumPy 数据互通；不使用模拟结果，不自动上传素材。
- 文件下载有字节进度；安装 wheel、独立 Python 和自检阶段无法获取可靠总量，显示阶段进度及“当前步骤处理中”，不伪造逐字节百分比或剩余时间。
- 不再承诺“1–3 分钟”。网络、平台与依赖缓存会影响下载量和时间，可能数百 MB 至数 GB；界面建议预留至少 5 GB，实际需求随平台变化。
- 失败不显示 100%，不放行；连续点击只启动一个准备任务。关闭应用会取消准备并回收子进程，下次重新检测，可重用已完成且通过校验的文件。
- 状态带单调递增 `revision`，前端忽略迟到的旧状态，防止旧的 `running` 响应覆盖已完成状态。
- 下载源不可达时仍会失败；自动准备不等于内置国内镜像、断网安装或有速度保证。下载服务可能记录访问日志。

## 维护入口与验证

- 后端：`backend/setup/{setup.go,artifacts.go,artifacts.json}`。
- 启动与 API 门禁：`backend/app.go`；视频工具路径：`backend/media/probe.go`。
- 界面：`SetupScreen.tsx`、`lib/setup.ts`、`App.tsx`。
- 默认单测：检测不安装、单任务重试、失败门禁、阶段进度、旧响应、下载大小、压缩包路径／链接拒绝、缓存完整性、平台依赖和许可清单。
- UI fixture：`tests/ui/test_setup.py`，检查确认按钮、失败重试、窄窗口、快捷键门禁与乱序 RPC；不是 Windows 真机或原生桥接验收。

真实下载测试使用全新临时目录并强制不复用主机 Python / FFmpeg：

```bash
RALLYCUT_SETUP_E2E=1 go test -v ./backend/setup \
  -run '^TestProvisionerInstallsRuntime$' -count=1 -timeout 18m
```

本次在 Apple Silicon 上执行上述测试：独立 Python、FFmpeg / FFprobe、基础包、PyTorch、模型下载和自检通过。该次约 36 秒仅是当次网络与机器的记录，**不是用户安装时长承诺**。Windows 与 Intel Mac 的原生、无依赖机器首启仍待验证，不能把平台资源存在或交叉编译通过等同于真机验收。
