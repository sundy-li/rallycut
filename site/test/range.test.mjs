import test from 'node:test';
import assert from 'node:assert/strict';
import { onRequest } from '../functions/media/rallycut-demo.mp4.js';
import { onRequest as workbenchRequest } from '../functions/media/rallycut-workbench.mp4.js';

const url = 'https://example.pages.dev/media/rallycut-demo.mp4';
const fixture = new Uint8Array(Array.from({ length: 100 }, (_, i) => i));
async function fetchDemo({ method = 'GET', range, validator, assetStatus = 200 } = {}) {
  const headers = new Headers();
  if (range) headers.set('Range', range);
  if (validator) headers.set('If-Range', validator);
  let assetCalls = 0;
  const response = await onRequest({ request: new Request(url, { method, headers }), env: { ASSETS: {
    async fetch(request) {
      assetCalls++;
      assert.equal(request.url, url);
      assert.equal(request.headers.has('Range'), false);
      assert.equal(request.headers.has('If-Range'), false);
      return new Response(method === 'HEAD' || assetStatus !== 200 ? null : fixture.slice(), { status: assetStatus, headers: {
        'Content-Type': 'video/mp4', 'Content-Length': '100', ETag: '"demo-v1"', 'Last-Modified': 'Mon, 26 Oct 2026 00:00:00 GMT',
      } });
    },
  } } });
  return { response, assetCalls };
}

test('both explicitly approved videos share the same tested range handler', () => {
  assert.equal(workbenchRequest, onRequest);
});

test('only GET and HEAD are allowed; no remote URL or asset path can be supplied', async () => {
  const { response, assetCalls } = await fetchDemo({ method: 'POST' });
  assert.equal(response.status, 405);
  assert.equal(response.headers.get('Allow'), 'GET, HEAD');
  assert.equal(assetCalls, 0);
});
test('full GET and HEAD advertise seeking and keep binary/privacy headers', async () => {
  for (const method of ['GET', 'HEAD']) {
    const { response } = await fetchDemo({ method, range: 'bytes=0-9' });
    assert.equal(response.status, method === 'HEAD' ? 200 : 206);
    assert.equal(response.headers.get('Accept-Ranges'), 'bytes');
    assert.equal(response.headers.get('Content-Type'), 'video/mp4');
    assert.equal(response.headers.get('X-Content-Type-Options'), 'nosniff');
    assert.equal(response.headers.get('X-Robots-Tag'), 'noindex, nofollow');
    const body = new Uint8Array(await response.arrayBuffer());
    assert.equal(body.length, method === 'HEAD' ? 0 : 10);
  }
  const { response } = await fetchDemo();
  assert.equal(response.status, 200);
  assert.deepEqual(new Uint8Array(await response.arrayBuffer()), fixture);
});
test('closed, open, suffix and clipped byte ranges return exact 206 bytes', async () => {
  for (const [range, start, end] of [['bytes=0-9', 0, 9], ['bytes=25-', 25, 99], ['bytes=-10', 90, 99], ['bytes=95-1000', 95, 99], ['bytes=-1000', 0, 99]]) {
    const { response } = await fetchDemo({ range });
    assert.equal(response.status, 206, range);
    assert.equal(response.headers.get('Content-Range'), `bytes ${start}-${end}/100`);
    assert.equal(response.headers.get('Content-Length'), String(end - start + 1));
    assert.deepEqual(new Uint8Array(await response.arrayBuffer()), fixture.slice(start, end + 1));
  }
});
test('unsatisfiable ranges return bounded 416, not incorrect full bodies', async () => {
  for (const range of ['bytes=100-', 'bytes=20-10', 'bytes=-0', 'bytes=99999999999999999999-']) {
    const { response } = await fetchDemo({ range });
    assert.equal(response.status, 416, range);
    assert.equal(response.headers.get('Content-Range'), 'bytes */100');
    assert.equal((await response.arrayBuffer()).byteLength, 0);
  }
});
test('malformed/multipart ranges and stale If-Range validators fall back to 200', async () => {
  for (const range of ['bytes=', 'bytes=-', 'bytes=0-4,10-14', 'items=0-10', 'bytes=one-two']) {
    const { response } = await fetchDemo({ range });
    assert.equal(response.status, 200, range);
    assert.equal((await response.arrayBuffer()).byteLength, 100);
  }
  for (const validator of ['"old-version"', 'W/"demo-v1"']) {
    const { response } = await fetchDemo({ range: 'bytes=0-9', validator });
    assert.equal(response.status, 200);
  }
  for (const validator of ['"demo-v1"', 'Mon, 26 Oct 2026 00:00:00 GMT']) {
    const { response } = await fetchDemo({ range: 'bytes=0-9', validator });
    assert.equal(response.status, 206);
  }
});
test('missing or conditionally cached static assets preserve their status', async () => {
  for (const assetStatus of [304, 404, 500]) {
    const { response } = await fetchDemo({ range: 'bytes=0-9', assetStatus });
    assert.equal(response.status, assetStatus);
  }
});
