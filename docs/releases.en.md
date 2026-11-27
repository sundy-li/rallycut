# Release notes

[中文](releases.zh-CN.md) · English

## v0.1.0-alpha.5 · Agent-assisted editing and faster local analysis on Apple Silicon

[Download this release](https://github.com/sundy-li/rallycut/releases/tag/v0.1.0-alpha.5)

- Choose “Copy for AI” (复制给 AI) in the export bar to share the project path and commands with an agent that has the `rallycut` skill. Preview a plan, select rallies, set a clip limit and adjust padding without rerunning analysis.
- On Apple Silicon, RallyCut converts and verifies the Core ML model locally, then runs inference in a separate process. MPS remains the fallback. Live previews also avoid frequent full recomputation on long videos. These changes target speed, not segmentation accuracy.
- Model downloads now support mirrors and retries, with size and SHA-256 checks regardless of source. The app and skill do not bundle model weights. Setup and settings display the build version.
- Export overlay settings are no longer reset. The desktop app can replace an earlier export after confirmation in the system save dialog; the skill requires `--overwrite`. Neither can overwrite the source video.

### Downloads and upgrades

| Use | Release asset |
| --- | --- |
| macOS (Apple Silicon / Intel) | `RallyCut-0.1.0-alpha.5-macos-universal.zip` |
| Windows x64 (recommended) | `RallyCut-0.1.0-alpha.5-windows-amd64-setup.exe` |
| Windows x64 portable | Put `RallyCut-0.1.0-alpha.5-windows-amd64.exe` and `RallyCut-runtime-windows-amd64.zip` in the same folder |
| Agent skill | `rallycut-skill-0.1.0-alpha.5.skill`, listed in `SHA256SUMS-macos.txt` |

Quit the old app and back up projects before upgrading. There is no need to delete user data. Installers are not publisher-signed or Apple-notarized, and the Windows build is not native ARM64. Review automatically detected rallies before exporting.

[Installation guide](getting-started.en.md) · [FAQ](faq.en.md)
