package integration

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"rallycut/backend/analysis"
	exporter "rallycut/backend/export"
	"rallycut/backend/media"
	"rallycut/backend/project"
	"rallycut/backend/storage"
	"rallycut/vision"
	"testing"
)

// Synthetic media only; no copyrighted footage or downloaded models required.
func TestImportAnalyzeEditSaveExport(t *testing.T) {
	for _, name := range []string{"ffmpeg", "ffprobe", "python3"} {
		if _, err := exec.LookPath(media.Binary(name)); err != nil {
			t.Skip(name + " unavailable")
		}
	}
	python := analysis.Python("")
	if !analysis.CheckPython(python) {
		t.Skip("run just setup to install visual dependencies")
	}
	dir := t.TempDir()
	source := filepath.Join(dir, "source with spaces.mp4")
	picture := filepath.Join(dir, "visual-fixture.mp4")
	code := "import sys;sys.path.insert(0,sys.argv[1]);from test_worker import fixture;fixture(sys.argv[2])"
	if out, err := exec.Command(python, "-c", code, filepath.Join("..", "..", "vision", "tests"), picture).CombinedOutput(); err != nil {
		t.Fatalf("fixture: %s %v", out, err)
	}
	ctx := context.Background()
	cmd := exec.CommandContext(ctx, media.Binary("ffmpeg"), "-v", "error", "-i", picture, "-f", "lavfi", "-i", "sine=frequency=880:duration=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", source)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("fixture: %s %v", out, err)
	}
	v, err := media.Inspect(ctx, source)
	if err != nil {
		t.Fatal(err)
	}
	if !v.HasAudio || v.FPS != 30 || v.Width != 960 {
		t.Fatalf("bad metadata %+v", v)
	}
	worker, err := vision.Install(dir)
	if err != nil {
		t.Fatal(err)
	}
	result, err := analysis.RunWithModel(ctx, python, worker, v, analysis.ClassicalModel, func(float64, string) {})
	if err != nil {
		t.Fatal(err)
	}
	p := project.New(v)
	p.RawRallies = result.Rallies
	p.Model = result.Model
	p.Rallies = []project.Rally{{ID: "a", Start: .5, End: 1.5, Selected: true, Edited: true}, {ID: "b", Start: 3, End: 4, Selected: true, Edited: true}}
	p.ManualTimeline = true
	p.Rules = project.Rules{PreRoll: .1, PostRoll: .2}
	path := filepath.Join(dir, "p-rallycut.json")
	if err := storage.WriteJSON(path, p); err != nil {
		t.Fatal(err)
	}
	p, err = storage.Load(path)
	if err != nil {
		t.Fatal(err)
	}
	output := filepath.Join(dir, "highlights.mp4")
	if err := exporter.Run(ctx, p, output, func(float64, string) {}); err != nil {
		t.Fatal(err)
	}
	out, err := media.Probe(ctx, output)
	if err != nil {
		t.Fatal(err)
	}
	if !out.HasAudio || out.Duration < 2.4 || out.Duration > 2.9 || out.Codec != "h264" {
		t.Fatalf("invalid export: %+v", out)
	}
	if err := exporter.Run(ctx, p, output, func(float64, string) {}); err == nil {
		t.Fatal("existing output overwritten")
	}
	cancelled, cancel := context.WithCancel(ctx)
	cancel()
	bad := filepath.Join(dir, "cancelled.mp4")
	if err := exporter.Run(cancelled, p, bad, func(float64, string) {}); err == nil {
		t.Fatal("cancellation ignored")
	}
	if _, err := os.Stat(bad); !os.IsNotExist(err) {
		t.Fatal("cancelled task left a published output")
	}
}

func TestSilentVideoExport(t *testing.T) {
	if _, err := exec.LookPath(media.Binary("ffmpeg")); err != nil {
		t.Skip("ffmpeg unavailable")
	}
	dir := filepath.Join(t.TempDir(), "中文 空格 #100% & 视频")
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	source := filepath.Join(dir, "静音 对拉 🏓.mp4")
	cmd := exec.Command(media.Binary("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=160x90:r=24:d=2", "-c:v", "libx264", source)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("fixture: %s %v", out, err)
	}
	v, err := media.Inspect(context.Background(), source)
	if err != nil {
		t.Fatal(err)
	}
	p := project.New(v)
	p.Rallies = []project.Rally{{ID: "a", Start: .2, End: 1.5, Selected: true}}
	if err := exporter.Run(context.Background(), p, filepath.Join(dir, "out.mp4"), func(float64, string) {}); err != nil {
		t.Fatal(err)
	}
}
