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
  assert.deepEqual(relative, ['404.html', '_headers', '_routes.json', 'guide/faq.html', 'guide/getting-started.html', 'guide/index.html', 'guide/releases.html', 'icon.svg', 'index.html', 'media/rallycut-demo.mp4', 'media/rallycut-poster.jpg', 'media/rallycut-preview.gif', 'robots.txt', 'styles.css']);
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
  assert.ok(html.includes('GitHub invitation required.'));
  for (const term of ['Python 3.10+', 'FFmpeg', 'not Developer ID signed or notarized', 'Weights are not bundled', 'Chinese interface']) assert.ok(html.includes(term), term);
  assert.equal(/<script|<iframe|<form/i.test(html), false);
});
test('site has no private runtime artifacts, local source paths or unresolved markdown links', async () => {
  for (const filename of htmlFiles) {
    const html = await fs.readFile(filename, 'utf8');
    assert.equal(/\/Users\/|github_pat_|ghp_[A-Za-z0-9]+|<script/i.test(html), false, filename);
    assert.equal(/href="(?!https?:)[^"]+\.md"/.test(html), false, filename);
    assert.ok(html.includes('name="viewport"'));
    assert.ok(/<html lang="(en|zh-CN)">/.test(html));
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
  assert.ok(/<video controls playsinline preload="none"/.test(html));
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
  assert.equal(/tt[\s_-]*cut|huji/i.test(readme), false);
});
