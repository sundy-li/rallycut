"""Static-site browser QA; does not start the desktop app or read private projects.
Run after `npm --prefix site run build`:
  uv run --with playwright python tests/site/test_download_page.py
Install Playwright Chromium if needed. Artifacts go to the system temp directory.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import io
import re
import os
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / 'site/dist'
ARTIFACTS = Path(tempfile.gettempdir()) / 'rallycut-download-site'


class StaticHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        # Local fixture only: production byte handling is tested separately in
        # site/test/range.test.mjs and against the deployed Pages Function.
        if urlsplit(self.path).path != '/media/rallycut-demo.mp4':
            return super().send_head()
        data = (DIST / 'media/rallycut-demo.mp4').read_bytes()
        length = len(data)
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
        partial = match is not None and bool(match[1] or match[2])
        start, end = 0, length - 1
        if partial:
            start = int(match[1]) if match[1] else max(0, length - int(match[2]))
            end = min(int(match[2]), length - 1) if match[1] and match[2] else length - 1
        if start >= length or end < start or (partial and not match[1] and int(match[2]) == 0):
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{length}')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return None
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type', 'video/mp4')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        if partial:
            self.send_header('Content-Range', f'bytes {start}-{end}/{length}')
        self.end_headers()
        return io.BytesIO(data[start:end + 1])

    def end_headers(self):
        for line in (DIST / '_headers').read_text().splitlines():
            if line.startswith('  ') and ':' in line:
                name, value = line.strip().split(':', 1)
                self.send_header(name, value.strip())
        super().end_headers()

    def log_message(self, *args):
        pass

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers cancel an initial media transfer when switching to playback.
            pass


def main():
    ARTIFACTS.mkdir(exist_ok=True)
    server = None
    base = os.environ.get('RALLYCUT_SITE_URL', '').rstrip('/')
    if not base:
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(StaticHandler, directory=str(DIST)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
    errors = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            routes = ['/', '/guide/', '/guide/getting-started.html', '/guide/faq.html', '/guide/releases.html']
            for width in [320, 375, 390, 768, 1024, 1440]:
                page.set_viewport_size({'width': width, 'height': 1000})
                for route in routes:
                    response = page.goto(base + route, wait_until='networkidle')
                    assert response.status == 200, (width, route, response.status)
                    assert 'media-src' in response.headers['content-security-policy']
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, route, 'overflow')
                print(f'PASS: {width}px, landing + four guides')
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.goto(base, wait_until='networkidle')
            page.screenshot(path=str(ARTIFACTS / 'desktop.png'), full_page=True)
            assert page.locator('video').get_attribute('preload') == 'none'
            assert page.locator('video').get_attribute('autoplay') is None
            # Native media events avoid Playwright's polling expression eval,
            # which the production CSP deliberately disallows.
            page.locator('video').evaluate('''async (video) => {
                video.muted = true;
                const loaded = new Promise((resolve, reject) => {
                    const timer = setTimeout(() => reject(new Error('Video load timed out')), 30000);
                    video.addEventListener('loadeddata', () => { clearTimeout(timer); resolve(); }, {once: true});
                    video.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Video decode failed')); }, {once: true});
                });
                video.load();
                await loaded;
            }''')
            assert 29 < page.locator('video').evaluate('(video) => video.duration') < 30
            page.locator('video').evaluate('''async (video) => {
                const played = new Promise((resolve, reject) => {
                    const timer = setTimeout(() => reject(new Error('Playback timed out')), 15000);
                    const onTime = () => {
                        if (video.currentTime > .3) {
                            clearTimeout(timer); video.removeEventListener('timeupdate', onTime); resolve();
                        }
                    };
                    video.addEventListener('timeupdate', onTime);
                });
                await video.play();
                await played;
                video.pause();
                await new Promise((resolve, reject) => {
                    const timer = setTimeout(() => reject(new Error('Seek timed out')), 15000);
                    video.addEventListener('seeked', () => { clearTimeout(timer); resolve(); }, {once: true});
                    video.currentTime = 25;
                });
            }''')
            # A seeked event can fire after a failed seek back to 0. Check the
            # actual destination as well, including against real Pages hosting.
            position = page.locator('video').evaluate('(video) => video.currentTime')
            assert abs(position - 25) < .1, ('seek target', position)
            page.screenshot(path=str(ARTIFACTS / 'video-frame.png'))
            page.get_by_role('link', name='Get the seed preview').click()
            assert page.evaluate('location.hash') == '#download'
            assert '/v0.1.0-alpha.2' in page.locator('.release-link').get_attribute('href')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.goto(base, wait_until='networkidle')
            page.screenshot(path=str(ARTIFACTS / 'mobile.png'), full_page=True)
            page.keyboard.press('Tab')
            assert page.locator('.skip-link').evaluate('(a) => document.activeElement === a')
            page.keyboard.press('Enter')
            assert page.evaluate('location.hash') == '#main'
            assert not errors, errors
            browser.close()
            print('PASS: video decodes, plays and seeks with CSP; download navigation, mobile keyboard and no page errors')
            print(f'Artifacts: {ARTIFACTS}')
    finally:
        if server:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
