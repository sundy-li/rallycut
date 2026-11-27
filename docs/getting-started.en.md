# Install and quick start

[中文](getting-started.zh-CN.md) · English

RallyCut does three things: **find rallies, show the ball, export highlights.**

You can let the machine analyze first or cut everything by hand. The recommended way combines both: the machine proposes candidate rallies, you fix what it got wrong, and at export time you choose how overlapping results are resolved.

The app interface is currently in Chinese. This guide gives each button in English followed by the Chinese label you will see, for example **Ball trajectory (球轨迹)**.

[Watch the workbench](https://rallycut-app.pages.dev/en/#workbench) · [See an export](https://rallycut-app.pages.dev/en/#demo) · [Download installers](https://github.com/sundy-li/rallycut/releases/tag/v0.1.0-alpha.5)

## 1. Download and install

This is a public preview. The repository and the release installers are public, so **you can download without an invitation, repository access or a GitHub sign-in**. Pick the installer for your system under the release's Assets. The automatically generated source code ZIP / tar.gz is not an installer. If GitHub is hard to reach from your network, ask the maintainer for the same installer and its SHA-256 checksum.

- **macOS**: download `RallyCut-0.1.0-alpha.5-macos-universal.zip`, unzip it and drag `RallyCut.app` to Applications. Apple Silicon is the main test platform; Intel Macs still need hands-on testing.
- **Windows (experimental)**: prefer `RallyCut-0.1.0-alpha.5-windows-amd64-setup.exe`. It installs for the current user and already contains a private Python, FFmpeg and the analysis dependencies. WebView2 is required; if it is missing, the installer asks before installing it. For the portable fallback, download the EXE of the same version **and** `RallyCut-runtime-windows-amd64.zip` into the same folder. Copying only the EXE does not work.
- **Windows 11 on ARM**: use the same x64 package, which runs under system emulation, not as native ARM64. Emulation speed, native windows and `\\Mac\Home` shared folders have not been tested on real machines yet.

Before upgrading, quit the old app, back up your projects, then install. You do not need to delete the old data folder; do not move your source videos. Downloads of older versions have been withdrawn, so use this release.

The installers are not yet signed by a registered publisher or notarized by Apple. After checking where the file came from, open it as your system prompts. If a security warning worries you, contact the maintainer. **Do not turn off your system's security protection.** The release page also provides SHA-256 checksum lists.

## 2. First-run setup

**This version does not ask you to install Python, FFmpeg or PyTorch, or to edit PATH.** On launch, RallyCut checks your computer locally. If something is missing, it downloads only after you click to confirm. You reach the project list only after every check passes; if setup fails you can retry, and you cannot skip setup to start editing.

- **Full Windows installer**: the runtime is unpacked during installation, so the first launch should not download dependencies again or run pip. If the model is missing, click “Download the model and start (about 6 MB)” (下载模型并开始使用（约 6 MB）). The app verifies a fixed checksum and runs the model once as a self-test. Keep at least 5 GB free; loading can be slow under ARM emulation.
- **Portable Windows fallback**: the EXE uses the runtime ZIP next to it, verifies it on first launch and unpacks it to its own folder. The model is still prepared separately.
- **macOS**: if the environment is missing, click “Prepare the environment” (开始准备环境). The app downloads its own Python, video tools, analysis dependencies and model for your platform and shows real progress. Your system Python is not touched.

The first download needs internet access to the download sources. After that, analysis, editing and export all run on your computer. Time and disk space depend on the platform, so do not estimate them from the installer size alone.

**Later launches on Windows**: once the full check has passed in an environment, reopening the app goes straight to the project list without the setup page. Upgrades, changes to key files or an explicit re-check trigger a full check again. No command prompt windows should pop up. To test the first launch again, use a clean virtual machine snapshot rather than deleting projects or data folders.

## 3. Start with a short video

1. **Create a project**: enter a project name and import a match video you have the right to edit. Start with a few minutes of footage.
2. **Analyze**: click the analyze button next to the video title. Candidate rallies appear on the right and on the timeline as analysis progresses.
3. **Review**: click a rally to jump to it and turn on **Show ball trajectory (显示球轨迹)** to check the ball. The table outline is a separate display option; analysis still works when no table is found.
4. **Fix boundaries**: double-click the start or end time on a rally card and type a new time, or take the player's current time. Right-click a rally to mark it as a highlight, mark it invalid, split it or delete it. You can also add a rally by hand with `I` and `O`.
5. **Pick clips**: tick the rallies to export. How much extra time to keep before and after each clip is set under the gear icon: **Settings → Clip padding (设置 → 片段缓冲)**.
6. **Export an MP4**: in the export bar, tick **Ball trajectory (球轨迹)** and **Rally numbers (回合编号)** as needed. If you see “Rallies overlap. How should they be exported?” (回合有重叠，怎么导出？), choose an option as described below. If you have already corrected the boundaries yourself, “Manual rallies override analysis” (人工回合覆盖分析回合) is usually right. Pick the encoder under **Settings → Export encoding (设置 → 导出编码)**; H.264 is a good first choice.
7. **Watch the result**: check rally boundaries, audio sync and joins. Tick a single rally to export it on its own. Use a new file name; RallyCut does not overwrite the source video or earlier exports.

## 4. Combining manual editing with machine analysis

### Analyze first, then correct

This is the recommended way. Analyze the whole video, then replay each candidate rally:

| What you see | What to do |
| --- | --- |
| Starts too early, ends too late, or cuts off the serve | Double-click its start or end time and set the boundary you want. A machine rally you edit directly counts as a manual correction. |
| A rally is missing | Go to where it starts and press `I`, go to where it ends and press `O` to add a manual rally. You can also click the plus button in the rally list and then adjust the times. |
| Picking up the ball or passing it back was taken as a rally | Untick it, mark it invalid or delete it so it stays out of the export. |
| One clip contains several rallies, or several clips belong together | Split it from the right-click menu, or merge neighbours, then replay to check. |
| You don't want to sit through breaks and ball pickups | Turn on **Rallies only (只播回合)** while reviewing. This only changes playback; it does not export anything. |

Manual editing covers both **rallies you added yourself** and **machine rallies you corrected**. After re-analysis, manual results and new machine candidates can coexist; you decide which one to use at export time.

### Or skip analysis and cut by hand

After importing a video, mark the clips you want with `I` and `O`, adjust the boundaries, tick them and export. You don't need to run analysis first. The plus button in the rally list also adds a clip; check its start and end afterwards.

**Rallies you mark by hand do not get a ball trajectory automatically.** To preview or export a real trajectory, the video needs trajectory data from an analysis; the trajectory switch cannot invent ball positions. Rally numbers do not depend on the trajectory.

## 5. Choosing how overlaps are exported

When **ticked, valid** manual and analysis rallies overlap, clicking export opens **“Rallies overlap. How should they be exported?”** (回合有重叠，怎么导出？). Choose an option, check the expected number of rallies and duration, then click **“Export this way”** (按此方式导出).

| Option in the app | What happens | When to use it |
| --- | --- | --- |
| **Manual rallies override analysis** (人工回合覆盖分析回合) | Keeps manually added or corrected rallies; any analysis rally that overlaps one is skipped entirely. Other ticked, valid analysis rallies that don't overlap are still exported. | You have fixed the boundaries and want your version to win. |
| **Analysis overrides manual rallies** (分析回合覆盖人工回合) | Keeps analysis rallies; any manual rally that overlaps one is skipped entirely. | You prefer the machine result for now and don't want the overlapping manual version. |
| **Merge ranges, no overlap** (合并区间，不重叠) | Joins overlapping ranges into one continuous clip that keeps every covered frame once. | You don't want to lose any footage and accept longer clips. This is also the default if you never chose an option. |
| **Earlier one wins** (按先后顺序覆盖) | The rally that starts first is kept; an overlapping rally from the other source that starts later is skipped entirely. | You want start time, not the source, to decide. |

**Note: “override” keeps or drops whole rallies. It does not replace only the overlapping seconds.**

Example: the machine rally is `00:10–00:20` and your manual rally is `00:12–00:18`. Both are ticked and valid, the padding before and after is 0 and there are no other rallies:

- **Manual rallies override analysis** exports `00:12–00:18`. The whole machine rally `00:10–00:20` is skipped, and **`00:10–00:12` and `00:18–00:20` are not added back**.
- **Analysis overrides manual rallies** exports `00:10–00:20`.
- **Merge ranges, no overlap** exports one clip `00:10–00:20`, without playing the overlap twice.
- **Earlier one wins**: the machine rally starts first, so this example exports `00:10–00:20`. It does not always favour the machine.

These options only decide which rallies go into the export. **They do not delete rallies, change the project timeline, or overwrite the source video or earlier exports.** Overlaps between two manual rallies, or between two analysis rallies, are merged automatically and do not use the rules above. Unticked or invalid rallies are neither exported nor considered for overlaps.

Padding before and after changes the final clip boundaries. If you want the export to follow your marks exactly, check both values under **Settings → Clip padding** first. Watch the export afterwards to make sure the chosen option did not drop anything you wanted.

## 6. Common editing actions

| Action | How |
| --- | --- |
| Play / pause | Space or `K` |
| Add a rally | `I` marks the start, `O` marks the end |
| Change a rally's start or end | Double-click the time on the rally card |
| Undo / redo | macOS: `⌘Z` / `⇧⌘Z`; Windows: `Ctrl+Z` / `Ctrl+Y` |
| Settings | Gear icon at the top, or `⌘,` / `Ctrl+,` |
| All shortcuts | Keyboard icon at the top, or `⌘/` / `Ctrl+/` |

Edits are saved automatically. Undo history lasts only for the current session; it is cleared when you switch projects or videos or when an analysis finishes, so it is not a substitute for a project backup. Export settings, project renames and adding or removing videos cannot be undone.

## 7. Re-analysis and project backups

Re-analysis replaces machine rallies you have not touched and keeps rallies you added or corrected. New analysis candidates that overlap your manual rallies are also kept, so you can choose at export time. Seeing rallies from both sources in the list is normal and does not mean the export will contain duplicates.

Deleting a machine rally does not exclude it permanently; it may come back after re-analysis. If you just don't want it in the export, untick it instead. New machine rallies that match an unticked old candidate stay unticked, but review again if the candidates changed a lot.

Finishing a re-analysis clears the undo history. Use **Save as** for important projects first instead of relying on undo as a snapshot.

Project files do not contain the videos. Don't move, rename or replace the source videos a project refers to; copying only the project JSON to another computer does not bring the videos along. Before upgrading or making big edits, use **Save as** to keep a copy of the project.

Automatic detection can miss rallies or mistake passing the ball back or picking it up for a rally. You decide which clips to keep after reviewing them.

[Having trouble?](faq.en.md) · [Release notes](releases.en.md)
