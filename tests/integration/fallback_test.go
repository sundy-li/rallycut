package integration

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	exporter "rallycut/backend/export"
	"rallycut/backend/media"
	"rallycut/backend/project"
	"runtime"
	"strings"
	"testing"
)

func TestHardwareFailureRestartsEntireBatch(t *testing.T) {
	if runtime.GOOS != "darwin" {
		t.Skip("VideoToolbox preference is macOS-only")
	}
	ffmpeg, err := exec.LookPath(media.Binary("ffmpeg"))
	if err != nil {
		t.Skip("ffmpeg unavailable")
	}
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 unavailable")
	}
	dir := t.TempDir()
	source := filepath.Join(dir, "source.mp4")
	if logs, err := exec.Command(ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30:duration=4", "-c:v", "libx264", source).CombinedOutput(); err != nil {
		t.Fatalf("fixture: %v %s", err, logs)
	}
	v, err := media.Inspect(context.Background(), source)
	if err != nil {
		t.Fatal(err)
	}
	logPath := filepath.Join(dir, "calls.txt")
	wrapper := filepath.Join(dir, "ffmpeg-wrapper")
	// Simulate a successful first hardware clip and a failed second clip, without
	// requiring actual VideoToolbox hardware in CI. All media is real libx264.
	script := fmt.Sprintf(`#!%s
import os, sys
real = %q
log = %q
args = sys.argv[1:]
if '-c:v' in args:
    index = args.index('-c:v') + 1
    encoder = args[index]
    with open(log, 'a') as out:
        out.write(encoder + '\n')
    if encoder == 'h264_videotoolbox':
        with open(log) as inp:
            count = inp.read().count('h264_videotoolbox')
        if count == 2:
            sys.stderr.write('simulated hardware session failure on clip 2')
            sys.exit(1)
        args[index] = 'libx264'
        i = args.index('-allow_sw')
        del args[i:i+2]
os.execv(real, [real] + args)
`, python, ffmpeg, logPath)
	if err := os.WriteFile(wrapper, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("RALLYCUT_FFMPEG", wrapper)
	p := project.New(v)
	p.Rules = project.Rules{}
	p.Rallies = []project.Rally{{ID: "a", Start: 0, End: 1, Selected: true}, {ID: "b", Start: 2, End: 3, Selected: true}}
	fallback := false
	if err := exporter.Run(context.Background(), p, filepath.Join(dir, "out.mp4"), func(_ float64, msg string) {
		if strings.Contains(msg, "全部片段重新使用软件编码") {
			fallback = true
		}
	}); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatal(err)
	}
	want := "h264_videotoolbox\nh264_videotoolbox\nlibx264\nlibx264\n"
	if string(data) != want || !fallback {
		t.Fatalf("batch did not fully restart: %q, fallback=%v", data, fallback)
	}
}
