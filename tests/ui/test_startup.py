"""Ready/opening startup must never mount the setup screen (Wails fixture)."""
import os
from playwright.sync_api import sync_playwright, expect

URL=os.getenv('RALLYCUT_TEST_URL','http://127.0.0.1:5187')
BRIDGE=r"""
(() => {
 let setup={state:INITIAL_STATE,revision:1,step:'ready',progress:1,message:'cached ready',detail:''};
 const listeners=new Set();window.__startupCalls=[];window.__setupFlashed=false;
 new MutationObserver(records=>{
   for(const r of records)for(const n of r.addedNodes){
     if(n.nodeType===1&&(n.matches('.setup-screen')||n.querySelector('.setup-screen')))window.__setupFlashed=true;
   }
 }).observe(document,{subtree:true,childList:true});
 window.runtime={EventsOn:(name,cb)=>{const item=[name,cb];listeners.add(item);return()=>listeners.delete(item);}};
 window.__finishBoot=()=>{setup={...setup,state:'ready',revision:2};for(const [name,cb] of listeners)if(name==='setup:progress')cb({...setup});};
 window.go={backend:{App:{
  GetState:()=>new Promise(resolve=>setTimeout(()=>resolve({setup:{...setup},project:null,project_path:'',dependencies:{},error:''}),120)),
  ListRecentProjects:async()=>[],
  StartSetup:async()=>{window.__startupCalls.push('start');throw new Error('must not start setup');},
  RefreshDependencies:async()=>{window.__startupCalls.push('probe');throw new Error('must not probe');}
 }}};
})();
"""

def main():
 with sync_playwright() as pw:
  browser=pw.chromium.launch(channel=os.getenv('RALLYCUT_BROWSER_CHANNEL','chrome') or None,headless=True)
  for initial in ['ready','opening']:
   page=browser.new_page(viewport={'width':1100,'height':850})
   page.add_init_script(BRIDGE.replace('INITIAL_STATE',repr(initial)))
   page.goto(URL)
   if initial=='opening':
    expect(page.locator('.app-opening')).to_be_visible()
    expect(page.locator('.setup-screen')).to_have_count(0)
    page.evaluate('window.__finishBoot()')
   expect(page.locator('.project-home')).to_be_visible()
   page.wait_for_load_state('networkidle')
   assert not page.evaluate('window.__setupFlashed'),'first-use UI flashed on cached startup'
   assert page.evaluate('window.__startupCalls')==[],'ready startup started setup or probes'
   page.keyboard.press('Meta+,')
   expect(page.get_by_role('dialog',name='设置')).to_be_visible()
   page.get_by_role('tab',name='运行环境').click()
   expect(page.get_by_role('button',name='完整重新检查运行环境')).to_be_enabled()
   assert page.evaluate('window.__startupCalls')==[],'opening environment settings must not run probes'
   page.get_by_role('button',name='关闭设置',exact=True).click()
   page.close()
  browser.close()
 print('PASS: cached-ready and opening-to-ready startup never mount the setup UI or start probes')

if __name__=='__main__':main()
