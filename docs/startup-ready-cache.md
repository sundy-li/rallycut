# Windows 重复启动：成功缓存与静默子进程

适用 `v0.1.0-alpha.3-windows.4` 源码／测试包，实际交付状态以 Release 为准。

## 修复的问题

旧版每次 `Startup → Detect` 都启动 Python、FFmpeg／FFprobe，导入依赖、遍历并哈希整个环境，再加载模型执行 CPU 前向。即使上次已成功，也先展示首次准备页；Windows 控制台子程序还会闪出 DOS 窗口。

## 新流程

- 第一次成功准备或完整检查后，原子写入当前用户数据目录的 `runtime-ready.json`。
- 下次 `Startup → Boot` 先在 Go 进程内核对成功记录：固定环境／模型／worker 标识、路径、运行所需的 EXE／DLL／PYD 等关键文件大小和修改时间、worker 文件信息，以及小模型、运行时 `bundle-manifest.json` 和已固定文件清单的哈希。
- 记录有效时只发出 `ready`，不进入 `checking`，不执行任何 Python、FFmpeg 命令，不重复模型前向，不下载、不解压；直接允许项目列表／工作台。
- 首次 RPC 尚未返回或后端尚在决定快速路径时，只显示极简打开状态，不预先挂载首次准备页。因此缓存命中后不会先闪出自检卡片再切回项目列表。
- 已安装运行时的完整检查（升级后缺少成功记录时）同样只显示「正在检查运行环境…」的极简打开态；只有检查失败、需要用户准备或重新检测时才切到首次准备页。
- 缺少成功记录、环境／worker／模型版本或路径变化、关键文件缺失或元数据变化、模型哈希变化，才回到完整检测；重新检测是本地操作，下载仍需明确确认。
- 升级到此版首次没有旧成功记录，仍需完整检查一次。随后同版、同路径、相同环境正常重开才会走快速路径；不凭“上次文件存在”假定旧版成功。

成功记录不是安全签名，也不声称抵御能同时修改用户记录与安装文件的攻击者。快速路径不每次重哈希大体积 DLL 或逐个检查所有 Python 模块；完整校验、导入与真实前向仍用于首次验证和显式复检，分析时的真实错误不会被缓存掩盖。记录写入失败时保留日志，下次重新完整检查，不伪装缓存成功。

## 不再闪 DOS 窗口

`backend/childproc` 统一封装内部命令：Windows 使用 `CREATE_NO_WINDOW`；普通 Python、uv、pip、FFmpeg／FFprobe 同时设置 `HideWindow`。标准输出、标准错误、退出码和 context 取消照常保留，不能用“隐藏窗口”代替错误处理。

用户明确请求的文件选择器只隐藏 PowerShell 控制台，不隐藏选择对话框；资源管理器也保留正常窗口行为。WebView2 原生安装提示不是普通内部命令，仍按其独立流程处理。

快速缓存同时覆盖「固定清单的预制环境」和「本地构建 + 已安装运行时」：后者不嵌入运行时清单（`{"platforms":{}}`），但 exe 旁的 `runtimes/<bundled-id>/` 与其中的 `bundle-manifest.json` 仍参与身份和文件戳校验，命中即直接 ready。只有根本没有已安装运行时（首次安装或旧 Mac 准备方式）才走完整检测。没有固定清单时不会再像旧实现那样“每次启动都完整检测且从不写成功记录”。

## 测试边界

- `backend/setup/receipt_test.go`：成功后跳过完整检测、不会出现 checking 事件；记录损坏、文件或版本变化、显式复检会失效；失败不写成功记录。
- `backend/childproc`：Windows 断言创建标志，并实际运行测试子进程，通过 `GetConsoleWindow` 检查没有控制台；输出、错误码和取消仍可观测。
- `TestInstalledRuntimeFirstUse`：Windows runner 真实安装后的首次准备，第二个 Provisioner 读取磁盘记录、禁止调用 inspect/install，必须直接 ready，并记录耗时。此测试是后端启动路径，不等于人工测量完整 GUI 启动时间。
- `tests/ui/test_startup.py`：Wails fixture 验证 ready 和 opening → ready 两种首屏不曾插入 `.setup-screen`，不启动准备或复检；不冒充 Windows ARM 原生 GUI 观察结果。
- Windows ARM 用户仍需复测首次准备、退出后重开、导入／分析／导出以及文件选择器，确认没有黑窗口且正常对话框仍可用。
