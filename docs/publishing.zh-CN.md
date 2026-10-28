# 发布维护

本页面向维护者。用户入口是[安装指南](getting-started.zh-CN.md)，开发与实验分别见 [development.md](development.md)、[experiments.md](experiments.md)。

## 当前交付

- GitHub：`sundy-li/rallycut`，**private**。
- 当前统一版本：`v0.1.0-alpha.3`，预发布；同一个 Release 提供 macOS 通用包与 Windows 完整安装器／免安装包，历史 Release 在新版验证后撤下。以标签成功构建的实际 Assets 为准。
- 免费网站：**https://rallycut-byc.pages.dev/**，中文指南：**https://rallycut-byc.pages.dev/guide/**。
- Cloudflare Pages 项目名是 `rallycut`，不是 `rallycut-byc`；平台分配的访问域名带后缀，部署仍使用 `--project-name rallycut`。
- 网站 Direct Upload，不会因 GitHub push 自动更新。构建额度与收费按平台当前条款，不默认无限免费。

## v0.1.0-alpha.3 发布结果（2026-10-28）

- [Release workflow 40617938515](https://github.com/sundy-li/rallycut/actions/runs/40617938515) 全部成功；发布标签固定在 `af2d04a02e14fb57f8d8560bf05a4c1640d07022`。本地源码随后将默认 `bundled-id` 同步为本版（正式 Windows 包在 CI 已生成相同 ID），[Test 40618252515](https://github.com/sundy-li/rallycut/actions/runs/40618252515) 通过。
- 7 项新附件已从 Release 重新下载并通过 `scripts/verify_release.py`；macOS 两个架构的 production 信息与签名再校验通过。Windows 安装器 **163,315,842 bytes**，macOS ZIP **9,002,509 bytes**。
- 安装后真实首次准备测试覆盖有／无嵌入归档清单的缺模型路径；重复启动 readiness 核对 **34.9575 ms**，未调用 Python／FFmpeg／完整检测。该耗时只代表该 x64 runner，不推断 ARM VM 性能。
- Pages 生产部署 `16ef1fd7`，中文首页／四篇指南、320–1440px 布局、两段演示播放及拖动、下载入口已通过真实浏览器检查；私有源码／模型路径返回 404。
- 已删除 6 个历史 Release、27 个上传附件及其本地／远端版本标签；当前唯一 Release 和版本标签为 `v0.1.0-alpha.3`。未删除 Git 提交或用户项目／原片／成片，仓库仍 private。
- 操作前的 Release 元数据、完整源码 refs bundle 与本次新附件保存在本机临时目录 `/tmp/rallycut-alpha3-release-20261028/`。bundle 只用于源码引用恢复，不包含已经删除的旧安装包，不是永久异地备份。

## 权限边界

Pages 默认公开，`noindex` 不是访问控制；源码和 Release 仍私有。没有仓库权限的用户不能匿名下载，GitHub 可能返回 404。

邀请协作者也会授予源码访问权限，不是“只下载”权限。如果要让普通用户只拿安装包，需另行确认独立分发仓库或对象存储方案，不能在网页里放 GitHub Token 绕过权限。不要把 GitHub PAT、Cloudflare Token、私有项目或源视频放进网站。

## 站点内容

`site/build.mjs` 只转换固定允许列表：`docs/README.md`、`getting-started.zh-CN.md`、`faq.zh-CN.md`、`releases.zh-CN.md`。技术报告与开发者文档不复制；链接需要仓库权限。

网站当前统一使用中文（包括首页、文档导航、视频说明和 404），暂不提供语言切换；RallyCut 与必要技术名称保留原名。

用户已明确批准以下产品展示资源进入 Git 和公开页面：30 秒内导出演示、用户提供的真实工作台录屏，以及两者的预览 GIF 与封面。

```text
site/public/media/rallycut-demo.mp4
site/public/media/rallycut-preview.gif
site/public/media/rallycut-poster.jpg
site/public/media/rallycut-workbench.mp4
site/public/media/rallycut-workbench-preview.gif
site/public/media/rallycut-workbench-poster.webp
```

视频经真实应用导出器生成，叠加保存的球轨迹和回合编号，原声保留；网页版本压缩为 720p H.264，预览 GIF 为短片段。来源与复现命令见[实验记录](experiments.md)。工作台录屏剪去原始文件开头 1 秒，完整保留其余约 18.67 秒，转为 1920×1128、30 FPS 的 H.264 MP4，原片无音轨。README 的 8 秒 GIF 与封面均取自该剪辑版；旧截图已移出网站。录屏不作为准确率证据，未公开 110 MB 原始 MOV。展示层级固定为“先看软件怎么用，再看导出效果”：主界面录屏是 Pages 首屏的首个视频（`#workbench`），画面空间优先；导出集锦放在后续“补充演示”区域（`#demo`），不与首要演示争抢注意力。README 同样先展示操作录屏 GIF，将导出效果收进可展开的补充演示。两段视频都保留原内容与拖动播放能力。不要将此例外扩大为原片、完整项目、标注库、其他截图或模型权重。站点不使用第三方字体、分析脚本、表单或前端访问令牌。

演示 MP4 在生产 Pages 静态服务上缺少可用的 Range 响应，导致浏览器拖动回到开头。因此 `/media/rallycut-demo.mp4` 与 `/media/rallycut-workbench.mp4` 使用共享的 Pages Function 处理逻辑：从本站静态资源读取批准的视频，提供 GET / HEAD、单段 `206` 和越界 `416`；没有任意 URL、私有文件代理或访问令牌。`_routes.json` 把 Function 限定在这两个已批准的视频路径，其余页面仍静态托管。此端点计入 Pages Functions 的账户额度；请求上限以 Cloudflare 当前计划为准，不宣称无限免费。

## 源码提交与版本

早期已按用户要求整理过一次根提交，那不是日常发布步骤。后续发布不改写提交历史，不 force push；本次“删除历史版本”仅指已确认的旧 Release／附件及版本标签，不删除 Git 提交、CI 记录、项目或视频。

常规发布：

```bash
git status --short
# 确认本版已提交、测试通过且标签未占用
git tag v0.1.0-alpha.3
git push origin main
git push origin v0.1.0-alpha.3
gh run list --repo sundy-li/rallycut --workflow release.yml --limit 5
```

`release.yml` 在 macOS runner 生成通用包并校验两种架构、production 和 ad-hoc 签名；Windows 复用 `windows-preview.yml` 的完整预制环境、模型真实前向、安装／卸载保留数据、Unicode 导入／预览／导出、readiness 缓存与原生 Job Object／窗口／EXE 资源测试，不能退回仅编译 EXE 的轻量发布。两端成功后用 `scripts/verify_release.py` 检查精确的 7 项交付、完整 SHA-256 覆盖和 runtime 版本，再创建预发布。手动 workflow_dispatch 只构建，不发布。

下载新附件后再执行 `python scripts/verify_release.py <下载目录> --version 0.1.0-alpha.3`。CI 成功不等于 Windows ARM VM、原生选择器点击、共享盘网络、Intel Mac 或多显示器真机验收。

`just package-macos` 会写 `build/bin`，不要与同一工作树中的 `wails dev` 并行；使用 CI 独立构建。本次不关闭用户开发实例、不上传旧 ZIP 冒充新构建。

## 站点构建与部署

本地首次授权（不要把凭据发到聊天）：

```bash
cd site
npm ci
npx wrangler login --scopes account:read user:read pages:write
npx wrangler whoami
```

已有项目不必再次 `project create`。每次更新：

```bash
cd site
npm ci
npm run build
npm test
npx wrangler pages deploy dist --project-name rallycut --branch main
```

**只部署 `site/dist`，不能部署仓库根目录或整个 `docs`。** 当前不配置 GitHub → Cloudflare 自动部署 secrets。CSP 仅允许本站静态样式、图像和视频，不为视频播放开放内联脚本或 `unsafe-eval`。

浏览器验收：

```bash
# 从仓库根目录运行，需要 Playwright Chromium
uv run --with playwright python tests/site/test_download_page.py
```

测试覆盖 320 / 375 / 390 / 768 / 1024 / 1440px：首页与四篇指南无横向溢出，真实视频在生产 CSP 下解码、播放、跳转，下载入口和键盘跳转正文可用。截图只保存在系统临时目录，不提交。Node 测试另检查允许列表、链接、版本、README 长度、资源体积、私有权限提示，以及主界面录屏位于首屏、导出集锦位于后续区域的展示顺序。

## 新版验收后再清理旧版

顺序不能倒置：

1. 新标签 Release 与测试 workflow 成功。
2. 重新下载全部新 Assets，运行 `scripts/verify_release.py`，确认 macOS 与 Windows 交付齐全；归档原 Release 元数据与 tag → commit 映射，备份只留本机临时目录，不提交或公开。
3. 部署 Pages，检查首页、指南、演示视频与新版本链接。
4. 本次用户明确要求删除所有历史版本；仅删除操作开始时已列出的 6 个旧 Release：`v0.1.0-alpha.2`、`v0.1.0-alpha.3-windows.1` 至 `.5`，包括附件及对应远端／本地标签，保留当前 `v0.1.0-alpha.3`。未来新增版本不自动纳入本次删除。
5. 重新列出远端 Releases／标签，确认唯一下载版本与站点、README 一致。删除标签不删除提交历史，也不删除用户数据。

```bash
# 对已经核对、明确授权的旧标签逐个执行；不要通配删除未知版本。
gh release delete <已确认的旧标签> --repo sundy-li/rallycut --yes --cleanup-tag
```

Release 附件删除不可直接撤销；Git refs 备份只保留源码定位，不等于附件备份。新版未验证或下载站未切换时，不能先删除旧版。

## 验收与回退

发布前检查：

- 仓库仍 private；保留正常提交历史，不为发版重新整理根提交。
- 最新源码在包中，Go / Python 运行时资源清单完整，默认测试不依赖用户私有素材。
- 安装包及校验清单齐全；没有模型、原片、项目、运行日志或凭据。
- macOS `codesign --verify --deep --strict`、`lipo -archs` 和 production 构建信息通过；ad-hoc 不是 Apple 公证。
- 首页、四篇指南、MP4、GIF 与封面返回 200，未知路径、`/.git/config`、模型路径返回 404，视频 MIME 和 Range 响应可用。
- 页面没有让用户误以为匿名可下载，也没有声称 Windows、Intel Mac 或全新机器已经实机验收。
- 旧版只在新版可用后删除；Pages 链接与 README 指向同一新版。

回退网站可以从本地备份源码重新构建部署；应用回退前先备份项目，不保证旧版可读新项目。撤下页面或 Release 不能收回已被下载的文件。停止种子测试时同时检查下载、协作者和公开站点权限。
