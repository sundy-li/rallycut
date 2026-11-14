# RallyCut guide

[中文](README.md) · English

**The machine finds the rallies, you check and correct them, then export your table tennis highlights.**

RallyCut works three ways: let the machine analyze the rallies, cut by hand, or combine both. Where the machine gets a cut wrong, adjust the start and end or add the rally it missed; at export time, choose which version to use.

**Recommended flow: import a match → analyze → replay and correct → choose an overlap option → export highlights.**

If you only want to cut by hand, import the video and mark rallies directly; you don't need to run analysis first.

The app interface is currently in Chinese. The English guides name each button in English followed by its Chinese label.

[See how rallies are split](https://rallycut-app.pages.dev/en/#workbench) · [See an export](https://rallycut-app.pages.dev/en/#demo) · [Download the preview](https://rallycut-app.pages.dev/en/#download)

## Start here

- [Install and quick start](getting-started.en.md): installation, combining manual and machine editing, the four overlap options and exporting with trajectories.
- [FAQ and feedback](faq.en.md): downloads, first-run setup, trajectories and rally numbers, undo, and feedback.
- [Release notes](releases.en.md): what's new, upgrading and current limits.

## Fix what the machine got wrong

Click a rally to replay it and double-click its start or end time to change the boundary. Add a missed clip by pressing `I` at the start and `O` at the end. Rallies you add or correct are kept when you re-analyze.

When manual and machine rallies overlap at export, choose **“Manual rallies override analysis”** (人工回合覆盖分析回合) to use your version; other ticked, valid machine rallies that don't overlap are still exported. You can also choose analysis first, merge ranges, or earlier one wins.

**Overrides happen at export and don't change the project timeline. An overridden rally is dropped as a whole, not just trimmed where it overlaps.** See the [quick start](getting-started.en.md) for an example.

Videos are processed on your computer and never uploaded. Automatic results still need a replay to check. First-run setup needs internet access and your explicit confirmation: the full Windows installer already has its dependencies and only adds the missing model, while macOS prepares a private environment. You don't install Python or FFmpeg by hand. Manual cuts don't get a ball trajectory automatically. The GitHub repository and installers are public and can be downloaded without an invitation or sign-in; if GitHub is hard to reach, ask the maintainer for the same installer and its checksum.

## Developers and maintainers

These documents are in Chinese: [Development and tests](development.md) · [Algorithms and experiments](experiments.md) · [Publishing](publishing.zh-CN.md) · [Licenses](licenses.md)

The download site hosts only the user guides, the approved workbench recording and a short demo. Full source code and developer documents are in the public GitHub repository. A public repository doesn't make user projects, source videos, model weights or private experiment data public, and those must not be uploaded.
