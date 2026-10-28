# 开发与测试

普通用户先看[安装与快速开始](getting-started.zh-CN.md)。这里记录维护者需要的环境、命令和实现边界；算法成绩与实验在[实验记录](experiments.md)。

## 技术结构

Go + Wails v2 桌面宿主、React / TypeScript 界面、Python JSON Lines 分析、FFmpeg 导出。`vision/` 是桌面与独立 skill 共用的唯一运行时；不要手工修改应用数据目录或 `build/skills` 中生成的副本。

- `backend/project`：项目、原始分析与人工回合，按素材保存轨迹。
- `backend/timeline`：剪辑缓冲、重叠优先级、输出片段与回合编号。
- `backend/export`：FFmpeg 编码、逐帧轨迹与编号叠加、不覆盖输出、取消和结果核验。
- `frontend/src/lib/shortcuts.ts`：快捷键表与说明的单一来源。
- `backend/menu.go`：原生菜单与界面事件。菜单只在 macOS 构建；Windows 没有原生菜单，退出入口是界面右上角的电源按钮（`App.tsx` `requestQuit`）。Windows 窗口使用 `GetMonitorInfoW.rcWork` 的真实工作区、物理像素和当前窗口 DPI，先调整 Wails 最小尺寸再放置；几何计算在 `backend/window.go`，原生调用在 `backend/window_windows.go`，不套用到 macOS 坐标系。
- `backend/setup`：用户确认后准备平台运行环境，首次启动门禁与进度；见[首次环境准备](first-run-setup.md)。
- `vision/neural_analysis.py`：分析管线与共享 TrackingStage。

完整结构见[架构](architecture.md)、[协议](protocol.md)和仓库 `AGENTS.md`。

## 环境与日常命令

主要开发平台为 macOS / Apple Silicon，需要 Xcode Command Line Tools、Go 1.24+、Node.js 22、uv、Python 3.12、FFmpeg / FFprobe、just。Wails CLI 使用 `v2.16.0`。

```bash
go install github.com/wailsapp/wails/v2/cmd/wails@v2.16.0
just setup
just doctor
just dev
```

首次实际运行模型可显式准备依赖与权重：

```bash
just setup-model
```

权重不提交、不打入应用或 skill。`just dev-web` 只有浏览器界面，没有本地 Go 文件能力，不等价于原生体验。

## 测试与构建

```bash
just test                 # 前端构建、Go race、Python、skill、前端单测
just test-go
just test-skill
just skill
just build                # 独立生产版 build/release/RallyCut.app
just run
```

`wails dev` 会覆盖 `build/bin`。不要从该路径拿开发包发布，也不要与同一工作树的生产打包并行。当前有开发实例时在 CI 或独立工作树打包，不要杀用户的开发进程。

浏览器回归见 `tests/ui/test_setup.py`（首次确认、进度、门禁、重试与乱序事件）和 `tests/ui/test_workbench.py`（工作台），原生检查见 `tests/desktop/`。前者使用内存 Wails fixture，不能冒充真实文件桥接或模型验收。私有素材测试需显式开启，普通 CI 不依赖私有视频、权重、项目或 `/tmp` 既有产物。

## 编辑与导出语义

- 项目自动保存，编辑支持会话内撤销／重做；切换项目、素材、分析完成时清空历史。导出设置与素材管理不进入撤销。
- 重分析替换未编辑机器回合，保留人工添加与修正回合，也保留与人工重叠的新候选。被取消选择的匹配机器候选继续保持取消选择；人工删除没有持久墓碑。
- 重叠策略在导出阶段解析：人工优先、机器优先、合并、先后，不回写时间轴。同来源重叠自动合并。
- 预览与导出叠加各自开关。导出按素材坐标绘制 RGBA 透明图层，再交 FFmpeg overlay 合成；轨迹使用短拖尾与球点圆圈，不画 `off_play`。
- 回合编号来自实际输出计划，在合并片段内部按回合切换。使用系统中文字体，不依赖 FFmpeg drawtext；无可用字体必须报错。
- macOS 优先 VideoToolbox 硬编，失败则整批软件重做。H.264 是兼容性优先选择；HEVC 需要对应编码器。
- 输出默认拒绝覆盖原片或已有文件，取消与失败不发布半成品。导出后检查时长、编码、音轨；主观音画同步仍需回放。

## 独立视频 → JSON skill

```bash
just skill
```

完整发行目录为 `build/skills/rallycut-video-json/`，可复制到仓库外运行，不依赖 Go / Node / Wails。用户显式准备模型后离线分析；`from-project` 是项目转换，不是最新模型重跑。操作说明见 [skill 规范](../skills/rallycut-video-json/SKILL.md)。

## Windows 本地构建与平台回归

在 Windows 安装 Go 1.25+、Node.js 22 与 Wails CLI v2.16.0，然后运行：

```powershell
./scripts/build-windows.ps1
# 可指定 Go/Wails 路径及输出 EXE；不需要 GCC/cgo。
./scripts/build-windows.ps1 -Go 'C:\Program Files\Go\bin\go.exe' -Out 'build\bin\RallyCut.exe'
```

脚本执行锁文件依赖安装和标准 Wails 构建，不能假设 `frontend/dist` 已提交；构建后检查首页与 JS 产物。Wails 同时生成 DPI manifest、图标、版本资源。`-Out` 相对仓库根目录解析，`-Go` 的 PATH 调整只在脚本进程中有效，退出时恢复。

图标来自仓库中的 `build/appicon.png`（由 `design/logo/final/rallycut-appicon-1024.png` 复制），必须随仓库保留，否则 Wails 会退回通用图标。`wails.json` 的 `info` 段提供产品名、版本与版权；Windows 文件版本号必须是纯数字（当前 `0.1.0`），alpha 标识写进 `comments`，否则资源管理器里的版本属性不可读。

桌面端启用单实例锁：再次启动只唤醒已有窗口，避免两个进程同时写同一项目 JSON 与分析缓存。Windows 默认最小窗口为 960×600 DIP；更小工作区按实际 DPI 动态降低最小尺寸，界面同时使用 950／660 断点下的紧凑布局。

此脚本只生成程序 EXE，不下载或分发完整运行环境。完整安装器走 `Windows preview` workflow。开发 EXE 要复用已安装环境，需放在与嵌入的 `bundled-id` 对应的 `runtimes/<id>/` 同级目录；请先退出旧窗口，不覆盖运行中的程序。没有嵌入归档清单但已有展开环境时，仍逐文件校验本地 manifest，缺模型只补模型，不创建第二套 venv／执行 pip。正式发布仍保留嵌入清单的固定哈希约束。

`Test` workflow 的 Windows job 从干净检出运行上述脚本，检查 EXE 的 DPI manifest／图标／版本资源和嵌入前端；执行真实 Job Object 父进程强杀后子孙进程退出、原生工作区 API、DPI／任务栏纯几何、最大化窗口聚焦及环境分支回归。测试窗口是隐藏的合成窗口，不等于 Windows ARM、多显示器 GUI 或真实素材全链路已验收。

## 本地数据与隐私

macOS 默认目录：`~/Library/Application Support/RallyCut/`，含最近项目索引、缓存、worker 与日志。项目只保存原片绝对路径、指纹、轨迹和编辑，不包含原视频；当前没有素材重定位。

新版本不要回退为“非空人工时间轴整表冻结”；这已经被保留人工修改、更新机器候选的行为取代。

## 网站与发布

见[发布维护](publishing.zh-CN.md)。网站以独立静态页面为主，仅演示 MP4 使用限定路径的 Pages Function 补齐视频 Range；只允许列出的用户文档和经明确批准的短演示进入公开输出，不部署源码根目录。GitHub 仓库与 Release 已公开，可匿名浏览源码和下载安装包；用户原片、项目、凭据和未授权资源仍不得上传。
