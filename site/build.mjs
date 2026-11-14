import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import MarkdownIt from 'markdown-it';

const root = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(root, 'dist');
const config = JSON.parse(await fs.readFile(path.join(root, 'release.json'), 'utf8'));
const md = new MarkdownIt({ html: false, linkify: false, typographer: false });
// Each locale is a fixed allow-list of user guides; engineering docs stay on GitHub.
const locales = {
  zh: {
    lang: 'zh-CN', prefix: '', switchLabel: 'English', switchLang: 'en',
    pages: [
      ['README.md', 'index.html', '中文文档'],
      ['getting-started.zh-CN.md', 'getting-started.html', '安装与快速开始'],
      ['faq.zh-CN.md', 'faq.html', '常见问题与反馈'],
      ['releases.zh-CN.md', 'releases.html', '更新说明'],
    ],
    description: 'RallyCut 种子用户中文使用指南：安装、复核乒乓球回合并在本地导出集锦。',
    skip: '跳转到正文', beta: '种子测试版', download: '下载种子版 ↗', guide: '使用指南', toc: '文档目录',
    note: '视频留在本机。<br>结果由你决定。', footer: '种子测试 · 请在分享日志前移除个人信息。',
    githubTitle: '在 GitHub 公开仓库中查看文档',
  },
  en: {
    lang: 'en', prefix: '/en', switchLabel: '中文', switchLang: 'zh-CN',
    pages: [
      ['README.en.md', 'index.html', 'Guide home'],
      ['getting-started.en.md', 'getting-started.html', 'Install and quick start'],
      ['faq.en.md', 'faq.html', 'FAQ and feedback'],
      ['releases.en.md', 'releases.html', 'Release notes'],
    ],
    description: 'RallyCut user guide: install, review table tennis rallies and export highlights on your own computer.',
    skip: 'Skip to content', beta: 'Seed preview', download: 'Download ↗', guide: 'User guide', toc: 'Guide contents',
    note: 'Videos stay on your computer.<br>You decide the result.', footer: 'Seed preview · Remove personal details before sharing logs.',
    githubTitle: 'View this document in the public GitHub repository',
  },
};
const other = { zh: 'en', en: 'zh' };
const guideUrl = (locale, file) => `${locales[locale].prefix}/guide/${file === 'index.html' ? '' : file}`;
const sources = new Map();
for (const [locale, { pages }] of Object.entries(locales)) {
  pages.forEach(([source, file]) => sources.set(source, guideUrl(locale, file)));
}
const escape = (value) => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
for (const key of ['repository', 'releaseUrl']) {
  const url = new URL(config[key]);
  if (url.origin !== 'https://github.com' || !url.pathname.startsWith('/sundy-li/rallycut')) {
    throw new Error(`Unexpected ${key}: only the RallyCut GitHub repository is allowed`);
  }
}
if (!/^[0-9A-Za-z.-]+$/.test(config.version)) throw new Error('Invalid version');
await fs.rm(dist, { recursive: true, force: true });
await fs.cp(path.join(root, 'public'), dist, { recursive: true });
await fs.copyFile(path.join(root, '../design/logo/final/rallycut-appicon.svg'), path.join(dist, 'icon.svg'));
for (const landing of ['index.html', 'en/index.html']) {
  let index = await fs.readFile(path.join(dist, landing), 'utf8');
  for (const [key, value] of Object.entries(config)) index = index.replaceAll(`{{${key}}}`, escape(value));
  if (/\{\{\w+\}\}/.test(index)) throw new Error(`Unresolved template variable in ${landing}`);
  await fs.writeFile(path.join(dist, landing), index);
}

const defaultLink = md.renderer.rules.link_open ?? ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  const href = token.attrGet('href') || '';
  if (sources.has(href)) token.attrSet('href', sources.get(href));
  else if (!/^(https?:|mailto:|#|\/)/.test(href)) {
    // Engineering documents are linked on public GitHub, not copied into Pages.
    token.attrSet('href', `${config.repository}/blob/main/docs/${href}`);
    token.attrSet('title', env.githubTitle);
  }
  return defaultLink(tokens, idx, options, env, self);
};
let count = 0;
for (const [locale, t] of Object.entries(locales)) {
  await fs.mkdir(path.join(dist, t.prefix, 'guide'), { recursive: true });
  for (const [source, filename, title] of t.pages) {
    const markdown = await fs.readFile(path.join(root, '../docs', source), 'utf8');
    const nav = t.pages.map(([, file, label]) => `<a href="${guideUrl(locale, file)}"${file === filename ? ' aria-current="page"' : ''}>${escape(label)}</a>`).join('');
    const self = guideUrl(locale, filename);
    const alt = guideUrl(other[locale], filename);
    const alternates = Object.values(locales).map(l => `<link rel="alternate" hreflang="${l.lang}" href="${l === t ? self : alt}">`).join('');
    const html = `<!doctype html>
<html lang="${t.lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><meta name="description" content="${escape(t.description)}"><title>${escape(title)} · RallyCut</title>${alternates}<link rel="icon" href="/icon.svg" type="image/svg+xml"><link rel="stylesheet" href="/styles.css"></head>
<body class="docs-page"><a class="skip-link" href="#content">${t.skip}</a><header class="site-header"><a class="brand" href="${t.prefix}/"><img src="/icon.svg" width="34" height="34" alt="">RallyCut<span class="beta">${t.beta}</span></a><nav aria-label="${escape(t.guide)}"><a class="nav-link" href="${t.prefix}/#download">${t.download}</a><a class="nav-link lang-switch" href="${alt}" hreflang="${locales[other[locale]].lang}" lang="${locales[other[locale]].lang}">${t.switchLabel}</a></nav></header><div class="docs-layout"><aside class="docs-nav"><p class="eyebrow">${t.guide}</p><nav aria-label="${escape(t.toc)}">${nav}</nav><p class="side-note">${t.note}</p></aside><main class="prose" id="content">${md.render(markdown, t)}</main></div><footer class="site-footer"><a href="${t.prefix}/">RallyCut</a><span>${t.footer}</span></footer></body></html>`;
    await fs.writeFile(path.join(dist, t.prefix, 'guide', filename), html);
    count++;
  }
}
console.log(`Built ${dist}: Chinese and English landing pages + ${count} guides (only approved demo media; no source videos or engineering reports).`);
