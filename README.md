# RallyCut

中文 · [English](README.en.md)

**让每个好球，留下来。** 把整场乒乓球视频，剪成值得回看的回合集锦。

[下载种子版](https://rallycut-app.pages.dev/#download) · [看软件界面](https://rallycut-app.pages.dev/#workbench) · [看导出效果](https://rallycut-app.pages.dev/#demo) · [中文指南](https://rallycut-app.pages.dev/guide/)

## 先看主界面：回合怎么拆

[![RallyCut 真实操作录屏：回放原片、查看回合列表与时间轴](site/public/media/rallycut-workbench-preview.gif)](https://rallycut-app.pages.dev/#workbench)

**右侧逐个看回合，底部总览整场。** 点击动图观看约 19 秒的真实操作录屏（已剪去开头 1 秒，无音轨）。点击回合回放，复核或调整起止点，勾选想保留的片段，再导出集锦。

<details>
<summary>补充演示：再看导出后的效果</summary>

[![RallyCut 实际导出：乒乓球轨迹与回合编号](site/public/media/rallycut-preview.gif)](https://rallycut-app.pages.dev/#demo)

*樊振东比赛素材的实际导出片段：橙色线条跟随球的轨迹，左上角显示回合编号。完整演示带原声，点击观看。*

</details>

## 它能做什么

- **找回合**：导入比赛视频，自动生成候选回合，少拖一点进度条。
- **看轨迹**：回放球的运动轨迹，复核精彩瞬间。
- **改剪辑**：机器分析与人工修正结合，导出时可选人工优先等覆盖方式，支持撤销与重做。
- **出集锦**：勾选想保留的回合，导出 MP4；可把**球轨迹和回合编号一起放进视频**。
- **交给 AI 再剪**：导出栏的“复制给 AI”把回合列表和剪辑参数复制成文本，粘贴给装了 [rallycut skill](skills/rallycut/SKILL.md) 的 agent，就能用一句话挑回合、改缓冲、再导出；不开桌面版也能用 skill 完成识别到导出。

## 开始使用

1. [下载安装包](https://github.com/sundy-li/rallycut/releases/tag/v0.1.0-alpha.4)，按[安装指南](docs/getting-started.zh-CN.md)完成首次准备。
2. 新建项目 → 导入视频 → 分析并复核回合。
3. 在导出栏勾选“球轨迹”“回合编号”，导出你的集锦。

视频在本机处理，不需要上传。当前为早期预览版，**源码和安装包已公开，无需邀请或登录即可浏览、下载**；macOS 优先，Windows 为实验性支持。Windows 完整安装器已含依赖，缺模型时确认后下载；macOS 首次确认后准备私有环境，无需手动安装 Python／FFmpeg。安装包尚未完成正式发布者签名／公证；自动识别结果仍需人工复核。

[安装与使用](docs/getting-started.zh-CN.md) · [常见问题](docs/faq.zh-CN.md) · [本版更新](docs/releases.zh-CN.md)

## 交给 AI agent 使用（rallycut skill）

`rallycut` 是给 AI agent 用的 skill，可以在不打开桌面版的情况下完成“识别回合 → 挑选 → 导出集锦”，也能接手桌面版分析好的项目做二次剪辑。适用于支持 skills 目录的 agent，例如 Claude Code、Codex 和其他读取 `SKILL.md` 的工具。

**1. 获取 skill 包**

- 从 [Release](https://github.com/sundy-li/rallycut/releases) 下载 `rallycut-skill-<版本>.skill`（就是 zip 文件），或
- 从源码构建：`just skill`，产物在 `build/skills/rallycut/`（目录）和 `build/skills/rallycut.skill`。构建需要 Go 和 Python 3，使用时不需要。

**2. 放进 agent 的 skills 目录**（整个目录，不要只复制 `SKILL.md`）

```bash
# 从下载的包安装；目录名必须是 rallycut
mkdir -p ~/.claude/skills && unzip rallycut-skill-*.skill -d ~/.claude/skills/
# 或从源码构建结果复制
cp -R build/skills/rallycut ~/.claude/skills/
```

不同 agent 的目录不同：Claude Code 是 `~/.claude/skills/`，Codex 是 `~/.codex/skills/`，通用目录 `~/.agents/skills/`。装过旧名 `rallycut-video-json` 的，删掉旧目录即可，已准备好的运行环境和模型会继续使用。

**3. 依赖**

- 二次剪辑和导出（`plan` / `export` / `brief`）：只要系统 Python 3 和 FFmpeg（macOS `brew install ffmpeg`）。
- 分析新视频（`analyze`）：另需 [uv](https://docs.astral.sh/uv/)。第一次让 agent 运行 `setup --download-model`，它会准备独立的 Python 3.12 环境、PyTorch，并下载约 6 MB 模型；之后完全离线。

**4. 怎么用**

- 在桌面版导出栏点 **“复制给 AI”**，粘贴给 agent，再说要求：“只要最精彩的 10 个回合，前后各留 2 秒，导出到 ~/Movies/集锦.mp4”。
- 或直接给视频：“用 rallycut 识别 ~/Videos/比赛.mp4 的回合，导出前 20 个”。

agent 会先列出剪辑计划（用哪些回合、总时长），确认后再导出。导出和桌面版用同一套片段合并与编码逻辑，不覆盖原片；替换已有成片需要你明确要求。详细用法见 [skill 说明](skills/rallycut/SKILL.md)。

---

开发者：[开发与测试](docs/development.md) · [算法与实验记录](docs/experiments.md) · [发布维护](docs/publishing.zh-CN.md) · [许可证](docs/licenses.md)
