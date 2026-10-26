# 发布维护

本页面向维护者。用户入口是[安装指南](getting-started.zh-CN.md)，开发与实验分别见 [development.md](development.md)、[experiments.md](experiments.md)。

## 当前交付

- GitHub：`sundy-li/rallycut`，**private**。
- 本次版本：`v0.1.0-alpha.2`，预发布；安装包以该标签成功构建后的 Release Assets 为准。
- 免费网站：**https://rallycut-byc.pages.dev/**，中文指南：**https://rallycut-byc.pages.dev/guide/**。
- Cloudflare Pages 项目名是 `rallycut`，不是 `rallycut-byc`；平台分配的访问域名带后缀，部署仍使用 `--project-name rallycut`。
- 网站 Direct Upload，不会因 GitHub push 自动更新。构建额度与收费按平台当前条款，不默认无限免费。

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

视频经真实应用导出器生成，叠加保存的球轨迹和回合编号，原声保留；网页版本压缩为 720p H.264，预览 GIF 为短片段。来源与复现命令见[实验记录](experiments.md)。工作台录屏剪去原始文件开头 1 秒，完整保留其余约 18.67 秒，转为 1920×1128、30 FPS 的 H.264 MP4，原片无音轨。README 的 8 秒 GIF 与封面均取自该剪辑版；旧截图已移出网站。录屏不作为准确率证据，未公开 110 MB 原始 MOV。README 与页面分别展示“软件里如何拆回合”和“导出后的效果”。不要将此例外扩大为原片、完整项目、标注库、其他截图或模型权重。站点不使用第三方字体、分析脚本、表单或前端访问令牌。

演示 MP4 在生产 Pages 静态服务上缺少可用的 Range 响应，导致浏览器拖动回到开头。因此 `/media/rallycut-demo.mp4` 与 `/media/rallycut-workbench.mp4` 使用共享的 Pages Function 处理逻辑：从本站静态资源读取批准的视频，提供 GET / HEAD、单段 `206` 和越界 `416`；没有任意 URL、私有文件代理或访问令牌。`_routes.json` 把 Function 限定在这两个已批准的视频路径，其余页面仍静态托管。此端点计入 Pages Functions 的账户额度；请求上限以 Cloudflare 当前计划为准，不宣称无限免费。

## 源码提交与版本

用户要求本次整理为**一个根提交**。操作前备份原 Git refs 和工作区；把最新源码、依赖清单、文档与允许的短演示审查后纳入新根提交。主分支更新使用 `--force-with-lease`，远端已变化时停止，不覆盖未知提交。不要把本次一次性的历史整理当日常发布流程。

后续常规发布不必再次改历史：

```bash
git status --short
# 确认本版已提交、测试通过且标签未占用
git tag v0.1.0-alpha.2
git push origin main
git push origin v0.1.0-alpha.2
gh run list --repo sundy-li/rallycut --workflow release.yml --limit 5
```

发布 workflow 在 macOS / Windows 原生 runner 构建，生成 `SHA256SUMS-macos.txt`、`SHA256SUMS-windows.txt`，两个平台成功后创建预发布 Release。编译成功不等于全新机器首启验收，也不等于 Windows 真机验收。

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

测试覆盖 320 / 375 / 390 / 768 / 1024 / 1440px：首页与四篇指南无横向溢出，真实视频在生产 CSP 下解码、播放、跳转，下载入口和键盘跳转正文可用。截图只保存在系统临时目录，不提交。Node 测试另检查允许列表、链接、版本、README 长度、资源体积和私有权限提示。

## 新版验收后再清理旧版

顺序不能倒置：

1. 新标签的 Release 与测试 workflow 成功。
2. 重新下载新 Assets，核验 SHA-256；确认 macOS universal、production、ad-hoc 签名以及不含权重／原片。
3. 部署 Pages，检查页面、指南、演示视频与新版本链接。
4. 按用户要求删除旧 `v0.1.0-alpha.1` Release 及标签，保留本地备份，不自动重建旧版。

```bash
gh release delete v0.1.0-alpha.1 --repo sundy-li/rallycut --yes --cleanup-tag
```

清理远端旧标签后也应删除本地旧标签，以免以后误推。只操作这个明确的旧版本，不批量删除其他版本或仓库。

## 验收与回退

发布前检查：

- 仓库仍 private；主分支只有本次整理后的一个提交。
- 最新源码在包中，Go / Python 运行时资源清单完整，默认测试不依赖用户私有素材。
- 安装包及校验清单齐全；没有模型、原片、项目、运行日志或凭据。
- macOS `codesign --verify --deep --strict`、`lipo -archs` 和 production 构建信息通过；ad-hoc 不是 Apple 公证。
- 首页、四篇指南、MP4、GIF 与封面返回 200，未知路径、`/.git/config`、模型路径返回 404，视频 MIME 和 Range 响应可用。
- 页面没有让用户误以为匿名可下载，也没有声称 Windows、Intel Mac 或全新机器已经实机验收。
- 旧版只在新版可用后删除；Pages 链接与 README 指向同一新版。

回退网站可以从本地备份源码重新构建部署；应用回退前先备份项目，不保证旧版可读新项目。撤下页面或 Release 不能收回已被下载的文件。停止种子测试时同时检查下载、协作者和公开站点权限。
