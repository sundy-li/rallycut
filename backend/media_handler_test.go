package backend

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"

	wassets "github.com/wailsapp/wails/v2/pkg/assetserver"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
	"rallycut/backend/project"
)

// Use Wails' actual external/Vite proxy, not only our isolated handler. A SPA
// returns 200 HTML for unknown URLs and otherwise prevents Handler from running.
func TestMediaMiddlewareBypassesViteSPAFallback(t *testing.T) {
	var proxyRequests atomic.Int32
	vite := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		proxyRequests.Add(1)
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte("<!doctype html><div>Vite SPA fallback</div>"))
	}))
	defer vite.Close()
	proxyURL, _ := url.Parse(vite.URL)
	app := NewApp()
	app.ctx = context.Background()
	path := filepath.Join(t.TempDir(), "source.MP4")
	if err := os.WriteFile(path, []byte("0123456789"), 0600); err != nil {
		t.Fatal(err)
	}
	app.current = project.New(project.Video{Path: path, Name: "source.MP4", Duration: 1, Width: 320, Height: 180})
	handler := wassets.NewExternalAssetsHandler(nil, assetserver.Options{Handler: MediaHandler(app), Middleware: MediaMiddleware(app)}, proxyURL)
	for _, item := range []struct {
		method, path, rangeHeader string
		status                    int
		body                      string
	}{
		{"GET", "/media/source?project=" + app.current.ID, "bytes=2-5", 206, "2345"},
		{"HEAD", "/media/source?project=" + app.current.ID, "", 200, ""},
		{"GET", "/media/source?project=wrong", "", 404, "404 page not found\n"},
		{"GET", "/media/source?project=" + app.current.ID, "bytes=99-100", 416, "invalid range: failed to overlap\n"},
		{"GET", "/media/unknown", "", 404, "404 page not found\n"},
	} {
		req := httptest.NewRequest(item.method, item.path, nil)
		if item.rangeHeader != "" {
			req.Header.Set("Range", item.rangeHeader)
		}
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, req)
		if response.Code != item.status || response.Body.String() != item.body {
			t.Errorf("%s %s: %d %q", item.method, item.path, response.Code, response.Body.String())
		}
		if item.status == 206 {
			if got := response.Header().Get("Content-Range"); got != "bytes 2-5/10" {
				t.Error(got)
			}
			if !strings.HasPrefix(response.Header().Get("Content-Type"), "video/") {
				t.Error(response.Header())
			}
		}
	}
	if proxyRequests.Load() != 0 {
		t.Fatal("media was sent to Vite", proxyRequests.Load())
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest("GET", "/", nil))
	if response.Code != 200 || !strings.Contains(response.Body.String(), "Vite SPA fallback") || proxyRequests.Load() != 1 {
		t.Fatal("frontend no longer proxied", response.Code, response.Body.String())
	}
}
