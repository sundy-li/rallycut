# 本版更新

## v0.1.0-alpha.3 · 安装与 Windows 体验更新

[打开本版 GitHub Release](https://github.com/sundy-li/rallycut/releases/tag/v0.1.0-alpha.3)。本版统一提供 **macOS 通用包、Windows x64 完整安装器和免安装备用包**，附平台 SHA-256 校验清单。仓库和 Release 安装包现已公开，无需邀请或登录即可浏览、下载；公开网站提供 GitHub 下载入口，不托管原片或项目。

### 安装与启动

- **Windows 安装时准备好依赖**：完整安装器展开私有 Python、NumPy／OpenCV／PyTorch、FFmpeg／FFprobe 和 app-local Visual C++ 运行库，不需要自行安装 Python、修改 PATH 或在用户电脑现场执行 pip。
- **模型仍需单独准备**：权重不打入安装包；首次使用缺模型时，明确点击后才下载约 6 MB 模型并执行真实自检。已准备过且哈希符合要求的模型可复用。
- **重复打开直接进入软件**：Windows 首次完整验证成功后保存本机成功记录；环境、模型和 worker 无变化时，只做 Go 进程内轻量文件核对，不再运行 Python／FFmpeg／模型探测，也不闪准备页。升级导致记录失效时仍需完整检查一次。
- **内部命令不弹 DOS 窗口**：保留错误和退出状态；用户主动打开的原生对话框和资源管理器仍正常显示。
- **macOS 首次准备向导**：先本地检测，缺依赖时由你点击准备，再下载应用私有环境与模型；不要求手动安装 Python／FFmpeg，不修改系统 Python 或全局 PATH。Mac 不承诺与 Windows 相同的启动缓存路径。

### Windows 使用与可靠性

- 中文、空格、符号、emoji 视频路径直接通过原生 Unicode 多选接口传递，不再经 PowerShell 控制台转换；UNC 前缀原样保留。共享盘仍需系统可访问。
- 单实例运行：再次启动聚焦已有窗口，仅最小化时才还原，不把最大化窗口恢复成普通窗口。
- 按真实工作区和 DPI 适配窗口，处理缩放、小屏、负坐标显示器和任务栏占用；先调整最小尺寸，避免窗口被固定下限撑出屏幕。
- Windows Job Object 在父进程被强制结束后回收其辅助子孙进程，减少分析 worker 残留。
- 本地构建改走标准 Wails 链，重新生成前端、DPI manifest、图标和版本资源；无嵌入归档清单的本地构建仍校验并复用已安装环境，缺模型不创建第二套 Python。
- 环境准备的阶段进度、超时及错误详情保留。推理线程数沿用本次源码设置，不把线程数增加宣传为已验证的跨平台加速。

### 剪辑功能继续保留

- 自动候选回合、球轨迹预览，导出 MP4 时可叠加球轨迹与回合编号。
- 双击修正起止点、手动添加回合、撤销／重做、设置与快捷键面板。
- 重新分析保留人工添加和修正的回合；导出时选择人工优先、分析优先、合并或按先后覆盖。覆盖只决定成片，不删除项目回合，不覆盖原片或已有成片。
- 无需强制找到球桌也能分析球；缺少几何证据时不编造触网／出界结论。自动结果仍需复核。

### 下载与升级

| 系统／用途 | 附件 |
| --- | --- |
| macOS Apple Silicon／Intel | `RallyCut-0.1.0-alpha.3-macos-universal.zip` |
| Windows 首选 | `RallyCut-0.1.0-alpha.3-windows-amd64-setup.exe` |
| Windows 免安装备用 | `RallyCut-0.1.0-alpha.3-windows-amd64.exe`，同时下载 `RallyCut-runtime-windows-amd64.zip` 放在 EXE 同目录 |
| 文件校验 | `SHA256SUMS-macos.txt`、`SHA256SUMS-windows.txt`；`runtime-bundle.json` 是运行环境固定清单 |

先退出旧软件、备份项目，再安装／替换应用；**不用卸载或删除用户数据目录**。保留原视频名称与路径，用短素材试用后再继续重要项目。6 个历史 Release 及下载附件已统一撤下，目前只保留本版，旧链接不再可用；Git 提交历史、用户项目和视频没有删除。

### 验证范围与限制

发布链在 macOS runner 检查通用包两种架构、production 构建和 ad-hoc 签名；Windows x64 runner 检查安装／卸载保留数据、预制环境搬移、真实模型前向、Unicode 项目导入与重开、Range 预览、实际视频解码与导出、重复启动缓存、原生资源和辅助进程回收。以本版 Release workflow 的成功结果为准。

这些不等于 Windows ARM 虚拟机、原生选择窗口点击、`\\Mac\Home` 共享服务、多显示器交互或 Intel Mac 真机已验收。Windows 包仍是 x64，不是原生 ARM64；不承诺模拟层或显卡加速效果。安装包未正式签名／Apple 公证，遇到系统拦截请确认来源，不要关闭系统安全保护。模型再分发／商用条款仍在确认。

[安装与使用](getting-started.zh-CN.md) · [常见问题与反馈](faq.zh-CN.md)
