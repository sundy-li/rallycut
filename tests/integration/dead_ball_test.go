package integration

import (
	"os"
	"rallycut/backend/project"
	"rallycut/backend/storage"
	"rallycut/backend/timeline"
	"testing"
)

func TestUser0043DeadBallProjectAndPadding(t *testing.T) {
	path := os.Getenv("RALLYCUT_TEST_DEAD_BALL_PROJECT")
	if path == "" {
		t.Skip("explicit real-video project path")
	}
	p, err := storage.Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if p.Analysis == nil || p.Analysis.RallyStateVersion != "dead-ball-v1" {
		t.Fatal("wrong state rules")
	}
	first, second := false, false
	for _, event := range p.Analysis.RallyEvents {
		if event.Type == "dead_ball" && event.Reason == "out_without_table_bounce" && event.Time > 17.7 && event.Time < 18.2 {
			first = true
		}
		if event.Type == "dead_ball" && event.Reason == "below_table_stopped" && event.Time > 34.1 && event.Time < 34.8 {
			second = true
		}
	}
	if !first || !second {
		t.Fatal("user-reported ends missing", p.Analysis.RallyEvents)
	}
	for _, r := range p.RawRallies {
		if (r.Start < 17.9 && r.End > 20.5) || (r.Start < 34.3 && r.End > 36.6) {
			t.Fatal("raw rally crossed confirmed dead interval", r)
		}
	}
	spans, err := timeline.Segments(p.RawRallies, project.Rules{PreRoll: 2, PostRoll: 2}, p.Video.Duration)
	if err != nil {
		t.Fatal(err)
	}
	for i, r := range p.RawRallies {
		if !r.BoundaryBefore || i == 0 {
			continue
		}
		cut := (p.RawRallies[i-1].End + r.Start) / 2
		for _, s := range spans {
			if s.Start < cut && s.End > cut {
				t.Fatal("export buffers erased a protected boundary", s, cut)
			}
		}
	}
	t.Logf("validated %d source frames, %d candidate rallies and %d independently protected export intervals", p.Analysis.DecodedFrames, len(p.RawRallies), len(spans))
}
