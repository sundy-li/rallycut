# RallyCut

[中文](README.md) · English

**Keep every great point.** RallyCut turns a full table tennis match video into a highlight reel of the rallies worth watching again.

[Download the preview](https://rallycut-app.pages.dev/en/#download) · [See the app](https://rallycut-app.pages.dev/en/#workbench) · [See an export](https://rallycut-app.pages.dev/en/#demo) · [English guide](https://rallycut-app.pages.dev/en/guide/)

## Let an AI agent do the cutting

Send this sentence to Claude Code, Codex or another AI agent and it installs the `rallycut` skill itself:

```text
Install the rallycut skill by following https://raw.githubusercontent.com/sundy-li/rallycut/main/skills/INSTALL.md
```

Then just ask, for example, “find the rallies in ~/Videos/match.mp4 and export the best 10”, without opening the desktop app. Or click **“复制给 AI”** (copy for AI) in the app's export bar to hand an analysed project to the agent. The agent shows a cut plan first and exports after you confirm; source videos are never overwritten.

<details>
<summary>Manual install, dependencies and more</summary>

- One-line install from a terminal (macOS / Linux): `curl -fsSL https://raw.githubusercontent.com/sundy-li/rallycut/main/scripts/install-skill.sh | bash`. It installs into `~/.claude/skills` and `~/.codex/skills` when present, plus `~/.agents/skills`; use `--dir` for another directory.
- Re-cutting and exporting need only Python 3 and FFmpeg. Analysing new videos also needs [uv](https://docs.astral.sh/uv/); before the first analysis the agent asks you, then prepares PyTorch and a 6 MB model and runs offline afterwards.
- Build from source: `just skill` (needs Go); output in `build/skills/rallycut/`.
- Full usage: [skill guide](skills/rallycut/SKILL.md) (Chinese).

</details>

## See the workbench first

[![RallyCut screen recording: playing the source video with the rally list and timeline](site/public/media/rallycut-workbench-preview.gif)](https://rallycut-app.pages.dev/en/#workbench)

**Review rallies one by one on the right; see the whole match on the timeline below.** Click the animation to watch the 19-second screen recording (first second trimmed, no audio). Click a rally to replay it, adjust its start and end, tick the clips you want, then export.

<details>
<summary>More: what an exported highlight looks like</summary>

[![RallyCut export: ball trajectory and rally numbers](site/public/media/rallycut-preview.gif)](https://rallycut-app.pages.dev/en/#demo)

*A real export from Fan Zhendong match footage: the orange line follows the ball and the rally number sits in the top-left corner. The full demo keeps the original audio.*

</details>

## What it does

- **Finds rallies**: import a match video and get candidate rallies instead of scrubbing the timeline.
- **Shows the ball**: replay the ball trajectory to check each point.
- **Lets you correct it**: combine machine analysis with your own edits; at export time choose whose result wins. Undo and redo are supported.
- **Exports highlights**: tick the rallies to keep and export an MP4, optionally with **the ball trajectory and rally numbers burned in**.

## Getting started

1. [Download the installer](https://github.com/sundy-li/rallycut/releases/tag/v0.1.0-alpha.5) and follow the [install guide](docs/getting-started.en.md) for first-run setup.
2. Create a project → import a video → analyze and review the rallies.
3. In the export bar, tick “Ball trajectory” and “Rally numbers”, then export.

Videos are processed on your computer and never uploaded. This is an early preview. **Source code and installers are public; no invitation or sign-in is needed to browse or download.** macOS comes first; Windows support is experimental. The full Windows installer bundles its dependencies and only downloads the model after you confirm; on macOS the app prepares a private environment after you confirm. You do not need to install Python or FFmpeg. Installers are not yet signed by a registered publisher or notarized by Apple, and automatic results still need a human review.

The app interface is currently in Chinese.

[Install and use](docs/getting-started.en.md) · [FAQ](docs/faq.en.md) · [Release notes](docs/releases.en.md)

---

Developers (Chinese): [Development and tests](docs/development.md) · [Algorithms and experiments](docs/experiments.md) · [Publishing](docs/publishing.zh-CN.md) · [Licenses](docs/licenses.md)
