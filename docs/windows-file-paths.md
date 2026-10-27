# Windows 中文路径与原生视频选择器

修复版本：`v0.1.0-alpha.3-windows.5`。发布与否以对应 Release 实际附件为准。

## 问题与原因

用户在 Windows 11 ARM 虚拟机中新建项目、选中 `Documents/生活/video/...mp4` 后，得到 `GetFileAttributesEx ...\??\video\...: The system cannot find the path specified`。报错发生在 `media.Probe → os.Stat`，尚未进入 FFprobe 或模型分析。

旧多选路径为：WinForms 对话框 → Windows PowerShell 控制台文本输出 → Go 把 stdout 当 UTF-8。没有指定控制台输出编码，默认代码页无法表示的字符可能已经变成 `?`；这时在 Go 层尝试重新解码已经不能恢复原始文件名。旧代码注释错误地称 Wails 2.16 没有多选接口，导致不必要的脚本中转。

这条链路确实存在编码缺陷，但单张截图不能证明共享盘自身一定可达。修复编码不等于授予共享目录权限、修复断开的网络盘或把已经损坏的项目路径自动猜回去。

## 修复

- `media.PickVideos` 直接使用 Wails `OpenMultipleFilesDialog`，返回原生 Unicode 路径数组。
- Windows 使用 `IFileOpenDialog` 与 `SIGDN_FILESYSPATH` 的 UTF-16 返回值；不再经过 PowerShell、系统 ANSI/OEM 代码页、按行切分或 TrimSpace。
- macOS、Linux 同样走框架原生多选接口，不再分别维护 osascript／zenity stdout 协议。
- 不对返回路径做 URL 解码，不改 `#`、`%`、空格、中文、emoji 或 UNC 前缀；`\\Mac\Home\...` 不得补成 `C:\Mac\Home\...`。
- 对话框错误向调用方传播；取消不创建项目。真实的文件不可访问时保留原始错误，并提示检查共享目录或权限，而不是让用户把中文目录改名。
- 未改环境准备、启动缓存、模型或分段算法；内部视频命令仍静默运行。

## 同轮回归拦住的导出问题

第一次真实 Windows 全链路回归中，Unicode 新建项目、FFprobe、指纹、OpenCV 解码和 Range 预览均通过，但输出目录含 `#` 时，FFmpeg concat 将绝对路径的一部分按 URL fragment 处理，拼接时寻找了错误目录。现在拼接进程明确使用临时目录作为工作目录，传入固定 ASCII 相对文件名 `concat.txt`、`clip-*.mp4` 和 `highlights.mp4`，不把用户目录嵌入 concat URL，也不降低 `-safe 1`。生成输出仍校验轨道、时长并拒绝覆盖原片。Windows 完成文件发布改用同卷、拒绝替换目标的 `MoveFileW`，避免要求共享盘支持 NTFS 硬链接；已有目标拒绝覆盖有独立回归，真实 Mac 共享服务仍须人工验收。

`TestSilentVideoExport` 也改用中文／空格／`#`／`%`／`&`／emoji 路径，作为跨平台重复回归。失败版本没有发布。

## 验证分层

1. `backend/media/picker_test.go`：通过注入的对话框回调，验证中文／空格／符号／emoji／UNC 字符串完全不变；验证取消和错误不同。这是接口边界单测，不是点击真实对话框的 GUI 测试。
2. `picker_windows_test.go`：在 Windows 中验证 `filepath.Abs` 不把 UNC 路径改成当前磁盘路径。这不证明 Mac 共享服务可达。
3. `TestWindowsUnicodeProjectImportPreviewExport`：真实安装器安装后，以安装目录的 FFmpeg／FFprobe 创建短合成视频，真实读取中文、空格、特殊符号和 emoji 路径，经过同一个新建项目后处理函数、内容指纹、项目 JSON 持久化／重开、Range 原片预览、人工回合导出和输出探测；校验原片未改。路径来自测试本地 NTFS 目录，不冒充 Mac 网络共享盘或真实比赛素材。
4. Windows ARM 虚拟机需要用户实际复测原生多选窗口与 `\\Mac\Home` 共享盘导入。CI 的 x64 runner 不代表 ARM GUI 或 Parallels 共享服务已验收。

## 升级后如何测试

退出旧版后安装 `.5` 完整安装器。先直接选择原中文目录的文件，不必改英文名，尝试新建项目、播放、保存／重开与导出；再试多选、取消，以及 Windows 本地的中文目录。

若原共享盘仍报无法访问，请先用 Windows 资源管理器打开同一文件，核对真实 UNC／映射盘路径和共享权限；可以复制到 Windows 本地目录区分共享访问问题与程序读取问题。不要手工编辑项目 JSON 猜测 `??` 对应的原目录。
