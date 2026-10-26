# 本地视频预览修复

## 根因

不是所有 `HTMLMediaElement` 错误都代表 WebView 不支持编码。开发模式的 Wails `NewExternalAssetsHandler` 对 GET 先请求外部 Vite，仅在 404 / 405 时回退到自定义 Handler；但 Vite SPA fallback 对 `/media/source?project=...` 返回 **200 text/html**。播放器因此收到前端页面，而非视频数据，原先被误报为“系统 WebView 不支持此编码”。

## 修复

- `backend.MediaMiddleware` 在外部 Vite 代理 / 静态资产处理之前拦截 `/media/`，媒体请求直接由 Go 授权的媒体服务处理。开发版和生产版使用同一层。
- 保持 `http.ServeContent` 的 Range / Content-Range / HEAD 支持；只能读取当前项目原片，错误项目 ID 和未知媒体路径均不回退到前端页面。
- 前端分别显示中断、读取、解码和媒体源错误；保留实际错误码，不再把源错误一概判为编码不支持。
- 增加“重试预览”，重建播放器请求；如果原来有播放位置，加载元数据后恢复。无需重新导入、重新分析或转码原片。
- 用户手动播放被系统策略阻止时提示使用原生播放按钮；跳转导致的 AbortError 不再误报为编码错误。

此修复没有强制将全部视频转成代理文件，不改变原片、颜色、检测时间轴或导出设置。系统确实不支持的其他编码 / 容器仍可能无法直接播放，不能从这次结果推断任意视频格式均可预览。

## 验证

1. Go 测试使用 **Wails 实际外部代理实现**，模拟 Vite 对任何路径返回 200 HTML，确认媒体 GET / HEAD / Range / 416 / 错误 ID 均绕过代理，而前端页面仍正确代理。
2. Chrome 交互测试先让媒体返回 200 HTML，检查错误码与“重试预览”，恢复真正 MP4 后确认播放器实际推进时间，并回归拆分、合并、独立叠加开关及紧凑布局。
3. 原生回归工具 `tests/desktop/test_preview.py` 构建真实 Wails / macOS WKWebView，复制项目到隔离 HOME，不改变用户项目或最近打开记录。测试媒体响应为 206 video/mp4、元数据加载、实际播放推进以及 seek 完成；不是模拟 browser bridge。

执行原生验证：

```bash
python3 tests/desktop/test_preview.py --project /absolute/20261024-152433-rallycut.json
# --project 可重复；不传时只读当前最近项目并使用隔离副本。
```

本次原生实测三例均通过：H.264 320×180 测试片实际播放并跳转到 15 秒；`DJI_20261020171009_0043_D.MP4` 和 `DJI_20261020201410_0044_D.MP4` 两段 1080p HEVC 原片实际播放并跳转到 30 秒，均获得 206 / video/mp4，`readyState == 4`。未转码原片。详细输出在 `/tmp/rallycut-preview-fix/native-validation.json`。

具体原生测试输出由测试命令记录，只有退出码 0 才表示通过。启动新版需要退出旧窗口后 `just run`，开发模式则重新启动 `just dev`。
