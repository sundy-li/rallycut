import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import MarkdownIt from 'markdown-it';

const root = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(root, 'dist');
const config = JSON.parse(await fs.readFile(path.join(root, 'release.json'), 'utf8'));
const md = new MarkdownIt({ html: false, linkify: false, typographer: false });
const pages = [
  ['README.md', 'index.html', '中文文档'],
  ['getting-started.zh-CN.md', 'getting-started.html', '安装与快速开始'],
  ['faq.zh-CN.md', 'faq.html', '常见问题与反馈'],
  ['releases.zh-CN.md', 'releases.html', '更新说明'],
];
const escape = (value) => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
for (const key of ['repository', 'releaseUrl']) {
  const url = new URL(config[key]);
  if (url.origin !== 'https://github.com' || !url.pathname.startsWith('/sundy-li/rallycut')) {
    throw new Error(`Unexpected ${key}: only the RallyCut GitHub repository is allowed`);
  }
}
if (!/^[0-9A-Za-z.-]+$/.test(config.version)) throw new Error('Invalid version');
await fs.rm(dist, { recursive: true, force: true });
await fs.mkdir(path.join(dist, 'guide'), { recursive: true });
await fs.cp(path.join(root, 'public'), dist, { recursive: true });
await fs.copyFile(path.join(root, '../design/logo/final/rallycut-appicon.svg'), path.join(dist, 'icon.svg'));
let index = await fs.readFile(path.join(dist, 'index.html'), 'utf8');
for (const [key, value] of Object.entries(config)) index = index.replaceAll(`{{${key}}}`, escape(value));
if (/\{\{\w+\}\}/.test(index)) throw new Error('Unresolved template variable');
await fs.writeFile(path.join(dist, 'index.html'), index);

const defaultLink = md.renderer.rules.link_open ?? ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  const href = token.attrGet('href') || '';
  const target = pages.find(([source]) => source === href);
  if (target) token.attrSet('href', `/guide/${target[1]}`);
  else if (!/^(https?:|mailto:|#|\/)/.test(href)) {
    // Engineering documents are linked on public GitHub, not copied into Pages.
    token.attrSet('href', `${config.repository}/blob/main/docs/${href}`);
    token.attrSet('title', '在 GitHub 公开仓库中查看文档');
  }
  return defaultLink(tokens, idx, options, env, self);
};
for (const [source, filename, title] of pages) {
  const markdown = await fs.readFile(path.join(root, '../docs', source), 'utf8');
  const nav = pages.map(([, file, label]) => `<a href="/guide/${file}"${file === filename ? ' aria-current="page"' : ''}>${label}</a>`).join('');
  const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><meta name="description" content="RallyCut 种子用户中文使用指南：安装、复核乒乓球回合并在本地导出集锦。"><title>${escape(title)} · RallyCut</title><link rel="icon" href="/icon.svg" type="image/svg+xml"><link rel="stylesheet" href="/styles.css"></head>
<body class="docs-page"><a class="skip-link" href="#content">跳转到正文</a><header class="site-header"><a class="brand" href="/"><img src="/icon.svg" width="34" height="34" alt="">RallyCut<span class="beta">种子测试版</span></a><a class="nav-link" href="/#download">下载种子版 ↗</a></header><div class="docs-layout"><aside class="docs-nav"><p class="eyebrow">使用指南</p><nav aria-label="文档目录">${nav}</nav><p class="side-note">视频留在本机。<br>结果由你决定。</p></aside><main class="prose" id="content">${md.render(markdown)}</main></div><footer class="site-footer"><a href="/">RallyCut</a><span>种子测试 · 请在分享日志前移除个人信息。</span></footer></body></html>`;
  await fs.writeFile(path.join(dist, 'guide', filename), html);
}
console.log(`Built ${dist}: landing page + ${pages.length} Chinese guides (only approved demo media; no source videos or engineering reports).`);
