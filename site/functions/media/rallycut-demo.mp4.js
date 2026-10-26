// Pages' static MP4 response can omit byte-range support. Keep this handler
// restricted by routes to the approved showcase videos; it never accepts URLs
// or private paths. The workbench recording reuses this handler.
export async function onRequest({ request, env }) {
  if (!['GET', 'HEAD'].includes(request.method)) {
    return new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } });
  }
  const assetRequest = new Request(request.url, request);
  assetRequest.headers.delete('Range');
  assetRequest.headers.delete('If-Range');
  const asset = await env.ASSETS.fetch(assetRequest);
  if (asset.status !== 200) return asset;
  const headers = new Headers(asset.headers);
  headers.set('Accept-Ranges', 'bytes');
  headers.set('X-Content-Type-Options', 'nosniff');
  // _headers is not guaranteed on Functions responses, so retain the relevant
  // media/privacy restrictions explicitly as well.
  headers.set('Content-Security-Policy', "default-src 'none'; media-src 'self'; frame-ancestors 'none'");
  headers.set('X-Frame-Options', 'DENY');
  headers.set('X-Robots-Tag', 'noindex, nofollow');
  headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  const range = request.headers.get('Range');
  const ifRange = request.headers.get('If-Range');
  const matchesValidator = !ifRange ||
    (ifRange === headers.get('ETag') && !ifRange.startsWith('W/')) ||
    (headers.has('Last-Modified') && ifRange === headers.get('Last-Modified'));
  const match = /^bytes=(\d*)-(\d*)$/.exec(range ?? '');
  // Ignore unsupported/malformed/multi-range headers and stale validators.
  if (request.method === 'HEAD' || !matchesValidator || !match || (!match[1] && !match[2])) {
    return new Response(request.method === 'HEAD' ? null : asset.body, { status: 200, headers });
  }
  const bytes = await asset.arrayBuffer();
  const length = bytes.byteLength;
  const start = match[1] ? Number(match[1]) : Math.max(0, length - Number(match[2]));
  const end = match[1] ? (match[2] ? Math.min(Number(match[2]), length - 1) : length - 1) : length - 1;
  if (!Number.isSafeInteger(start) || start >= length || start > end || (!match[1] && Number(match[2]) === 0)) {
    headers.set('Content-Range', `bytes */${length}`);
    headers.set('Content-Length', '0');
    return new Response(null, { status: 416, headers });
  }
  headers.set('Content-Range', `bytes ${start}-${end}/${length}`);
  headers.set('Content-Length', String(end - start + 1));
  return new Response(bytes.slice(start, end + 1), { status: 206, headers });
}
