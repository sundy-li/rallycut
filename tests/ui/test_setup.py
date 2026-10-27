"""First-run UI gate, using a Wails bridge fixture (not a native installer test)."""
import os
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright, expect

URL = os.getenv('RALLYCUT_TEST_URL', 'http://127.0.0.1:5187')
ARTIFACTS = Path(tempfile.gettempdir()) / 'rallycut-setup-ui'
BRIDGE = r"""
(() => {
 const listeners=new Set();window.__setupCalls=[];
 let revision=1;
 let setup={state:'checking',revision,step:'check',message:'正在检查运行环境…',detail:'',progress:0,platform:'Windows · x64',indeterminate:true};
 window.runtime={EventsOn:(name,cb)=>{const e=[name,cb];listeners.add(e);return()=>listeners.delete(e);}};
 window.__setSetup=(next)=>{setup={...setup,...next,revision:++revision};for(const [n,cb] of listeners)if(n==='setup:progress')cb(structuredClone(setup));};
 window.__emitMenu=(name)=>{for(const [n,cb] of listeners)if(n==='menu:'+name)cb();};
 const getState=()=>({setup:structuredClone(setup),project:null,project_path:'',dependencies:{},error:''});
 window.go={backend:{App:{
  GetState:async()=>getState(),
  ListRecentProjects:async()=>{window.__setupCalls.push('list');return[];},
  StartSetup:async()=>{window.__setupCalls.push('start');window.__setSetup({state:'running',step:'python',progress:.02,error:'',indeterminate:false});const early=structuredClone(setup);return new Promise(resolve=>{window.__resolveStart=()=>resolve(early);});},
  RefreshDependencies:async()=>{window.__setupCalls.push('check');window.__setSetup({state:'checking',step:'check',progress:0,indeterminate:true});return getState();},
  OpenProject:async()=>{window.__setupCalls.push('open');throw new Error('must not open');},
 }}};
})();
"""


def main():
    ARTIFACTS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel=os.getenv('RALLYCUT_BROWSER_CHANNEL','chrome') or None,headless=True)
        page=browser.new_page(viewport={'width':1100,'height':850})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.add_init_script(BRIDGE);page.goto(URL);page.wait_for_load_state('networkidle')
        expect(page.get_by_role('heading',name='正在检查运行环境')).to_be_visible()
        expect(page.locator('.project-home,.app-shell')).to_have_count(0)
        assert page.evaluate('window.__setupCalls')==[]
        page.evaluate("window.__setSetup({state:'required',indeterminate:false,checks:[{id:'python',label:'Python',ready:false},{id:'media',label:'FFmpeg',ready:true}]})")
        start=page.get_by_role('button',name='开始准备环境',exact=True)
        expect(start).to_be_enabled()
        expect(page.get_by_text('环境未就绪前，不能进入剪辑界面。',exact=False)).to_be_visible()
        assert page.evaluate('window.__setupCalls')==[], 'must wait for consent'
        page.keyboard.press('Meta+o');page.keyboard.press('Control+o')
        page.evaluate("window.__emitMenu('settings');window.__emitMenu('help')")
        expect(page.get_by_role('dialog')).to_have_count(0)
        assert page.evaluate('window.__setupCalls')==[], 'shortcut bypassed setup gate'
        for width in [375,768,1100]:
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
        page.set_viewport_size({'width':1100,'height':850})
        page.screenshot(path=str(ARTIFACTS/'consent.png'),full_page=True)
        start.click()
        expect(page.get_by_role('heading',name='正在准备运行环境')).to_be_visible()
        expect(page.get_by_role('progressbar')).to_be_visible()
        assert page.evaluate("window.__setupCalls.filter(x=>x==='start').length")==1
        expect(page.get_by_role('button',name='开始准备环境',exact=True)).to_have_count(0)
        page.evaluate("window.__setSetup({step:'packages',progress:.56,indeterminate:true,detail:'正在安装推理依赖'})")
        expect(page.get_by_role('progressbar')).to_have_attribute('aria-valuenow','56')
        expect(page.locator('.project-home,.app-shell')).to_have_count(0)
        page.screenshot(path=str(ARTIFACTS/'progress.png'),full_page=True)
        page.evaluate("window.__setSetup({state:'failed',indeterminate:false,error:'下载失败，请检查网络\\nOSError: 模型加载失败，退出状态 0xc000001d'});window.__resolveStart()")
        expect(page.get_by_role('alert')).to_contain_text('下载失败')
        expect(page.get_by_role('button',name='重试准备环境')).to_be_enabled()
        page.locator('.setup-diagnostics summary').click()
        expect(page.locator('.setup-diagnostics pre')).to_contain_text('0xc000001d')
        expect(page.get_by_role('button',name='复制错误详情')).to_be_visible()
        expect(page.locator('.project-home,.app-shell')).to_have_count(0)
        page.screenshot(path=str(ARTIFACTS/'failure.png'),full_page=True)
        page.get_by_role('button',name='重新检测',exact=True).click()
        expect(page.get_by_role('heading',name='正在检查运行环境')).to_be_visible()
        assert page.evaluate("window.__setupCalls.filter(x=>x==='start').length")==1
        page.evaluate("window.__setSetup({state:'required',progress:0,indeterminate:false,error:''})")
        page.get_by_role('button',name='开始准备环境',exact=True).click()
        expect(page.get_by_role('heading',name='正在准备运行环境')).to_be_visible()
        page.evaluate("window.__setSetup({state:'ready',step:'ready',progress:1,indeterminate:false,python:'managed-python'});window.__resolveStart()")
        expect(page.locator('.project-home')).to_be_visible()
        expect(page.locator('.setup-screen')).to_have_count(0)
        assert page.evaluate("window.__setupCalls.filter(x=>x==='start').length")==2
        assert 'open' not in page.evaluate('window.__setupCalls')
        assert not errors,errors
        browser.close()
    print('PASS: consent required, unavailable workspace/shortcuts, real phase progress, failure/recheck/retry, and stale RPC cannot override ready')
    print(f'Artifacts: {ARTIFACTS}')

if __name__=='__main__':main()
