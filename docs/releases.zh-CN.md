# 本版更新

中文 · [English](releases.en.md)

## v0.1.0-alpha.5 · 项目交给 AI 剪辑，Apple Silicon 本地分析加速

[下载本版](https://github.com/sundy-li/rallycut/releases/tag/v0.1.0-alpha.5)

- 在导出栏点“复制给 AI”，把项目路径和命令交给装有 `rallycut` skill 的 agent。无需重新分析，就可以先看剪辑计划，再按回合、数量和前后缓冲导出。
- Apple Silicon 在本机转换并校验 Core ML 模型，通过后使用子进程推理；不可用时继续使用 MPS。长视频的实时回合预览不再频繁全量重算。这些是速度优化，不代表切分准确率提高。
- 模型下载支持镜像和重试，始终校验大小和 SHA-256；模型权重不在应用和 skill 包内。准备页和设置可查看构建版本。
- 修复导出叠加开关被重置的问题。桌面端可在系统保存对话框确认后替换已有成片；skill 需要显式 `--overwrite`。原片始终不能覆盖。

### 下载与升级

| 用途 | Release 附件 |
| --- | --- |
| macOS（Apple Silicon / Intel） | `RallyCut-0.1.0-alpha.5-macos-universal.zip` |
| Windows x64（推荐） | `RallyCut-0.1.0-alpha.5-windows-amd64-setup.exe` |
| Windows x64 免安装 | `RallyCut-0.1.0-alpha.5-windows-amd64.exe` 和 `RallyCut-runtime-windows-amd64.zip` 放在同一目录 |
| Agent skill | `rallycut-skill-0.1.0-alpha.5.skill`，校验值在 `SHA256SUMS-macos.txt` |

升级前退出旧应用、备份项目，无需删除用户数据。安装包未正式签名或经 Apple 公证；Windows 包不是原生 ARM64。自动识别的回合仍需人工复核。

[安装指南](getting-started.zh-CN.md) · [常见问题](faq.zh-CN.md)
