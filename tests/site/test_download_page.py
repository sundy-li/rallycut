"""Browser QA of the Chinese site and both real videos; no desktop app/private projects.
After `npm --prefix site run build`:
  uv run --with playwright python tests/site/test_download_page.py
Set RALLYCUT_SITE_URL to test a deployed site. Screenshots remain in system temp.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import io
import json
import os
import re
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / 'site/dist'
ARTIFACTS = Path(tempfile.gettempdir()) / 'rallycut-download-site'
MEDIA = {'/media/rallycut-demo.mp4', '/media/rallycut-workbench.mp4'}


class StaticHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        # Local fixture only; production handlers are covered by Node tests and
        # live Pages QA. Only these two approved local assets can use this route.
        media_path = urlsplit(self.path).path
        if media_path not in MEDIA:
            return super().send_head()
        data = (DIST / media_path.lstrip('/')).read_bytes()
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
            pass  # Browsers cancel initial transfers to issue seek requests.


def check_video(page, selector, minimum, maximum, seek):
    video = page.locator(selector)
    assert video.get_attribute('preload') == 'none'
    assert video.get_attribute('autoplay') is None
    # Native media events avoid polling expression eval blocked by our CSP.
    result = video.evaluate('''async (video, target) => {
        video.muted = true;
        await new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('Video load timed out')), 45000);
            video.addEventListener('loadeddata', () => { clearTimeout(timer); resolve(); }, {once: true});
            video.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Video decode failed')); }, {once: true});
            video.load();
        });
        const played = new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('Playback timed out')), 20000);
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
            const timer = setTimeout(() => reject(new Error('Seek timed out')), 30000);
            video.addEventListener('seeked', () => { clearTimeout(timer); resolve(); }, {once: true});
            video.currentTime = target;
        });
        return {duration: video.duration, position: video.currentTime, width: video.videoWidth, height: video.videoHeight};
    }''', seek)
    assert minimum < result['duration'] < maximum, (selector, result)
    # A seeked event alone can mean a failed seek clamped back to 0.
    assert abs(result['position'] - seek) < .1, (selector, result)
    video.scroll_into_view_if_needed()
    video.screenshot(path=str(ARTIFACTS / f'{selector[1:]}-frame.png'))
    print('PASS video:', selector, result)
    return result


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
            page = browser.new_page(locale='zh-CN')
            page.on('pageerror', lambda e: errors.append(str(e)))
            routes = ['/', '/guide/', '/guide/getting-started.html', '/guide/faq.html', '/guide/releases.html']
            for width in [320, 375, 390, 768, 1024, 1440]:
                page.set_viewport_size({'width': width, 'height': 1000})
                for route in routes:
                    response = page.goto(base + route, wait_until='networkidle')
                    assert response.status == 200, (width, route, response.status)
                    assert 'media-src' in response.headers['content-security-policy']
                    assert page.locator('html').get_attribute('lang') == 'zh-CN'
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, route, 'overflow')
                print(f'PASS: {width}px, Chinese landing + four guides')
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.goto(base, wait_until='networkidle')
            assert page.locator('video').first.get_attribute('id') == 'workbench-video'
            assert page.locator('.hero video').count() == 1
            assert page.locator('.hero #workbench-video').count() == 1
            assert page.locator('#demo .secondary-demo').count() == 1
            assert page.locator('#demo').evaluate('(el) => el.getBoundingClientRect().top > innerHeight')
            assert page.locator('#workbench-video').evaluate('(el) => el.getBoundingClientRect().top < innerHeight')
            page.get_by_role('link', name='看软件如何拆回合').click()
            assert page.evaluate('location.hash') == '#workbench'
            result = check_video(page, '#workbench-video', 18.5, 18.8, 10)
            assert (result['width'], result['height']) == (1920, 1128)
            page.locator('#workbench').screenshot(path=str(ARTIFACTS / 'workbench-desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#workbench').screenshot(path=str(ARTIFACTS / 'workbench-mobile.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.set_viewport_size({'width': 1440, 'height': 1000})
            check_video(page, '#export-demo-video', 29, 30, 25)
            page.evaluate('window.scrollTo(0, 0)')
            page.screenshot(path=str(ARTIFACTS / 'desktop.png'), full_page=True)
            page.get_by_role('link', name='下载种子版', exact=True).click()
            assert page.evaluate('location.hash') == '#download'
            config = json.loads((ROOT / 'site/release.json').read_text())
            assert page.locator('.release-link').get_attribute('href') == config['releaseUrl']
            assert config['releaseUrl'].endswith('/v' + config['version'])
            page.set_viewport_size({'width': 390, 'height': 844})
            page.goto(base, wait_until='networkidle')
            page.screenshot(path=str(ARTIFACTS / 'mobile.png'), full_page=True)
            page.keyboard.press('Tab')
            assert page.locator('.skip-link').evaluate('(a) => document.activeElement === a')
            page.keyboard.press('Enter')
            assert page.evaluate('location.hash') == '#main'
            assert not errors, errors
            browser.close()
            print('PASS: Chinese navigation, both videos play and seek precisely, mobile layout, keyboard and no page errors')
            print(f'Artifacts: {ARTIFACTS}')
    finally:
        if server:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
