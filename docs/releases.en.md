# Release notes

[中文](releases.zh-CN.md) · English

## v0.1.0-alpha.4 · English docs and public downloads

[Open this GitHub release](https://github.com/sundy-li/rallycut/releases/tag/v0.1.0-alpha.4). This release ships **a macOS universal package, a full Windows x64 installer and a portable Windows fallback**, with SHA-256 checksum lists. The repository and installers are public and can be downloaded without an invitation or sign-in. The website only links to the download; it doesn't host source videos or projects.

### What's new

- **Editing and analysis are the same as v0.1.0-alpha.3.** This release mainly updates the documentation and download pages; projects from alpha.3 keep working.
- **English user guides**: install, quick start, FAQ and release notes are now in English, naming each button in English followed by its Chinese label. The app interface itself is still Chinese only.
- **New website address**: https://rallycut-app.pages.dev/ , with English at `/en/`. The top navigation switches language and links to the GitHub repository. The old address `rallycut-byc.pages.dev` is no longer updated.
- **Public source and installers**: the GitHub repository is now public; browsing the source and downloading installers need no invitation or sign-in.
- **Simpler Chinese guides**: the Chinese release notes and FAQ drop engineering jargon in favour of plain instructions.
- **One environment check after upgrading on Windows**: the runtime identifier changes with the version, so the first launch after upgrading from alpha.3 runs a full check once; later launches go straight to the project list again.

Everything below has been available since v0.1.0-alpha.3 and is unchanged.

### Installation and launch

- **Windows dependencies are ready at install time**: the full installer brings its own Python, analysis dependencies, FFmpeg / FFprobe and required runtime libraries. You don't install Python, edit PATH or run pip.
- **The model is downloaded separately**: model weights are not in the installer. When the model is missing on first use, about 6 MB is downloaded only after you confirm, then self-tested. A model that was prepared before and passes its checksum is reused.
- **Reopening goes straight into the app**: after the first full check passes on Windows, the result is remembered, and the setup page stays away while the environment is unchanged. After an upgrade the full check runs once more.
- **No more black command prompt windows**: background commands run silently and still keep their errors. File dialogs and File Explorer that you open yourself appear as usual.
- **macOS first-run setup**: the app checks locally first; if something is missing, you click to prepare, and it downloads its own private environment and model. You don't install Python or FFmpeg by hand, and your system Python is left alone.

### Windows usability and reliability

- Videos whose paths contain Chinese, spaces, symbols or emoji import directly; file names no longer turn into `?`. Shared-folder paths are kept as they are, but the system itself must be able to reach them.
- Single instance: launching again switches to the existing window.
- The window is sized to the screen's usable area and scaling, so it is less likely to spill off small screens, high scaling or around the taskbar.
- If the app is force-closed, its background analysis processes exit too, leaving fewer stray processes.

### Editing

- Automatic candidate rallies and ball trajectory preview; MP4 exports can include the ball trajectory and rally numbers.
- Double-click to fix start and end times, add rallies by hand, undo / redo, a settings panel and a shortcuts panel.
- Re-analysis keeps rallies you added or corrected. At export you choose manual first, analysis first, merge, or earlier one wins. These options only decide what goes into the export; they don't delete project rallies or overwrite the source video or earlier exports.
- The ball is analyzed even when no table is found. Without a reliable table position, the app does not guess net or out calls. Automatic results still need review.

### Download and upgrade

| System / use | File |
| --- | --- |
| macOS Apple Silicon / Intel | `RallyCut-0.1.0-alpha.4-macos-universal.zip` |
| Windows (recommended) | `RallyCut-0.1.0-alpha.4-windows-amd64-setup.exe` |
| Windows portable fallback | `RallyCut-0.1.0-alpha.4-windows-amd64.exe`, plus `RallyCut-runtime-windows-amd64.zip` in the same folder as the EXE |
| Checksums | `SHA256SUMS-macos.txt`, `SHA256SUMS-windows.txt`; `runtime-bundle.json` lists the runtime contents |

Quit the old app and back up your projects before installing or replacing it. **You don't need to uninstall or delete the user data folder.** Keep your source videos' names and paths, and try a short clip before returning to important projects. Downloads of earlier test builds have been withdrawn and their links no longer work; user projects and videos are unaffected.

### Tested and not yet tested

Before every release, installation and uninstallation, a real model run, importing Chinese paths, preview, export and repeated launches are checked in automated macOS and Windows x64 environments. The build results on this release are the reference.

Not yet tested on real hardware: Windows 11 on ARM virtual machines, clicking native file dialogs, Mac shared folders (`\\Mac\Home`), multi-monitor use and Intel Macs. The Windows package is x64 and runs under emulation on ARM, with no promise of acceleration. The installers are not yet formally signed or notarized by Apple; if the system blocks them, check the source first and don't turn off system security. Redistribution and commercial-use terms for the model are still being confirmed.

[Install and use](getting-started.en.md) · [FAQ and feedback](faq.en.md)
