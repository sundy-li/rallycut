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
	"rallycut/backend/storage"
	"strings"
	"testing"
	"time"
)

// Explicit opt-in: never depends on private media in CI. This is a media
// pipeline check, NOT a ball-detection or rally-accuracy evaluation.
func TestRealVideoHardwareExport(t *testing.T) {
	source := os.Getenv("RALLYCUT_TEST_VIDEO")
	if source == "" {
		t.Skip("set RALLYCUT_TEST_VIDEO to opt in")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	v, err := media.Inspect(ctx, source)
	if err != nil {
		t.Fatal(err)
	}
	if v.Duration < 64 {
		t.Fatal("real-video smoke test expects at least 64 seconds")
	}
	dir := os.Getenv("RALLYCUT_TEST_OUTPUT")
	if dir == "" {
		dir = t.TempDir()
	}
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	type report struct {
		Settings      project.ExportSettings `json:"settings"`
		ActualEncoder string                 `json:"actual_encoder"`
		Elapsed       float64                `json:"elapsed_seconds"`
		Output        project.Video          `json:"output"`
	}
	reports := []report{}
	for _, tc := range []struct{ codec, encoder string }{{"h264", "auto"}, {"hevc", "auto"}, {"hevc", "software"}} {
		t.Run(tc.codec+"-"+tc.encoder, func(t *testing.T) {
			p := project.New(v)
			p.Rules = project.Rules{}
			p.ManualTimeline = true
			p.Rallies = []project.Rally{{ID: "manual-test-a", Start: 30, End: 33, Selected: true}, {ID: "manual-test-b", Start: 60, End: 63, Selected: true}}
			p.ExportSettings = project.ExportSettings{Codec: tc.codec, Encoder: tc.encoder, BitRate: v.BitRate}
			output := filepath.Join(dir, fmt.Sprintf("real-%s-%s-%s.mp4", tc.codec, tc.encoder, p.ID))
			start := time.Now()
			encoder := ""
			err := exporter.Run(ctx, p, output, func(progress float64, msg string) {
				t.Logf("%.0f%% %s", progress*100, msg)
				if strings.Contains(msg, " · 编码片段") {
					encoder = strings.Split(msg, " · ")[0]
				}
			})
			elapsed := time.Since(start).Seconds()
			if err != nil {
				t.Fatal(err)
			}
			out, err := media.Probe(ctx, output)
			if err != nil {
				t.Fatal(err)
			}
			if out.Width != v.Width || out.Height != v.Height || out.Codec != tc.codec || out.HasAudio != v.HasAudio {
				t.Fatalf("unexpected output: %+v", out)
			}
			// Decode the exported media to ensure it is playable, not just probeable.
			if logs, e := exec.CommandContext(ctx, media.Binary("ffmpeg"), "-v", "error", "-i", output, "-f", "null", "-").CombinedOutput(); e != nil {
				t.Fatalf("output decode failed: %v %s", e, logs)
			}
			if out.Duration < 5.8 || out.Duration > 6.4 {
				t.Fatalf("unexpected duration %.3f", out.Duration)
			}
			reports = append(reports, report{p.ExportSettings, encoder, elapsed, out})
			t.Logf("actual encoder=%s elapsed=%.3fs output=%s", encoder, elapsed, output)
		})
	}
	if err := storage.WriteJSON(filepath.Join(dir, "real-video-report.json"), map[string]any{"source": v, "sample_spans_seconds": [][2]int{{30, 33}, {60, 63}}, "results": reports, "note": "Technical sample only. Human A/V sync check and actual rally detection remain pending."}); err != nil {
		t.Fatal(err)
	}
}
