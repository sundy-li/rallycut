package integration

import (
	"context"
	"os"
	"rallycut/backend/analysis"
	"rallycut/backend/media"
	"rallycut/backend/storage"
	"testing"
)

// Opt-in validation for a real, saved private-video result. Never loads private
// media or downloads weights on a normal CI run.
func TestSavedPretrainedProject(t *testing.T) {
	path := os.Getenv("RALLYCUT_TEST_PRETRAINED_PROJECT")
	if path == "" {
		t.Skip("set RALLYCUT_TEST_PRETRAINED_PROJECT to opt in")
	}
	p, err := storage.Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if p.Model != analysis.Model {
		t.Fatalf("wrong detector %s", p.Model)
	}
	result := &analysis.Result{ProtocolVersion: analysis.ProtocolVersion, Model: p.Model, Rallies: p.RawRallies, Tracks: p.Tracks, Summary: p.Analysis}
	if err := analysis.Validate(result, p.Video.Duration); err != nil {
		t.Fatal(err)
	}
	hash, err := media.Fingerprint(context.Background(), p.Video.Path)
	if err != nil {
		t.Fatal(err)
	}
	if hash != p.Video.Fingerprint {
		t.Fatal("source fingerprint changed")
	}
	if len(p.RawRallies) == 0 || len(p.Tracks) == 0 || p.Analysis.DetectionFrames == 0 {
		t.Fatal("empty real-video evidence")
	}
	t.Logf("validated %d real frames, %d learned tracks, %d candidate rallies", p.Analysis.DecodedFrames, len(p.Tracks), len(p.RawRallies))
}
