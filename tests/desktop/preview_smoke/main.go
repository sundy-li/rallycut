// Native WKWebView media regression. Run with production desktop build tags.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
	"net/http"
	"os"
	"rallycut/backend"
	"sync/atomic"
	"testing/fstest"
	"time"
)

const page = `<!doctype html><html><body><video id="v" controls muted playsinline style="width:100%"></video><pre id="status">Native media smoke test</pre><script>
(async()=>{
 let finished=false;
 const done=async(result)=>{if(finished)return;finished=true;document.querySelector('#status').textContent=JSON.stringify(result);await fetch('/preview-report',{method:'POST',body:JSON.stringify(result)});};
 const timeout=setTimeout(()=>done({ok:false,error:'native video timeout'}),30000);
 try{
  const state=await (await fetch('/preview-state')).json();
  if(!state.project)throw Error('no saved project');
  const v=document.querySelector('#v');
  const url='/media/source?project='+encodeURIComponent(state.project.id);
  v.onerror=()=>done({ok:false,error:{code:v.error?.code,message:v.error?.message},source:state.project.video.path});
  const response=await fetch(url,{headers:{Range:'bytes=0-15'}});
  const contentType=response.headers.get('content-type');
  const chunk=await response.arrayBuffer();
  if(response.status!==206||!contentType?.startsWith('video/'))throw Error('bad media HTTP '+response.status+' '+contentType+' '+chunk.byteLength);
  const metadata=new Promise(resolve=>v.addEventListener('loadedmetadata',resolve,{once:true}));
  v.src=url;v.load();await metadata;await v.play();
  await new Promise(resolve=>{const changed=()=>{if(v.currentTime>.25){v.removeEventListener('timeupdate',changed);resolve();}};v.addEventListener('timeupdate',changed);changed();});
  v.pause();const seeked=new Promise(resolve=>v.addEventListener('seeked',resolve,{once:true}));v.currentTime=Math.min(30,v.duration/2);await seeked;
  clearTimeout(timeout);await done({ok:true,source:state.project.video.path,width:v.videoWidth,height:v.videoHeight,duration:v.duration,seek:v.currentTime,readyState:v.readyState,http:response.status,contentType});
 }catch(error){clearTimeout(timeout);await done({ok:false,error:String(error)});}
})();</script></body></html>`

func main() {
	app := backend.NewApp()
	ready := make(chan struct{})
	report := make(chan json.RawMessage, 1)
	var passed atomic.Bool
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-ready
		switch r.URL.Path {
		case "/preview-state":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(app.GetState())
		case "/preview-report":
			var data json.RawMessage
			if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 65536)).Decode(&data); err != nil {
				http.Error(w, err.Error(), 400)
				return
			}
			w.WriteHeader(200)
			select {
			case report <- data:
			default:
			}
		default:
			http.NotFound(w, r)
		}
	})
	err := wails.Run(&options.App{Title: "RallyCut native preview check", Width: 640, Height: 420,
		AssetServer: &assetserver.Options{Assets: fstest.MapFS{"index.html": &fstest.MapFile{Data: []byte(page)}}, Handler: handler, Middleware: backend.MediaMiddleware(app)},
		OnStartup: func(ctx context.Context) {
			app.Startup(ctx)
			close(ready)
			go func() {
				select {
				case data := <-report:
					fmt.Println(string(data))
					var result struct {
						OK bool `json:"ok"`
					}
					_ = json.Unmarshal(data, &result)
					passed.Store(result.OK)
				case <-time.After(40 * time.Second):
					fmt.Println(`{"ok":false,"error":"harness timeout"}`)
				}
				time.AfterFunc(200*time.Millisecond, func() { wruntime.Quit(ctx) })
			}()
		}, OnShutdown: app.Shutdown,
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if !passed.Load() {
		os.Exit(1)
	}
}
