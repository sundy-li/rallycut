# FAQ and feedback

[中文](faq.zh-CN.md) · English

## Why does the download link show 404?

The repository and release installers are public; no invitation or sign-in is needed. Download from the Assets of the [current release](https://github.com/sundy-li/rallycut/releases/tag/v0.1.0-alpha.3). Older releases have been withdrawn, so links to old versions or wrong file names return 404. If the current link still fails, check your network and report the link and error on [GitHub Issues](https://github.com/sundy-li/rallycut/issues). Never send passwords or access tokens.

## I can't reach the download page or GitHub. What now?

Ask the maintainer for **the same installer and its SHA-256 checksum**, confirm the system and version, then install. This guide can be saved or copied and read offline; it does not depend on the demo site. First-run setup still needs its download sources to be reachable. Don't treat packages from unknown third parties as an official mirror, and don't use the source code ZIP as the app.

## Why does the first launch still download something?

The full Windows installer already contains Python, the video tools and the analysis dependencies, unpacked during installation. If the model is missing, you still click to download about 6 MB of model weights. On macOS, first-run setup downloads the app's own dependencies and the model. The weights are not bundled with the installer. After setup, videos are processed on your computer and never uploaded.

## Does the new version set up the environment by itself?

`v0.1.0-alpha.3` includes a first-run setup. It checks locally first and downloads missing parts only after you click to confirm. If setup fails you can retry; you cannot start editing until it is ready. The full Windows installer usually only needs the model; macOS prepares a private environment for your platform. Neither changes your system Python or global PATH.

## The app can't find Python, FFmpeg or FFprobe

Make sure you are using this version's full installer, not an EXE copied on its own. A Windows installation should contain a `runtimes/` folder; the portable fallback needs the runtime ZIP in the same folder as the EXE. Don't work around it with pip or by editing the system PATH. Reinstall this version instead; your user data is kept. On macOS, retry from the setup page. If it still fails, expand and copy the full error and see the [install guide](getting-started.en.md).

## Why does the setup page appear again on the second launch?

After an upgrade, or when the runtime or model changes, the app runs one full check again. This is expected. On Windows, once the check has passed in an environment, later launches go straight to the project list without the setup page; you don't need to delete projects or data folders. If every launch runs the full check, report the app version and the error details.

## Videos with Chinese paths or on a Mac shared folder won't import

This version imports Chinese and other non-English paths directly; you don't need to rename files. If it still fails, check that File Explorer can open the same file. Access and permissions for shared folders such as `\\Mac\Home` are handled by the system or virtual machine. Windows on ARM and shared folders have not been tested on real machines yet, so feedback is welcome. Don't move source videos or overwrite earlier exports while troubleshooting.

## The system warns about an unknown developer or publisher

The preview builds are not yet signed by a registered publisher or notarized by Apple. Check the source and checksum, then follow the system prompt; contact the maintainer if unsure. Don't turn off Gatekeeper, SmartScreen or your antivirus.

## The preview shows the trajectory, but the export doesn't

The preview switch and the export options are separate. In **the export bar, under “Export overlays” (导出叠加)**, tick “Ball trajectory” (球轨迹); tick “Rally numbers” (回合编号) if you also want the number in the top-left corner. These settings are saved in the project. Trajectories outside the playing area are not drawn, and stretches where no ball was detected get no invented trajectory.

## Exporting rally numbers says a font is missing

Rally numbers need a Chinese font available on your computer. Turn off “Rally numbers” to finish the export, then contact the maintainer to check the font. This doesn't affect rally cutting or the trajectory option. Don't install font packs from unknown sources.

## Can I cut by hand without machine analysis?

Yes. After importing a video, press `I` to mark a start and `O` to mark an end, or click the plus button in the rally list, then adjust the boundaries, tick the clips and export. You don't need to run analysis, but the first-run setup in the [install guide](getting-started.en.md) is still required.

Manual clips don't get a ball trajectory automatically. For a trajectory overlay, the video needs trajectory data from an analysis. Rally numbers can be used on their own.

## Rallies are split wrongly or missing

Click a rally to replay it, double-click its start or end time to fix it, or add a rally by hand with `I` and `O`. A machine rally you corrected also counts as a manual result. Right-click to delete false detections or to mark a point as invalid or a highlight. Occlusion, slow motion and camera changes can all affect detection, so automatic results are no substitute for a review.

## How do my manual edits override the machine result?

Tick the rallies you want and export. When “Rallies overlap. How should they be exported?” (回合有重叠，怎么导出？) appears, choose **“Manual rallies override analysis”** (人工回合覆盖分析回合), then click “Export this way” (按此方式导出). Analysis rallies that overlap a manual rally are **skipped entirely**; other ticked, valid analysis rallies that don't overlap are still exported.

For example, the machine rally is `00:10–00:20` and the manual rally is `00:12–00:18`. With zero padding, manual-first keeps only `00:12–00:18` and does not add back the two ends of the machine rally. To keep the whole covered range, choose “Merge ranges, no overlap” (合并区间，不重叠) instead. The [quick start](getting-started.en.md) compares all four options.

## Does overriding delete rallies or change the timeline?

No. Overriding only decides which rallies the export uses. It doesn't delete manual or analysis results from the project and doesn't touch the source video. You can export again with another option, using a new output file name.

The rules apply only to ticked, valid rallies. Overlaps between two manual rallies, or between two analysis rallies, are merged automatically; the four options handle overlaps between the manual and analysis sources.

## Why are both manual and analysis rallies in the list?

They are two results that can be kept side by side, especially after you correct rallies and then re-analyze. Overlaps in the list don't mean the export will repeat footage; the overlap option you choose at export decides. To see only one kind, use the source filter in the rally list. **Filtering the list is not the same as unticking: hiding a rally does not remove it from the export.**

## Will re-analysis lose my edits?

Rallies you added or corrected are kept; machine rallies you didn't touch are replaced. New analysis candidates that overlap your manual results are also kept for you to choose from at export.

Deleted machine rallies are not excluded permanently and may return after re-analysis. Unticked machine rallies stay unticked when they match a new candidate, but review the changed results anyway. Finishing a re-analysis clears the undo history, so save a backup of important projects first.

## How do I undo?

Use `⌘Z` on macOS or `Ctrl+Z` on Windows, or the undo button at the top. Undo covers rally edits, ticking and cutting rules. Undo history doesn't survive the session and is cleared when you switch projects or videos or when an analysis finishes. Export settings, project names and adding or removing videos cannot be undone.

## The preview is black or the export fails

For the preview, click “Retry preview” (重试预览) first and note the full error text. Some source codecs aren't supported by the system player; save a copy of the video as a compatible H.264 MP4 and import it as a new video. Don't overwrite the original.

For exports, use a new `.mp4` file name and check free space, folder permissions and FFmpeg. If hardware encoding isn't available, the app tries software encoding, which can be slower. After a failure, don't treat the unfinished file as a finished export.

## I moved to another computer and the videos are missing

Projects store only the location of the source videos, not the files. Moving, renaming or replacing a source video can break the link, and the app can't relocate it automatically yet. Keep the original paths, or re-import and keep a copy of the old project.

## How do I send feedback?

Open an issue on [GitHub Issues](https://github.com/sundy-li/rallycut/issues) (requires a GitHub account) or contact the maintainer. Please include:

```text
App version, operating system and chip:
Steps:
Expected and actual result:
Full error text:
Time range in the source video (e.g. 00:12:30–00:12:42):
```

Logs and projects may contain your user name, video names and absolute paths; check and redact them before sending. Don't send whole match videos, complete projects, passwords or access tokens by default. If a short clip is needed, first make sure of copyright, portrait rights and who will receive it.
