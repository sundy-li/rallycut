"""Browser UI smoke test with an explicit in-memory Wails bridge fixture.

This does NOT test the native bridge or filesystem dialogs. Real media / Python
integration is covered by Go tests. Run with Playwright installed, e.g.:
  python .../webapp-testing/scripts/with_server.py \
    --server 'npm --prefix frontend run dev -- --port 5187 --strictPort' --port 5187 \
    -- python tests/ui/test_workbench.py
"""
from pathlib import Path
import json
import re
import os
import subprocess
import tempfile

from playwright.sync_api import sync_playwright, expect

URL = os.getenv('RALLYCUT_TEST_URL', 'http://127.0.0.1:5187')
ARTIFACTS = Path(tempfile.gettempdir()) / 'rallycut-ui'
ARTIFACTS.mkdir(exist_ok=True)

BRIDGE = """
(() => {
 const rallies = [
  {id:'mock-00001',start:1,end:4,confidence:0,score:20,selected:true,edited:false},
  {id:'mock-00002',start:6,end:14,confidence:0,score:40,selected:true,edited:false},
  {id:'mock-00003',start:17,end:28,confidence:0,score:60,selected:true,edited:false}
 ];
 const fixture = {schema_version:1,id:'ui-fixture',name:'UI 测试比赛',
  video:{path:'/test/fixture.mp4',name:'训练赛 · UI fixture.mp4',fingerprint:'test',
   duration:30,width:320,height:180,fps:30,codec:'h264',bit_rate:8233650,rotation:0,has_audio:false},
  raw_rallies:rallies,rallies:structuredClone(rallies),model:'mock-v1',manual_timeline:false,
  rules:{pre_roll:.5,post_roll:.8,min_duration:6},export_settings:{codec:'h264',encoder:'auto',bit_rate:0},updated_at:'2026-01-01T00:00:00Z'};
 const recentProjects=[{path:'/test/20261024-152433-rallycut.json',name:fixture.name,video_name:fixture.video.name,
  updated_at:fixture.updated_at,opened_at:fixture.updated_at,duration:fixture.video.duration,
  rallies:fixture.rallies.length,sources:1,analyzed:false,available:true}];
 let project = null;
 let history={undo:[],redo:[]};
 const snapTimeline=()=>copy({rallies:project.rallies,rules:project.rules,manual_timeline:project.manual_timeline});
 const recordTimeline=(before)=>{if(before.rallies.length&&JSON.stringify(before)!==JSON.stringify(snapTimeline())){history.undo.push(before);history.redo=[];}};
 const stepTimeline=(from,to)=>{const target=from.pop();if(!target)throw new Error('没有可撤销的操作');to.push(snapTimeline());Object.assign(project,copy(target));return copy(project);};
 const listeners = new Set();
 window.__calls=[];
 const copy = x => structuredClone(x);
 const emit = job => {project.job=job;for(const [name,cb] of listeners)if(name==='job:update')cb(copy(job));};
 // Route by event name like Wails does; window.__emitMenu simulates the native menu.
 window.runtime={EventsOn:(name,cb)=>{const entry=[name,cb];listeners.add(entry);return ()=>listeners.delete(entry);}};
 window.__emitMenu=(name)=>{for(const [n,cb] of listeners)if(n==='menu:'+name)cb();};
 window.go={backend:{App:{
  GetState:async()=>{
   const p=copy(project);
   if(window.__noGeometry && p?.analysis){p.analysis.table_bounds=[];p.analysis.table_segments=[{start:0,end:30,bounds:[],method:'unavailable'}];p.analysis.geometry_available=false;p.analysis.table_mode='off';}
   return {project:p,project_path:'/test/20261024-152433-rallycut.json',dependencies:{ffmpeg:true,ffprobe:true,python3:true,opencv_numpy:true,blurball_weights_torch:true},error:'',can_undo:Boolean(p)&&history.undo.length>0,can_redo:Boolean(p)&&history.redo.length>0};},
  Undo:async()=>{window.__calls.push('undo');return stepTimeline(history.undo,history.redo);},
  Redo:async()=>{window.__calls.push('redo');return stepTimeline(history.redo,history.undo);},
  DeleteProject:async(path)=>{window.__calls.push('delete-project');project=null;const i=recentProjects.findIndex(item=>item.path===path);if(i>=0)recentProjects.splice(i,1);},
  CreateProject:async(name)=>{window.__calls.push('create-project');project=copy(fixture);history={undo:[],redo:[]};project.name=name;return copy(project);},
  RenameProject:async(name)=>{window.__calls.push('rename-project');project={...project,name};const item=recentProjects[0];if(item)item.name=name;return copy(project);},
  ListRecentProjects:async()=>copy(recentProjects),
  OpenRecentProject:async(path)=>{window.__calls.push('recent');project=copy(fixture);history={undo:[],redo:[]};return copy(project);},

  ImportVideo:async()=>{window.__calls.push('import');project=copy(fixture);history={undo:[],redo:[]};return copy(project);},
  ImportVideos:async()=>{window.__calls.push('import');project=copy(fixture);history={undo:[],redo:[]};return copy(project);},
  OpenProject:async()=>{window.__calls.push('open');project=copy(fixture);history={undo:[],redo:[]};if(window.__noRallies){project.rallies=[];project.raw_rallies=[];}if(window.__legacyEmpty){project.rallies=[];project.manual_timeline=true;project.model='blurball-pretrained-v1';project.analysis={decoded_frames:900,detection_frames:450,track_count:1,elapsed_seconds:7.5,audio_impacts:0,warnings:[]};}return copy(project);}, SaveProjectAs:async()=>'/test/20261024-160000-rallycut.json',
  UpdateTimeline:async(rs,rules)=>{window.__calls.push('update');const before=snapTimeline();project.rallies=copy(rs).sort((a,b)=>a.start-b.start);project.rules=copy(rules);project.manual_timeline=true;if(project.rallies.length===0&&project.raw_rallies.length){project.rallies=copy(project.raw_rallies);project.manual_timeline=false;}recordTimeline(before);return copy(project);},
  SetExportSettings:async(settings)=>{window.__calls.push('encoding');project.export_settings=copy(settings);return copy(project);},
  SplitRally:async(id,at)=>{window.__calls.push('split');const before=snapTimeline();const r=project.rallies.find(r=>r.id===id);const oldEnd=r.end;r.end=at;r.edited=true;project.rallies.push({...r,id:'manual-split',start:at,end:oldEnd});project.rallies.sort((a,b)=>a.start-b.start);recordTimeline(before);return copy(project);},
  MergeRallies:async(ids)=>{window.__calls.push('merge');const before=snapTimeline();const rs=project.rallies.filter(r=>ids.includes(r.id));const merged={...rs[0],end:rs.at(-1).end,edited:true};project.rallies=[...project.rallies.filter(r=>!ids.includes(r.id)),merged].sort((a,b)=>a.start-b.start);recordTimeline(before);return copy(project);},
  StartAnalysis:async()=>{window.__calls.push('analysis');project.model='blurball-pretrained-v1';project.analysis={method:'blurball-pretrained-v1',device:'mps',precision:'fp32',batch_size:4,pipeline:true,detection_frames:450,decoded_frames:900,sampled_frames:900,track_count:1,elapsed_seconds:7.5,processing_fps:150,analysis_fps:120,pipeline_timings:{producer_seconds:5.8,forward_seconds:3.7,postprocess_seconds:.2,wall_seconds:6},table_bounds:[.1,.4,.9,.6],scene_changes:0,audio_impacts:5,warnings:['UI fixture: not real inference']};project.tracks=[{id:'ui-track',points:[{t:2,x:.2,y:.3,confidence:.5},{t:2.04,x:.3,y:.3,confidence:.5},{t:2.08,x:.4,y:.3,confidence:.5}]},{id:'ui-floor',off_play:true,points:[{t:2,x:.05,y:.95,confidence:.5},{t:2.04,x:.06,y:.95,confidence:.5},{t:2.08,x:.07,y:.95,confidence:.5}]}];project.raw_rallies=copy(fixture.raw_rallies);if(!project.manual_timeline||project.rallies.length===0){project.rallies=copy(project.raw_rallies);project.manual_timeline=false;}else{const human=(r)=>r.edited||r.id.startsWith('manual-');const kept=project.rallies.filter(human);const add=project.raw_rallies.map((c)=>kept.some((h)=>h.id===c.id)?{...c,id:c.id+'-r2'}:c);project.rallies=[...kept,...add].sort((a,b)=>a.start-b.start);project.manual_timeline=kept.length>0;}const j={id:'job-test',kind:'analysis',status:'running',progress:.2,message:'UI fixture processing',elapsed_seconds:5,performance:{stage:'inference',processed_frames:300,elapsed_seconds:3,recent_fps:120,average_fps:100}};emit(j);setTimeout(()=>emit({...j,status:'completed',progress:1,message:'UI fixture done',elapsed_seconds:9,performance:{...j.performance,stage:'finalizing',processed_frames:900,elapsed_seconds:6,average_fps:150,recent_fps:0}}),3000);return copy(j);},
  UseAnalysisCandidates:async()=>{window.__calls.push('adopt');const before=snapTimeline();project.rallies=copy(project.raw_rallies);project.manual_timeline=false;recordTimeline(before);return copy(project);},
  CancelJob:async()=>{emit({...project.job,status:'cancelled',message:'fixture cancelled'});},
  ExportHighlights:async()=>{window.__calls.push('export');const j={id:'export-test',kind:'export',status:'completed',progress:1,message:'fixture export',output:'/test/highlights.mp4'};emit(j);return copy(j);},
  RevealExport:async()=>{window.__calls.push('reveal');}
 }}};
})();
"""


def main():
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.getenv('RALLYCUT_BROWSER_CHANNEL', 'chrome') or None, headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(URL)
        page.wait_for_load_state('networkidle')
        expect(page.locator('.project-home')).to_be_visible()
        expect(page.get_by_text('当前是浏览器界面预览。', exact=False)).to_be_visible()
        expect(page.get_by_role('heading', name='从哪一场比赛开始？', exact=True)).to_be_visible()
        page.screenshot(path=str(ARTIFACTS / 'project-home-preview.png'), full_page=True)
        expect(page.get_by_role('button', name='打开项目文件', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='新建项目', exact=True)).to_be_visible()
        for width in (1440,1060):
            page.set_viewport_size({'width':width,'height':900})
            box=page.get_by_role('button', name='打开项目文件', exact=True).bounding_box()
            assert box and box['x']>=0 and box['x']+box['width']<=width and 0<=box['y']<600, box
        page.set_viewport_size({'width':1440,'height':1080})
        page.get_by_role('button', name='新建项目', exact=True).click()
        expect(page.get_by_role('dialog')).to_be_visible()
        default_name=page.get_by_label('项目名称').input_value()
        assert len(default_name)==15 and default_name[8]=='-' and default_name.replace('-','').isdigit(), default_name
        expect(page.get_by_role('button', name='下一步：选择视频', exact=True)).to_be_visible()
        page.get_by_role('button', name='取消', exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        page.get_by_role('button', name='打开项目文件', exact=True).click()
        expect(page.get_by_role('alert')).to_contain_text('wails dev')
        page.get_by_role('button', name='关闭', exact=True).click()

        fixture = ARTIFACTS / 'fixture.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                        'testsrc2=size=320x180:rate=30:duration=30',
                        '-c:v', 'libx264', '-preset', 'ultrafast', str(fixture)], check=True)
        page.add_init_script(BRIDGE)
        media_bytes = fixture.read_bytes()
        media_state={'html':True}
        def media_route(route):
            if media_state['html']:
                route.fulfill(status=200,content_type='text/html',body='<!doctype html><div>Vite fallback is not a video</div>')
                return
            byte_range = route.request.headers.get('range', '')
            if byte_range.startswith('bytes='):
                start_text, end_text = byte_range[6:].split('-', 1)
                start = int(start_text or 0)
                end = min(int(end_text) if end_text else len(media_bytes)-1, len(media_bytes)-1)
                route.fulfill(status=206, content_type='video/mp4', body=media_bytes[start:end+1],
                              headers={'Accept-Ranges':'bytes', 'Content-Range':f'bytes {start}-{end}/{len(media_bytes)}'})
            else:
                route.fulfill(content_type='video/mp4', body=media_bytes, headers={'Accept-Ranges':'bytes'})
        page.route('**/media/source?*', media_route)
        page.reload()
        page.wait_for_load_state('networkidle')
        expect(page.locator('.project-home')).to_be_visible()
        expect(page.locator('.project-card')).to_have_count(1)
        expect(page.get_by_role('button', name='项目列表', exact=True)).to_have_count(0)
        page.screenshot(path=str(ARTIFACTS / 'project-home-recent.png'), full_page=True)
        page.locator('.project-card .project-card-open').first.click()
        page.wait_for_function("window.__calls.filter(c=>c==='recent').length===1")
        try:
            expect(page.locator('.rally-card')).to_have_count(3)
        except AssertionError:
            page.screenshot(path=str(ARTIFACTS/'open-project-failure.png'),full_page=True)
            print('UI fixture diagnostic:',page.evaluate('async()=>({calls:window.__calls,state:await window.go.backend.App.GetState(),body:document.body.innerText})'))
            print('Browser errors:',errors)
            raise
        expect(page.get_by_role('heading',name='当前视频无法预览',exact=True)).to_be_visible()
        expect(page.locator('.empty-video')).to_contain_text('错误码 4')
        expect(page.locator('.empty-video')).not_to_contain_text('系统 WebView 不支持此编码')
        page.screenshot(path=str(ARTIFACTS/'preview-error-retry.png'),full_page=True)
        page.get_by_role('button', name='使用说明', exact=True).click()
        expect(page.get_by_role('dialog')).to_be_visible()
        page.get_by_role('button', name='开始剪辑', exact=True).click()
        expect(page.get_by_role('dialog')).not_to_be_visible()
        media_state['html']=False
        page.get_by_role('button',name='重试预览',exact=True).click()
        page.wait_for_function('document.querySelector("video")?.readyState >= 2')
        source_play=page.get_by_role('button',name='播放原片',exact=True)
        expect(source_play).to_have_text('播放原片')
        expect(source_play).to_have_attribute('title','从当前位置播放原视频；选择回合后可从回合起点重播')
        source_play.click()
        page.wait_for_function('document.querySelector("video").currentTime > .1 && !document.querySelector("video").paused')
        page.locator('video').evaluate('(video)=>video.pause()')
        page.locator('.rally-card').first.click()
        replay=page.get_by_role('button',name='重播回合',exact=True)
        expect(replay).to_be_visible()
        expect(replay).to_have_text('重播回合')
        expect(replay).to_have_attribute('title','从当前回合起点重新播放，到回合终点暂停，不循环')
        # The visible label must describe the existing one-shot behavior:
        # restart at the focused rally, then pause at its end (no loop).
        page.locator('video').evaluate('(v)=>{v.currentTime=3}')
        replay.click()
        page.wait_for_function('document.querySelector("video").currentTime>=1&&document.querySelector("video").currentTime<2&&!document.querySelector("video").paused')
        page.locator('video').evaluate('(v)=>{v.currentTime=3.9}')
        page.wait_for_function('document.querySelector("video").paused',timeout=5000)
        assert page.locator('video').evaluate('(v)=>v.currentTime')>=4
        page.locator('.rally-card').first.click()
        page.keyboard.press('Space')
        page.wait_for_function('!document.querySelector("video").paused')
        page.keyboard.press('Space')
        page.wait_for_function('document.querySelector("video").paused')
        # A focused rally checkbox does not swallow Space (and is not toggled).
        check=page.locator('.rally-card .rally-check').first
        was=check.is_checked()
        check.focus()
        page.keyboard.press('Space')
        page.wait_for_function('!document.querySelector("video").paused')
        page.keyboard.press('Space')
        page.wait_for_function('document.querySelector("video").paused')
        assert check.is_checked()==was
        # No native control overlay (it dims the frame on hover); playback is
        # driven by our own toolbar and by clicking the picture.
        assert page.locator('video').evaluate('(v)=>v.controls')==False
        page.locator('video').click()
        page.wait_for_function('!document.querySelector("video").paused')
        expect(page.get_by_role('button',name='暂停',exact=True)).to_be_visible()
        page.get_by_role('button',name='暂停',exact=True).click()
        page.wait_for_function('document.querySelector("video").paused')
        page.get_by_role('button',name='静音',exact=True).click()
        page.wait_for_function('document.querySelector("video").muted')
        page.get_by_role('button',name='取消静音',exact=True).click()
        page.wait_for_function('!document.querySelector("video").muted')
        # Adjustable skip step + preview speed (UI only, remembered locally).
        page.get_by_label('跳转步长', exact=True).select_option('10')
        expect(page.get_by_role('button', name='前进 10 秒', exact=True)).to_be_visible()
        page.locator('video').evaluate('(v)=>{v.currentTime=2}')
        page.wait_for_function('Math.abs(document.querySelector("video").currentTime-2)<.05')
        page.get_by_role('button', name='前进 10 秒', exact=True).click()
        page.wait_for_function('Math.abs(document.querySelector("video").currentTime-12)<.05')
        page.locator('.rally-card').first.click()
        page.locator('video').evaluate('(v)=>{v.currentTime=12}')
        page.wait_for_function('Math.abs(document.querySelector("video").currentTime-12)<.05')
        page.keyboard.press('ArrowLeft')
        page.wait_for_function('Math.abs(document.querySelector("video").currentTime-2)<.05')
        page.keyboard.press('ArrowLeft')
        page.wait_for_function('document.querySelector("video").currentTime<.05')
        speed=page.get_by_label('播放倍速', exact=True)
        # >2× is not offered: WebView may fall back to keyframe-only playback.
        assert speed.locator('option').all_inner_texts()==['0.5×','1×','1.25×','1.5×','2×']
        speed.select_option('1.5')
        assert page.locator('video').evaluate('(v)=>v.playbackRate')==1.5
        page.locator('.rally-card').first.click()
        page.keyboard.press('Shift+Period')
        page.keyboard.press('Shift+Period')
        page.wait_for_function('document.querySelector("video").playbackRate===2')
        expect(speed).to_have_value('2')
        assert page.evaluate("localStorage.getItem('rallycut.preview.rate')")=='2'
        page.keyboard.press('Shift+Comma')
        page.keyboard.press('Shift+Comma')
        page.keyboard.press('Shift+Comma')
        page.wait_for_function('document.querySelector("video").playbackRate===1')
        # Rally-only playback jumps the 4–6 s gap and stops after the last rally.
        rally_only=page.get_by_role('button', name='只播回合', exact=True)
        off_box=rally_only.bounding_box()
        assert rally_only.evaluate('(b)=>getComputedStyle(b).borderTopColor')=='rgba(0, 0, 0, 0)'
        rally_only.click()
        expect(rally_only).to_have_attribute('aria-pressed','true')
        expect(replay).to_have_attribute('title','从当前回合起点重新播放；已开启“只播回合”，结束后继续播放后续回合，不循环')
        # The on state is a framed, filled chip, not just a color change, and
        # toggling must not shift the toolbar.
        on_style=rally_only.evaluate('(b)=>{const s=getComputedStyle(b);return [s.borderTopColor,s.borderTopWidth,s.borderTopStyle,s.backgroundColor,b.className].join("|")}')
        assert on_style.startswith('rgb(194, 236, 148)|1px|solid'), on_style
        assert rally_only.evaluate('(b)=>getComputedStyle(b).backgroundColor')!='rgba(0, 0, 0, 0)'
        on_box=rally_only.bounding_box()
        assert abs(on_box['width']-off_box['width'])<0.5 and abs(on_box['height']-off_box['height'])<0.5
        page.mouse.move(0,0)
        page.screenshot(path=str(ARTIFACTS/'rally-only-on.png'))
        page.locator('video').evaluate('(v)=>{v.currentTime=3.6;return v.play()}')
        page.wait_for_function('document.querySelector("video").currentTime>=6&&document.querySelector("video").currentTime<7.5',timeout=8000)
        page.locator('video').evaluate('(v)=>{v.currentTime=27.6;return v.play()}')
        page.wait_for_function('document.querySelector("video").paused',timeout=8000)
        assert page.locator('video').evaluate('(v)=>v.currentTime')<29
        assert page.evaluate("localStorage.getItem('rallycut.preview.rallyOnly')")=='1'
        rally_only.click()
        expect(rally_only).to_have_attribute('aria-pressed','false')
        page.get_by_label('跳转步长', exact=True).select_option('5')
        header_project=page.locator('.header-project')
        expect(header_project).to_have_text('UI 测试比赛')
        header_project.dblclick()
        rename_input=page.get_by_label('项目名称', exact=True)
        expect(rename_input).to_have_value('UI 测试比赛')
        rename_input.fill('重命名比赛')
        rename_input.press('Enter')
        page.wait_for_function("window.__calls.filter(c=>c==='rename-project').length===1")
        expect(page.locator('.header-project')).to_have_text('重命名比赛')
        expect(page.get_by_role('button', name='打开项目', exact=True)).to_be_enabled()
        page.keyboard.press('Meta+o')
        page.wait_for_function("window.__calls.filter(c=>c==='open').length===1")
        expect(page.get_by_role('button', name='打开项目', exact=True)).to_be_enabled()
        page.keyboard.press('Control+o')
        page.wait_for_function("window.__calls.filter(c=>c==='open').length===2")
        expect(page.get_by_role('button', name='打开项目', exact=True)).to_be_enabled()
        page.get_by_role('button', name='导入视频', exact=True).click()
        expect(page.locator('.rally-card')).to_have_count(3)
        origin_filter=page.get_by_label('回合来源',exact=True)
        # No hand-added rallies yet: the list opens on machine-detected ones.
        expect(origin_filter).to_have_value('analysis')
        origin_filter.select_option('manual')
        expect(page.locator('.rally-card')).to_have_count(0)
        expect(page.locator('.empty-rallies')).to_contain_text('没有匹配的回合')
        expect(page.locator('.export-summary')).to_contain_text('3 个回合')
        origin_filter.select_option('edited')
        expect(page.locator('.rally-card')).to_have_count(0)
        origin_filter.select_option('analysis')
        expect(page.locator('.rally-card')).to_have_count(3)
        expect(page.get_by_role('button', name='显示球轨迹', exact=True)).to_be_disabled()
        expect(page.get_by_role('button', name='显示球桌', exact=True)).to_be_disabled()
        page.locator('.rally-card').first.click()
        # Double-click the time range to edit start / end inline.
        first_card=page.locator('.rally-card').first
        first_card.locator('.rally-range').dblclick()
        editor=first_card.get_by_role('group',name='修改回合起止时间')
        expect(editor).to_be_visible()
        expect(editor.get_by_label('开始时间', exact=True)).to_have_value('00:01.00')
        expect(editor.get_by_label('结束时间', exact=True)).to_have_value('00:04.00')
        updates_before=page.evaluate("window.__calls.filter(c=>c==='update').length")
        editor.get_by_label('结束时间', exact=True).fill('00:00.50')
        editor.get_by_label('结束时间', exact=True).press('Enter')
        expect(editor.get_by_role('alert')).to_contain_text('晚于')
        expect(editor).to_be_visible()
        editor.get_by_label('结束时间', exact=True).press('Escape')
        expect(editor).to_have_count(0)
        assert page.evaluate("window.__calls.filter(c=>c==='update').length")==updates_before
        first_card.locator('.rally-range').dblclick()
        editor.get_by_label('开始时间', exact=True).fill('1.2')
        editor.get_by_label('开始时间', exact=True).press('Enter')
        expect(editor).to_have_count(0)
        page.wait_for_function("window.__calls.filter(c=>c==='update').length===%d"%(updates_before+1))
        edited=page.evaluate("window.go.backend.App.GetState().then(s=>s.project.rallies.find(r=>r.id==='mock-00001'))")
        assert abs(edited['start']-1.2)<1e-6 and edited['end']==4 and edited['edited'] is True, edited
        # The side panel is the rally list only: no 剪辑 tab / in-out fields.
        expect(page.get_by_role('tab', name='剪辑', exact=True)).to_have_count(0)
        expect(page.locator('.side-header')).to_contain_text('回合')
        expect(page.locator('#start')).to_have_count(0)
        expect(page.get_by_role('button', name='保存边界', exact=True)).to_have_count(0)
        expect(page.get_by_role('button', name='此处拆分', exact=True)).to_have_count(0)
        # Shortcut hints on buttons come from the shared table.
        expect(page.get_by_role('button', name='添加回合', exact=True)).to_have_attribute('title', re.compile('I 标记开始.*O 标记结束'))
        # Shortcuts panel: header button, ⌘/ and the help modal link.
        page.get_by_role('button', name='快捷键', exact=True).click()
        shortcuts=page.get_by_role('dialog', name='快捷键')
        expect(shortcuts).to_be_visible()
        for label in ('标记回合开始','标记结束并添加回合','在播放头拆分当前回合','撤销','设置','修改起止点'):
            expect(shortcuts.get_by_text(label, exact=True)).to_be_visible()
        expect(shortcuts.locator('.shortcut-row', has_text='标记回合开始').locator('kbd')).to_have_text('I')
        updates_before=page.evaluate("window.__calls.filter(c=>c==='update').length")
        page.keyboard.press('d')   # editing shortcuts pause while a dialog is open
        page.keyboard.press('Escape')
        expect(shortcuts).to_have_count(0)
        expect(page.locator('.rally-card')).to_have_count(3)
        assert page.evaluate("window.__calls.filter(c=>c==='update').length")==updates_before
        page.keyboard.press('Meta+/')
        expect(shortcuts).to_be_visible()
        shortcuts.get_by_role('button', name='关闭快捷键').click()
        # Native menu items (RallyCut > 设置… / 帮助 > 快捷键) emit menu:* events.
        page.evaluate("window.__emitMenu('shortcuts')")
        expect(shortcuts).to_be_visible()
        page.evaluate("window.__emitMenu('settings')")
        expect(shortcuts).to_have_count(0)
        expect(page.get_by_role('dialog', name='设置')).to_be_visible()
        page.keyboard.press('Escape')
        page.get_by_role('button', name='使用说明', exact=True).first.click()
        page.get_by_role('button', name=re.compile('查看全部快捷键')).click()
        expect(shortcuts).to_be_visible()
        expect(page.locator('.help-modal')).to_have_count(0)
        page.keyboard.press('Escape')
        # Place the playhead strictly inside the first rally, then split.
        page.wait_for_function('document.querySelector("video").readyState >= 1')
        # Draggable progress bar under the video.
        seek=page.get_by_role('slider', name='视频进度')
        expect(seek).to_be_visible()
        box=seek.bounding_box()
        page.mouse.move(box['x']+box['width']*0.3, box['y']+box['height']/2)
        page.mouse.down()
        page.mouse.move(box['x']+box['width']*0.5, box['y']+box['height']/2, steps=5)
        page.mouse.move(box['x']+box['width']*0.7, box['y']+box['height']/2, steps=5)
        page.mouse.up()
        page.wait_for_function('Math.abs(document.querySelector("video").currentTime-21)<0.6')
        expect(seek).to_have_attribute('aria-valuetext', '00:21 / 00:30')
        seek.press('ArrowLeft')
        page.wait_for_function('Math.abs(document.querySelector("video").currentTime-20)<0.6')
        seek.press('Home')
        page.wait_for_function('document.querySelector("video").currentTime<0.05')
        page.locator('video').evaluate('(v)=>new Promise(resolve=>{v.addEventListener("seeked",resolve,{once:true});v.currentTime=2.5;})')
        expect(page.get_by_role('slider', name='视频进度')).to_have_attribute('aria-valuenow', '2.5')
        page.locator('.rally-card').first.click(button='right')
        page.get_by_role('menuitem', name='在播放头拆分').click(timeout=5000)
        # Re-timed / split machine rallies became corrections: the list left the
        # "machine" filter instead of hiding them.
        expect(origin_filter).to_have_value('all')
        expect(page.locator('.rally-card')).to_have_count(4)
        expect(page.locator('.save-status')).to_contain_text('已自动保存')
        page.keyboard.press('Meta+z')
        expect(page.locator('.rally-card')).to_have_count(3)
        page.keyboard.press('Shift+Meta+z')
        expect(page.locator('.rally-card')).to_have_count(4)
        page.get_by_role('button', name='撤销', exact=True).click()
        expect(page.locator('.rally-card')).to_have_count(3)
        page.get_by_role('button', name='重做', exact=True).click()
        expect(page.locator('.rally-card')).to_have_count(4)
        expect(page.get_by_role('button', name='重做', exact=True)).to_be_disabled()
        page.get_by_role('button', name='合并', exact=True).click()
        expect(page.locator('.rally-card')).to_have_count(1)
        origin_filter.select_option('edited')
        expect(page.locator('.rally-card')).to_have_count(1)
        origin_filter.select_option('analysis')
        expect(page.locator('.rally-card')).to_have_count(0)
        origin_filter.select_option('all')
        page.locator('.rally-card').first.click()
        # Clip buffer and export encoding live in the ⌘, settings page.
        page.keyboard.press('Meta+,')
        settings=page.get_by_role('dialog', name='设置')
        expect(settings).to_be_visible()
        expect(settings.get_by_role('tab', name='片段缓冲')).to_have_attribute('aria-selected', 'true')
        expect(settings).to_contain_text('保存在当前项目中')
        page.locator('#pre').fill('')
        expect(page.get_by_role('button', name='应用剪辑规则', exact=True)).to_be_disabled()
        page.locator('#pre').fill('1.5')
        page.get_by_role('button', name='应用剪辑规则', exact=True).click()
        page.wait_for_function("window.go.backend.App.GetState().then(s=>s.project.rules.pre_roll===1.5)")
        settings.get_by_role('tab', name='导出编码').click()
        page.locator('#codec').select_option('hevc')
        page.locator('#bitrate').fill('8.23365')
        page.get_by_role('button', name='应用导出设置', exact=True).click()
        expect(page.locator('.export-summary')).to_contain_text('HEVC')
        settings.get_by_role('tab', name='播放').click()
        settings.locator('#settings-step').select_option('10')
        expect(page.get_by_label('跳转步长')).to_have_value('10')
        settings.locator('#settings-step').select_option('5')
        page.keyboard.press('Escape')
        expect(settings).to_have_count(0)
        page.get_by_role('button', name='分析视频', exact=True).click()
        live=page.get_by_label('实时处理速度')
        expect(live).to_contain_text('120.0 FPS')
        expect(live).to_contain_text('100.0 FPS')
        expect(live).to_contain_text('60.0 FPS')
        # Play / pause stays available while the analysis runs.
        page.keyboard.press('Space')
        page.wait_for_function('!document.querySelector("video").paused')
        page.keyboard.press('k')
        page.wait_for_function('document.querySelector("video").paused')
        expect(live).to_be_visible()                     # still running
        expect(page.locator('.source-chip').first).to_have_attribute(
            'title','训练赛 · UI fixture.mp4 · 320×180 · 30.00fps · 00:30')
        expect(page.get_by_text('已完成', exact=True)).to_be_visible()
        expect(live).not_to_contain_text('120.0 FPS')
        # The merged rally is human-corrected: re-analysis keeps it, and the
        # machine candidates over the same footage stay as their own source
        # (export decides which one is used).
        expect(page.locator('.rally-card')).to_have_count(4)
        origin_filter.select_option('edited')
        expect(page.locator('.rally-card')).to_have_count(1)
        origin_filter.select_option('analysis')
        expect(page.locator('.rally-card')).to_have_count(3)
        expect(page.locator('.overlap-chip')).to_contain_text('人工 / 分析重叠')
        origin_filter.select_option('all')
        details=page.locator('.job-panel .analysis-summary')
        expect(details).to_be_visible()
        assert details.evaluate('(node)=>!node.open'), 'analysis details must start collapsed'
        expect(page.locator('.rallies-panel .analysis-summary')).to_have_count(0)
        details.locator(':scope > summary').click()
        expect(page.get_by_label('分析性能统计')).to_contain_text('150.0 FPS')
        expect(details).to_contain_text('FP32')
        expect(details).to_contain_text('UI fixture: not real inference')
        expect(page.get_by_label('视频分析叠加层')).to_have_count(0)
        page.get_by_role('button', name='显示球桌', exact=True).click()
        expect(page.get_by_test_id('table-overlay')).to_be_visible()
        expect(page.get_by_test_id('ball-tracks-overlay')).to_have_count(0)
        page.get_by_role('button', name='显示球轨迹', exact=True).click()
        page.locator('video').evaluate('(v)=>new Promise(resolve=>{v.addEventListener("seeked",resolve,{once:true});v.currentTime=2.08;})')
        # The off-play floor ball at the same moment is not drawn.
        expect(page.get_by_test_id('ball-tracks-overlay').locator('circle')).to_have_count(1)
        expect(page.get_by_label('视频分析叠加层')).to_contain_text('PRETRAINED TRACKS')
        expect(page.get_by_test_id('table-overlay')).to_be_visible()
        page.get_by_role('button', name='隐藏球桌', exact=True).click()
        expect(page.get_by_test_id('table-overlay')).to_have_count(0)
        expect(page.get_by_test_id('ball-tracks-overlay')).to_be_visible()
        expect(page.get_by_role('button', name='隐藏球轨迹', exact=True)).to_have_attribute('aria-pressed','true')
        page.get_by_role('button', name='隐藏球轨迹', exact=True).click()
        expect(page.get_by_label('视频分析叠加层')).to_have_count(0)
        page.get_by_role('button', name='显示球轨迹', exact=True).click()
        page.get_by_role('button', name='显示球桌', exact=True).click()
        page.get_by_role('button', name='隐藏球轨迹', exact=True).click()
        expect(page.get_by_test_id('table-overlay')).to_be_visible()
        expect(page.get_by_test_id('ball-tracks-overlay')).to_have_count(0)
        expect(page.get_by_role('button', name='隐藏球桌', exact=True)).to_have_attribute('aria-pressed','true')
        page.get_by_role('button', name='显示球轨迹', exact=True).click()
        # Burn-in overlays default off and are saved into the export settings.
        overlays=page.get_by_role('group', name='导出画面叠加')
        burn_track=overlays.get_by_label('球轨迹')
        burn_label=overlays.get_by_label('回合编号')
        expect(burn_track).not_to_be_checked()
        expect(burn_label).not_to_be_checked()
        burn_track.check()
        expect(burn_track).to_be_checked()
        burn_label.check()
        expect(burn_label).to_be_checked()
        saved=page.evaluate('window.go.backend.App.GetState().then(s=>s.project.export_settings)')
        assert saved.get('show_trajectory') is True and saved.get('show_rally_labels') is True, saved
        assert saved.get('overlap')=='merge' or saved.get('overlap') is None or isinstance(saved.get('overlap'),str), saved
        burn_label.uncheck()
        expect(burn_label).not_to_be_checked()
        saved=page.evaluate('window.go.backend.App.GetState().then(s=>s.project.export_settings)')
        assert saved.get('show_trajectory') is True and saved.get('show_rally_labels') is False, saved
        page.get_by_role('button', name='导出精彩集锦', exact=False).click()
        # Human and machine rallies over the same footage: export asks which.
        page.get_by_role('dialog').get_by_role('button',name='按此方式导出').click()
        expect(page.get_by_text('已保存：/test/highlights.mp4', exact=True)).to_be_visible()
        page.get_by_role('button', name='打开文件夹', exact=True).click()
        page.wait_for_function("window.__calls.includes('reveal')")
        page.screenshot(path=str(ARTIFACTS / 'populated-workbench.png'), full_page=True)
        page.set_viewport_size({'width':1060,'height':800})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'horizontal page overflow'
        page.locator('.player-toolbar').scroll_into_view_if_needed()
        toolbar=page.locator('.player-toolbar').bounding_box()
        expect(page.locator('.play-button span')).to_be_visible()
        controls=page.locator('.player-toolbar > div').bounding_box()
        tip=page.locator('.player-tip').bounding_box()
        assert controls and tip and (controls['x']+controls['width']<=tip['x'] or controls['y']+controls['height']<=tip['y']), (controls,tip)
        assert page.locator('.player-toolbar .timecode').evaluate('(e)=>getComputedStyle(e).whiteSpace')=='nowrap'
        for name in ('重播回合','隐藏球轨迹','隐藏球桌'):
            box=page.get_by_role('button',name=name,exact=True).bounding_box()
            assert box and toolbar and 0<=box['x'] and box['x']+box['width']<=1060 and box['y']+box['height']<=toolbar['y']+toolbar['height'], (name,box,toolbar)
        page.screenshot(path=str(ARTIFACTS / 'compact-workbench.png'), full_page=True)
        page.locator('.rally-card').filter(has=page.locator('.origin-tag.edited')).click()
        expect(page.locator('.rally-card.current .origin-tag.edited')).to_have_count(1)
        page.locator('.rally-card.current').click(button='right')
        page.get_by_role('menuitem', name='删除回合').click()
        expect(page.locator('.rally-card')).to_have_count(3)
        expect(page.get_by_role('button', name='导出精彩集锦', exact=False)).to_be_enabled()
        expect(page.locator('.rallies-blank')).to_have_count(0)
        # The machine rallies stayed beside the deleted correction, so the
        # timeline is still non-empty (no empty-timeline auto-adopt here).
        origin_filter.select_option('edited')
        expect(page.locator('.rally-card')).to_have_count(0)
        origin_filter.select_option('analysis')
        expect(page.locator('.rally-card')).to_have_count(3)
        origin_filter.select_option('all')
        page.evaluate('window.__noGeometry=true')
        page.get_by_role('button',name='另存为',exact=True).click()
        expect(page.get_by_role('button',name='显示球桌',exact=True)).to_be_disabled()
        expect(page.get_by_role('button',name='隐藏球轨迹',exact=True)).to_be_enabled()
        expect(page.get_by_role('button',name='隐藏球轨迹',exact=True)).to_have_attribute('aria-pressed','true')
        expect(page.get_by_test_id('ball-tracks-overlay')).to_have_count(1)
        expect(page.get_by_test_id('table-overlay')).to_have_count(0)
        page.get_by_role('button', name='项目列表', exact=True).click()
        expect(page.locator('.project-home')).to_be_visible()
        expect(page.locator('.project-card.current')).to_have_count(1)
        page.locator('.project-card.current .project-card-open').click()
        expect(page.locator('.rally-card')).to_have_count(3)
        calls = page.evaluate('window.__calls')
        assert all(name in calls for name in ['open', 'import', 'update', 'split', 'merge', 'undo', 'redo', 'analysis', 'encoding', 'export']), calls
        page.reload()
        page.wait_for_function('Boolean(window.go?.backend?.App)')
        page.wait_for_load_state('networkidle')
        expect(page.locator('.project-home')).to_be_visible()
        page.evaluate('()=>{window.__legacyEmpty=true;window.__confirmCalls=0;window.__confirmStacks=[];window.confirm=()=>{window.__confirmCalls++;window.__confirmStacks.push(new Error().stack);return false;};}')
        page.keyboard.press('Control+o')
        expect(page.locator('.rally-card')).to_have_count(3)
        expect(page.locator('.rallies-blank')).to_have_count(0)
        expect(page.locator('.pending-overlay')).to_have_count(0)
        assert page.evaluate('window.__confirmCalls')==0, page.evaluate('window.__confirmStacks')
        assert page.evaluate('window.__calls.filter(c=>c==="adopt").length')==1, 'legacy empty project must be adopted exactly once'
        page.get_by_role('button', name='项目列表', exact=True).click()
        expect(page.locator('.project-home')).to_be_visible()
        page.get_by_role('button', name='删除项目 UI 测试比赛', exact=True).click()
        expect(page.get_by_role('dialog')).to_contain_text('不会删除项目引用的视频或任何素材文件')
        page.get_by_role('button', name='删除项目', exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        page.wait_for_function("window.__calls.filter(c=>c==='delete-project').length===1")
        expect(page.locator('.project-card')).to_have_count(0)
        expect(page.locator('.project-library-empty')).to_be_visible()
        page.get_by_role('button', name='新建项目', exact=True).click()
        expect(page.get_by_role('dialog')).to_be_visible()
        page.get_by_label('项目名称', exact=True).fill('新项目 A')
        page.get_by_role('button', name='下一步：选择视频', exact=True).click()
        page.wait_for_function("window.__calls.filter(c=>c==='create-project').length===1")
        expect(page.locator('.header-project')).to_have_text('新项目 A')
        expect(origin_filter).to_have_value('analysis')
        expect(page.locator('.rally-card')).to_have_count(3)
        page.locator('.rally-card').first.click()
        page.keyboard.press('i')
        page.locator('.rally-card').nth(1).click()
        page.keyboard.press('o')
        # Hand-added rallies now exist: the list switches to them.
        expect(origin_filter).to_have_value('manual')
        expect(page.locator('.rally-card')).to_have_count(1)
        origin_filter.select_option('all')
        expect(page.locator('.rally-card')).to_have_count(4)
        # The I/O rally overlaps a machine rally: export must ask how to resolve.
        expect(page.locator('.overlap-chip')).to_contain_text('人工 / 分析重叠')
        exports_before=page.evaluate("window.__calls.filter(c=>c==='export').length")
        page.get_by_role('button',name='导出精彩集锦').click()
        modal=page.get_by_role('dialog',name='回合有重叠，怎么导出？')
        expect(modal).to_be_visible()
        expect(modal.locator('input[type=radio]')).to_have_count(4)
        expect(modal.locator('input[value=merge]')).to_be_checked()
        page.get_by_role('button',name='取消',exact=True).click()
        expect(modal).to_have_count(0)
        assert page.evaluate("window.__calls.filter(c=>c==='export').length")==exports_before
        page.get_by_role('button',name='导出精彩集锦').click()
        modal.get_by_text('人工回合覆盖分析回合').click()
        expect(modal.locator('input[value=human]')).to_be_checked()
        modal.get_by_role('button',name='按此方式导出').click()
        page.wait_for_function("window.__calls.filter(c=>c==='export').length===%d"%(exports_before+1))
        assert page.evaluate("window.go.backend.App.GetState().then(s=>s.project.export_settings.overlap)")=='human'
        expect(page.locator('.overlap-chip')).to_contain_text('人工回合覆盖分析回合')
        # Progress bar works on a project with no rallies at all.
        page.reload()
        page.wait_for_function('Boolean(window.go?.backend?.App)')
        page.evaluate('()=>{window.__noRallies=true;}')
        # ⌘, also works from the project home; project settings need a project.
        expect(page.locator('.project-home')).to_be_visible()
        page.keyboard.press('Meta+,')
        settings=page.get_by_role('dialog', name='设置')
        expect(settings).to_contain_text('打开项目后才能设置')
        expect(page.locator('#pre')).to_be_disabled()
        page.keyboard.press('Escape')
        expect(settings).to_have_count(0)
        page.keyboard.press('Control+o')
        page.wait_for_function("window.__calls.includes('open')")
        expect(page.locator('.rally-card')).to_have_count(0)
        page.wait_for_function('document.querySelector("video")?.readyState >= 1')
        seek=page.get_by_role('slider', name='视频进度')
        expect(seek).to_be_visible()
        box=seek.bounding_box()
        page.mouse.move(box['x']+box['width']*0.2, box['y']+box['height']/2)
        page.mouse.down()
        page.mouse.move(box['x']+box['width']*0.7, box['y']+box['height']/2, steps=6)
        page.mouse.up()
        page.wait_for_function('Math.abs(document.querySelector("video").currentTime-21)<0.6')
        seek.press('End')
        page.wait_for_function('document.querySelector("video").currentTime>29.5')
        assert not errors, errors
        browser.close()
        print(json.dumps({'status':'PASS', 'browser':'Chrome', 'bridge':'explicit UI fixture',
                          'checks':'project-home-recent-list/two-step-new-project/rename-project/open-recent/return-to-projects/continue-current/delete-project-metadata-only/visible-open-project/Meta+O/Control+O/media-html-failure/retry-real-playback/space-play-pause/undo-redo/autosave-status/manual-io-visible/export-overlap-policy/preview/error/help/import/origin-filter-default/edit/split/merge/rules/analyze/reanalysis-keeps-human-and-machine/collapsed-analysis-details/independent-ball-table-overlays/export/delete/empty-timeline-auto-adopt/legacy-empty-auto-adopt/compact',
                          'screenshots':str(ARTIFACTS)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
