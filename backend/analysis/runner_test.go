package analysis

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"rallycut/backend/project"
	"rallycut/vision"
	"strings"
	"testing"
	"time"
)

func event(t *testing.T, e Event) string {
	t.Helper()
	b, err := json.Marshal(e)
	if err != nil {
		t.Fatal(err)
	}
	return string(b) + "\n"
}
func TestParseRejectsMalformedProtocol(t *testing.T) {
	for _, body := range []string{"", "not json\n", `{"protocol_version":2,"job_id":"x","type":"progress"}` + "\n", `{"protocol_version":1,"job_id":"wrong","type":"progress"}` + "\n", `{"protocol_version":1,"job_id":"x","type":"mystery"}` + "\n"} {
		if _, err := Parse(strings.NewReader(body), "x", 10, func(float64, string) {}); err == nil {
			t.Fatalf("accepted: %s", body)
		}
	}
}
func TestParseResultMustBeTerminal(t *testing.T) {
	e := Event{ProtocolVersion: 1, JobID: "x", Type: "result", Result: &Result{ProtocolVersion: 1, Model: Model, Rallies: []project.Rally{}, Summary: &project.AnalysisSummary{Method: Model, DecodedFrames: 1, TableBounds: []float64{.1, .4, .9, .6}, WeightsSHA256: WeightsSHA256}}}
	line := event(t, e)
	if _, err := Parse(strings.NewReader(line), "x", 10, func(float64, string) {}); err != nil {
		t.Fatal(err)
	}
	if _, err := Parse(strings.NewReader(line+line), "x", 10, func(float64, string) {}); err == nil {
		t.Fatal("duplicate result accepted")
	}
}
func TestParseStreamsCandidatesBeforeResult(t *testing.T) {
	rally := project.Rally{ID: "visual-00001", Start: 1, End: 2, Confidence: .5, Score: 60, Selected: true}
	candidates := event(t, Event{ProtocolVersion: 1, JobID: "x", Type: "candidates", Rallies: []project.Rally{rally}, ProcessedSeconds: 3.4})
	stop := event(t, Event{ProtocolVersion: 1, JobID: "x", Type: "error", Message: "stop"})
	var got []project.Rally
	var processed float64
	_, err := parseObserved(strings.NewReader(candidates+stop), "x", 10, func(float64, string) {}, nil, func(u Stream) {
		got, processed = u.Rallies, u.ProcessedSeconds
	})
	if err == nil || len(got) != 1 || got[0].ID != "visual-00001" || processed != 3.4 {
		t.Fatalf("streamed=%v processed=%v err=%v", got, processed, err)
	}
}

func TestStreamingAgainstRealWorker(t *testing.T) {
	clip := os.Getenv("RALLYCUT_E2E_CLIP")
	worker := os.Getenv("RALLYCUT_E2E_WORKER")
	if clip == "" || worker == "" {
		t.Skip("set RALLYCUT_E2E_CLIP and RALLYCUT_E2E_WORKER to exercise the real worker")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	var updates []int
	var processed float64
	tracks := 0
	table := false
	result, err := RunStreaming(ctx, filepath.Join("..", "..", ".venv", "bin", "python3"), worker,
		project.Video{Path: clip, Duration: 90, FPS: 29.97, Width: 1920, Height: 1080, HasAudio: true, Codec: "hevc"},
		func(float64, string) {}, nil,
		func(u Stream) {
			updates = append(updates, len(u.Rallies))
			processed = u.ProcessedSeconds
			tracks += len(u.Tracks)
			if len(u.TableBounds) == 4 {
				table = true
			}
		})
	if err != nil {
		t.Fatal(err)
	}
	if len(updates) < 2 {
		t.Fatalf("expected progressive candidate updates, got %v", updates)
	}
	if processed <= 0 || len(result.Rallies) < updates[len(updates)-1] {
		t.Fatalf("processed=%.1f updates=%v final=%d", processed, updates, len(result.Rallies))
	}
	if !table || tracks == 0 {
		t.Fatalf("overlay stream missing: table=%v streamed_tracks=%d", table, tracks)
	}
	t.Logf("candidate updates=%v processed=%.1fs final=%d tracks=%d streamed_tracks=%d",
		updates, processed, len(result.Rallies), len(result.Tracks), tracks)
}

func TestParseSkipsOutOfRangeCandidates(t *testing.T) {
	bad := event(t, Event{ProtocolVersion: 1, JobID: "x", Type: "candidates", Rallies: []project.Rally{{ID: "a", Start: 1, End: 99}}, ProcessedSeconds: 3})
	stop := event(t, Event{ProtocolVersion: 1, JobID: "x", Type: "error", Message: "stop"})
	called := false
	_, err := parseObserved(strings.NewReader(bad+stop), "x", 10, func(float64, string) {}, nil, func(u Stream) {
		called = called || len(u.Rallies) > 0
	})
	if err == nil || called {
		t.Fatalf("invalid candidates delivered: called=%v err=%v", called, err)
	}
}

func TestRealPythonWorkerDeterministic(t *testing.T) {
	python := Python("")
	if !CheckPython(python) {
		t.Skip("run just setup to install visual dependencies")
	}
	dir := t.TempDir()
	path, err := vision.Install(dir)
	if err != nil {
		t.Fatal(err)
	}
	source := filepath.Join(dir, "real-pixels.mp4")
	code := "import sys;sys.path.insert(0,sys.argv[1]);from test_worker import fixture;fixture(sys.argv[2])"
	if out, err := exec.Command(python, "-c", code, filepath.Join("..", "..", "vision", "tests"), source).CombinedOutput(); err != nil {
		t.Fatalf("fixture: %s %v", out, err)
	}
	v := project.Video{Path: source, Duration: 10}
	a, err := RunWithModel(context.Background(), python, path, v, ClassicalModel, func(float64, string) {})
	if err != nil {
		t.Fatal(err)
	}
	b, err := RunWithModel(context.Background(), python, path, v, ClassicalModel, func(float64, string) {})
	if err != nil {
		t.Fatal(err)
	}
	// Wall-clock diagnostics are intentionally not deterministic; detections are.
	a.Summary.ElapsedSeconds = 0
	b.Summary.ElapsedSeconds = 0
	aa, _ := json.Marshal(a)
	bb, _ := json.Marshal(b)
	if string(aa) != string(bb) || len(a.Rallies) == 0 {
		t.Fatal("non deterministic result")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	if _, err := RunWithModel(ctx, python, path, v, ClassicalModel, func(float64, string) {}); err == nil {
		t.Fatal("cancellation ignored")
	}
}
