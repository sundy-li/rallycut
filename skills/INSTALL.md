# 安装 rallycut skill（给 AI agent 看的步骤）

用户让你“安装 rallycut skill”时，按下面做。不要只复制 `SKILL.md`，skill 需要完整目录（含 `assets/`）。

## 1. 运行安装脚本

macOS / Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/sundy-li/rallycut/main/scripts/install-skill.sh | bash -s -- --dir <你的 skills 目录>
```

- `<你的 skills 目录>` 是你自己加载 skill 的目录：Claude Code 为 `~/.claude/skills`，Codex 为 `~/.codex/skills`，其他 agent 用其约定目录（常见 `~/.agents/skills`）。不确定时省略 `--dir`，脚本会装到所有已存在的 agent 目录和 `~/.agents/skills`。
- 脚本从 GitHub Release 下载 `rallycut-skill-<版本>.skill`，用同一 Release 的 `SHA256SUMS-macos.txt` 校验后解压为 `<skills 目录>/rallycut`。github.com 不通时自动改用国内加速节点。它只写 skills 目录，不安装系统软件，不下载模型。
- 输出“还没有包含 rallycut skill 的 Release”时，改为从源码打包（需要 Go 和 git，先征得用户同意安装缺少的工具）：

  ```bash
  git clone --depth 1 https://github.com/sundy-li/rallycut /tmp/rallycut-src
  bash /tmp/rallycut-src/scripts/install-skill.sh --from-source /tmp/rallycut-src --dir <你的 skills 目录>
  ```

Windows（PowerShell）：从 [Releases](https://github.com/sundy-li/rallycut/releases) 下载最新的 `rallycut-skill-*.skill`，核对 `SHA256SUMS-macos.txt` 里的 SHA-256（`Get-FileHash`），用 `Expand-Archive` 解压到 skills 目录，确认得到 `<skills 目录>\rallycut\SKILL.md`。

## 2. 检查依赖并告诉用户

- 二次剪辑 / 导出只需 Python 3 和 FFmpeg。没有 FFmpeg 时告诉用户安装方式（macOS `brew install ffmpeg`），不要未经同意执行系统级安装。
- 分析新视频还需要 [uv](https://docs.astral.sh/uv/)，以及一次 `setup --download-model`（PyTorch 与约 6 MB 模型）。这一步等用户真要分析视频时再做，并先征得同意。
- 脚本提示存在旧目录 `rallycut-video-json` 时，告诉用户它是改名前的版本，由用户决定是否删除。

## 3. 让用户试一下

安装后可能需要重启 agent 或新开会话才能加载新 skill。告诉用户两种用法：

- 在 RallyCut 桌面版导出栏点“复制给 AI”，粘贴给你，再说要求（例如“只要最精彩的 10 个回合，前后各留 2 秒”）。
- 直接给一个比赛视频路径，让你识别回合并导出集锦。
