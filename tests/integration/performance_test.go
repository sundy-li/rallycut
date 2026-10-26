package integration

import (
	"context"
	"os"
	"rallycut/backend/analysis"
	"rallycut/backend/media"
	"rallycut/backend/project"
	"rallycut/vision"
	"testing"
	"time"
)

func TestRealObservedPerformance(t *testing.T) {
	source := os.Getenv("RALLYCUT_PERFORMANCE_VIDEO")
	if source == "" {
		t.Skip("set RALLYCUT_PERFORMANCE_VIDEO to a short real video")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	python := analysis.Python("")
	worker, err := vision.Install(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if !analysis.CheckModel(python, worker) {
		t.Skip("install verified local model / torch")
	}
	video, err := media.Inspect(ctx, source)
	if err != nil {
		t.Fatal(err)
	}
	snapshots := []project.Performance{}
	result, err := analysis.RunObserved(ctx, python, worker, video, func(float64, string) {}, func(p *project.Performance) { snapshots = append(snapshots, *p) })
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshots) < 2 {
		t.Fatal("missing live telemetry")
	}
	last := snapshots[len(snapshots)-1]
	if last.Stage != "finalizing" || last.ProcessedFrames != result.Summary.SampledFrames || last.AverageFPS <= 0 {
		t.Fatal(last, result.Summary)
	}
	if result.Summary.Decoder != "opencv" || result.Summary.HardwareDecode || result.Summary.ProcessingFPS <= 0 {
		t.Fatal(result.Summary)
	}
	if result.Summary.AnalysisFPS <= 0 {
		t.Fatal("missing analysis average")
	}
	previous := -1
	for _, snapshot := range snapshots {
		if snapshot.ProcessedFrames < previous || snapshot.Validate() != nil {
			t.Fatal(snapshot)
		}
		previous = snapshot.ProcessedFrames
	}
	t.Logf("live snapshots=%d, processed=%d, processing=%.2f FPS, analysis=%.2f FPS", len(snapshots), last.ProcessedFrames, result.Summary.ProcessingFPS, result.Summary.AnalysisFPS)
}
