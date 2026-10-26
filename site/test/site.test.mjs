import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = fileURLToPath(new URL('../dist/', import.meta.url));
const config = JSON.parse(await fs.readFile(new URL('../release.json', import.meta.url), 'utf8'));
async function files(dir) {
  const result = [];
  for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
    const name = path.join(dir, entry.name);
    if (entry.isDirectory()) result.push(...await files(name)); else result.push(name);
  }
  return result;
}
const output = await files(dist);
const htmlFiles = output.filter(f => f.endsWith('.html'));

test('only explicitly public pages and static assets are built', () => {
  const relative = output.map(f => path.relative(dist, f)).sort();
  assert.deepEqual(relative, ['404.html', '_headers', '_routes.json', 'guide/faq.html', 'guide/getting-started.html', 'guide/index.html', 'guide/releases.html', 'icon.svg', 'index.html', 'media/rallycut-demo.mp4', 'media/rallycut-poster.jpg', 'media/rallycut-preview.gif', 'media/rallycut-workbench-poster.webp', 'media/rallycut-workbench-preview.gif', 'media/rallycut-workbench.mp4', 'robots.txt', 'styles.css']);
});
test('all local URLs resolve to a file and fragments resolve to an ID', async () => {
  for (const filename of htmlFiles) {
    const html = await fs.readFile(filename, 'utf8');
    assert.equal(/\{\{\w+\}\}/.test(html), false, filename);
    for (const [, href] of html.matchAll(/(?:href|src|poster)="([^"]+)"/g)) {
      if (/^https?:|^mailto:/.test(href)) continue;
      const [url, fragment] = href.split('#');
      let target = url ? path.resolve(dist, `.${url}`) : filename;
      if (url.endsWith('/')) target = path.join(target, 'index.html');
      assert.ok(target.startsWith(dist), href);
      await fs.access(target);
      if (fragment) {
        const content = await fs.readFile(target, 'utf8');
        assert.ok(content.includes(`id="${fragment}"`), `${filename}: missing ${href}`);
      }
    }
  }
});
test('private beta access and dependency limitations remain visible', async () => {
  const html = await fs.readFile(path.join(dist, 'index.html'), 'utf8');
  assert.ok(html.includes(config.releaseUrl));
  assert.ok(html.includes('下载需要 GitHub 仓库权限。'));
  for (const term of ['Python 3.10+', 'FFmpeg', '正式发布者签名／Apple 公证', '不捆绑模型权重', '不支持匿名下载']) assert.ok(html.includes(term), term);
  assert.equal(/<script|<iframe|<form/i.test(html), false);
});
test('site has no private runtime artifacts, local source paths or unresolved markdown links', async () => {
  for (const filename of htmlFiles) {
    const html = await fs.readFile(filename, 'utf8');
    assert.equal(/\/Users\/|github_pat_|ghp_[A-Za-z0-9]+|<script/i.test(html), false, filename);
    assert.equal(/href="(?!https?:)[^"]+\.md"/.test(html), false, filename);
    assert.ok(html.includes('name="viewport"'));
    assert.ok(html.includes('<html lang="zh-CN">'));
    assert.equal(/SEED PREVIEW|Inside the app|Get the seed preview|Skip to content|GUIDE|Page not found|Your browser does not support/.test(html), false, filename);
  }
});
test('CSP restricts the static site and excludes inline scripts', async () => {
  const headers = await fs.readFile(path.join(dist, '_headers'), 'utf8');
  assert.ok(headers.includes("default-src 'none'"));
  assert.ok(headers.includes("style-src 'self'"));
  assert.ok(headers.includes("media-src 'self'"));
  assert.ok(headers.includes("frame-ancestors 'none'"));
  assert.equal(headers.includes('unsafe-inline'), false);
});
test('real demo is accessible, opt-in to load, and within static-host file limits', async () => {
  const html = await fs.readFile(path.join(dist, 'index.html'), 'utf8');
  assert.ok(/<video\b[^>]*\bcontrols playsinline preload="none"/.test(html));
  assert.ok(html.includes('src="/media/rallycut-demo.mp4"'));
  assert.ok(html.includes('poster="/media/rallycut-poster.jpg"'));
  assert.ok(html.includes('id="demo-caption"'));
  assert.equal(/\bautoplay\b/.test(html), false);
  assert.ok((await fs.stat(path.join(dist, 'media/rallycut-demo.mp4'))).size < 20 * 1024 * 1024);
  assert.ok((await fs.stat(path.join(dist, 'media/rallycut-preview.gif'))).size < 4 * 1024 * 1024);
});
test('README stays concise and its demo and release links exist', async () => {
  const readme = await fs.readFile(new URL('../../README.md', import.meta.url), 'utf8');
  assert.ok(readme.split('\n').length <= 50);
  assert.ok(readme.includes(config.releaseUrl));
  assert.ok(readme.includes('site/public/media/rallycut-preview.gif'));
  assert.ok(readme.includes('site/public/media/rallycut-workbench-preview.gif'));
  assert.ok(readme.includes('#workbench'));
  assert.equal(/tt[\s_-]*cut|huji/i.test(readme), false);
  assert.ok(readme.indexOf('rallycut-workbench-preview.gif') < readme.indexOf('rallycut-preview.gif'));
  assert.ok(/<details>\s*<summary>补充演示：[\s\S]*rallycut-preview\.gif[\s\S]*<\/details>/.test(readme));
});
test('workbench is the primary hero video and exported highlights are a later secondary demo', async () => {
  const html = await fs.readFile(path.join(dist, 'index.html'), 'utf8');
  const hero = html.match(/<section class="hero"[\s\S]*?<\/section>/)?.[0] || '';
  assert.ok(hero.includes('id="workbench-video"'));
  assert.ok(hero.includes('primary-demo'));
  assert.equal(hero.includes('id="export-demo-video"'), false);
  assert.ok(html.indexOf('id="workbench-video"') < html.indexOf('id="export-demo-video"'));
  assert.ok(/<section class="export-showcase"[\s\S]*secondary-demo[\s\S]*id="export-demo-video"/.test(html));
  for (const label of ['先看主界面', '补充演示', '人工回合覆盖分析回合']) assert.ok(html.includes(label), label);
});
test('trimmed workbench recording replaces the screenshot without replacing the export demo', async () => {
  const html = await fs.readFile(path.join(dist, 'index.html'), 'utf8');
  for (const term of ['id="workbench"', 'id="demo"', 'id="workbench-video"', 'id="export-demo-video"', 'src="/media/rallycut-workbench.mp4"', 'poster="/media/rallycut-workbench-poster.webp"', '已剪去开头 1 秒', '无音轨', '回合列表', '回合时间轴', '复核与导出']) assert.ok(html.includes(term), term);
  assert.equal(html.includes('rallycut-workbench.webp'), false);
  assert.equal((html.match(/<video /g) || []).length, 2);
  assert.equal((html.match(/controls playsinline preload="none"/g) || []).length, 2);
  assert.ok((await fs.stat(path.join(dist, 'media/rallycut-workbench.mp4'))).size < 20 * 1024 * 1024);
  assert.ok((await fs.stat(path.join(dist, 'media/rallycut-workbench-preview.gif'))).size < 4 * 1024 * 1024);
  const poster = await fs.readFile(path.join(dist, 'media/rallycut-workbench-poster.webp'));
  assert.equal(poster.toString('ascii', 0, 4), 'RIFF');
  assert.equal(poster.toString('ascii', 8, 12), 'WEBP');
});
