package backend

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"rallycut/backend/analysis"
	"rallycut/backend/childproc"
	exporter "rallycut/backend/export"
	"rallycut/backend/media"
	"rallycut/backend/project"
	"rallycut/backend/storage"
)

// Runs on Windows using the installed release's actual tools. It does not rely
// on runner Python or fake media, and exercises the same post-dialog new-project
// path as CreateProject. The input video is a short synthetic test pattern.
func TestWindowsUnicodeProjectImportPreviewExport(t *testing.T) {
	installed := os.Getenv("RALLYCUT_INSTALLED_ROOT")
	if runtime.GOOS != "windows" || installed == "" {
		t.Skip("requires real installed Windows runtime")
	}
	t.Setenv("RALLYCUT_FFMPEG", filepath.Join(installed, "bin", "ffmpeg.exe"))
	t.Setenv("RALLYCUT_FFPROBE", filepath.Join(installed, "bin", "ffprobe.exe"))
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	base := filepath.Join(t.TempDir(), "中文 用户", "生活 #100% & 比赛")
	if err := os.MkdirAll(base, 0700); err != nil {
		t.Fatal(err)
	}
	source := filepath.Join(base, "合作成 对拉 🏓.mp4")
	cmd := childproc.CommandContext(ctx, media.Binary("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=24:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", source)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("generate fixture: %s %v", out, err)
	}
	decode := childproc.CommandContext(ctx, filepath.Join(installed, "python", "python.exe"), "-I", "-c", `import cv2,sys
cap=cv2.VideoCapture(sys.argv[1],cv2.CAP_FFMPEG)
ok,frame=cap.read()
cap.release()
assert ok and frame.shape[:2]==(90,160),'Unicode source decode failed'
print('real OpenCV Unicode decode OK')`, source)
	decode.Env = analysis.PythonEnv()
	if out, err := decode.CombinedOutput(); err != nil {
		t.Fatalf("Python/OpenCV cannot decode Unicode source: %s %v", out, err)
	}
	before, err := os.ReadFile(source)
	if err != nil {
		t.Fatal(err)
	}
	app, _ := newTestApp(t, nil)
	app.dataDir = filepath.Join(base, "项目 数据")
	if err := os.MkdirAll(app.dataDir, 0700); err != nil {
		t.Fatal(err)
	}
	p, err := app.createProjectFromPaths("中文项目 🏓", []string{source})
	if err != nil {
		t.Fatal(err)
	}
	if p.Video.Path != source || p.Video.Name != filepath.Base(source) || p.Video.Fingerprint == "" || p.Video.Width != 160 {
		t.Fatalf("import altered video path or skipped probe: %+v", p.Video)
	}
	var saved project.Project
	if err := storage.ReadJSON(app.projectPath, &saved); err != nil {
		t.Fatal(err)
	}
	if saved.Video.Path != source || saved.Name != "中文项目 🏓" {
		t.Fatal("project JSON damaged Unicode paths")
	}
	handler := MediaHandler(app)
	req := httptest.NewRequest(http.MethodGet, "/media/source?project="+url.QueryEscape(p.ID), nil)
	req.Header.Set("Range", "bytes=0-31")
	res := httptest.NewRecorder()
	handler.ServeHTTP(res, req)
	if res.Code != 206 || !bytes.Equal(res.Body.Bytes(), before[:32]) {
		t.Fatalf("preview cannot read Unicode source: %d %q", res.Code, res.Body.String())
	}
	p.Rallies = []project.Rally{{ID: "manual-unicode", Start: .1, End: 1.5, Selected: true, Edited: true}}
	p.ExportSettings.Encoder = "software"
	output := filepath.Join(base, "导出 集锦 #1.mp4")
	if err := exporter.Run(ctx, p, output, func(float64, string) {}); err != nil {
		t.Fatal(err)
	}
	if v, err := media.Inspect(ctx, output); err != nil || v.Width != 160 || v.Duration <= 0 {
		t.Fatalf("Unicode export unreadable: %+v %v", v, err)
	}
	after, err := os.ReadFile(source)
	if err != nil || !bytes.Equal(after, before) {
		t.Fatal("source was altered")
	}
	// A new App can reopen the project without losing the original path.
	reopened, _ := newTestApp(t, nil)
	if _, err := reopened.openProjectPath(app.projectPath); err != nil {
		t.Fatal(err)
	}
	if reopened.current.Video.Path != source {
		t.Fatal("reopening changed path")
	}
	t.Log("PASS: Windows Chinese/spaces/symbols/emoji path → real ffprobe/fingerprint → new project → JSON reopen → Range preview → real FFmpeg export; original unchanged")
}
