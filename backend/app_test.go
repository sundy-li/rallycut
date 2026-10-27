package backend

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"path/filepath"
	"testing"

	"rallycut/backend/analysis"
	"rallycut/backend/project"
	setupenv "rallycut/backend/setup"
)

func newTestApp(t *testing.T, p *project.Project) (*App, string) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "match-rallycut.json")
	readySetup := setupenv.New(setupenv.Options{DataDir: filepath.Dir(path)})
	readySetup.MarkReady("test-python")
	return &App{
		setup:       readySetup,
		ctx:         context.Background(),
		dataDir:     filepath.Dir(path),
		worker:      "test-worker",
		current:     p,
		projectPath: path,
		log:         slog.New(slog.NewTextHandler(os.Stderr, nil)),
	}, path
}

func TestKeepPartialRalliesPreservesCancelledRounds(t *testing.T) {
	a, path := newTestApp(t, &project.Project{
		ID:  "x",
		Job: &project.Job{ID: "j", Status: "running", Candidates: []project.Rally{{ID: "c1", Start: 1, End: 2}}, ProcessedSeconds: 12},
	})
	a.keepPartialRallies([]project.Rally{{ID: "v1", Start: 1, End: 2.5, Selected: true}})

	if a.current == nil || !a.current.PartialAnalysis || len(a.current.Rallies) != 1 {
		t.Fatalf("in-memory project not kept: %+v", a.current)
	}
	if a.current.Job == nil || len(a.current.Job.Candidates) != 0 {
		t.Fatalf("provisional candidates leaked into project: %+v", a.current.Job)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var saved project.Project
	if err := json.Unmarshal(raw, &saved); err != nil {
		t.Fatal(err)
	}
	if !saved.PartialAnalysis || len(saved.Rallies) != 1 || saved.Rallies[0].ID != "v1" {
		t.Fatalf("saved project missing partial rounds: %+v", saved)
	}
}

func TestKeepPartialRalliesLeavesNonemptyManualTimelineAlone(t *testing.T) {
	a, _ := newTestApp(t, &project.Project{ID: "x", ManualTimeline: true, Rallies: []project.Rally{{ID: "manual", Start: 2, End: 7}}})
	a.keepPartialRallies([]project.Rally{{ID: "v1", Start: 1, End: 2}})
	if a.current.PartialAnalysis || len(a.current.Rallies) != 1 || a.current.Rallies[0].ID != "manual" {
		t.Fatalf("manual timeline was overwritten: %+v", a.current)
	}
}

func TestKeepPartialRalliesFillsEmptyTimeline(t *testing.T) {
	a, _ := newTestApp(t, &project.Project{ID: "x", ManualTimeline: true})
	a.keepPartialRallies([]project.Rally{{ID: "v1", Start: 1, End: 2}})
	if !a.current.PartialAnalysis || len(a.current.Rallies) != 1 || a.current.ManualTimeline {
		t.Fatalf("empty timeline did not use partial machine rounds: %+v", a.current)
	}
}

func TestUpdateTimelineAutomaticallyRestoresRawWhenEmpty(t *testing.T) {
	p := project.New(project.Video{Path: "source.mp4", Duration: 20})
	p.RawRallies = []project.Rally{{ID: "raw", Start: 1, End: 8}}
	p.Rallies = append([]project.Rally{}, p.RawRallies...)
	p.SyncActive()
	a, path := newTestApp(t, p)
	got, err := a.UpdateTimeline(nil, p.Rules)
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Rallies) != 1 || got.Rallies[0].ID != "raw" || got.ManualTimeline {
		t.Fatalf("empty timeline not restored from machine candidates: %+v", got)
	}
	if len(got.Sources) != 1 || len(got.Sources[0].Rallies) != 1 {
		t.Fatalf("active source not synchronized: %+v", got.Sources)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var saved project.Project
	if err := json.Unmarshal(data, &saved); err != nil {
		t.Fatal(err)
	}
	if len(saved.Rallies) != 1 || len(saved.Sources[0].Rallies) != 1 {
		t.Fatalf("saved timeline/source lost adopted candidates: %+v", saved)
	}
}

func TestUseAnalysisCandidatesPersistsActiveSource(t *testing.T) {
	p := project.New(project.Video{Path: "source.mp4", Duration: 20})
	p.RawRallies = []project.Rally{{ID: "raw", Start: 1, End: 8}}
	p.Rallies = []project.Rally{{ID: "manual", Start: 2, End: 7, Edited: true}}
	p.ManualTimeline = true
	p.Model = analysis.Model
	p.Analysis = &project.AnalysisSummary{}
	p.SyncActive()
	a, path := newTestApp(t, p)
	got, err := a.UseAnalysisCandidates()
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Rallies) != 1 || got.Rallies[0].ID != "raw" || got.ManualTimeline {
		t.Fatalf("explicit candidate adoption failed: %+v", got)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var saved project.Project
	if err := json.Unmarshal(data, &saved); err != nil {
		t.Fatal(err)
	}
	if len(saved.Sources) != 1 || len(saved.Sources[0].Rallies) != 1 || saved.Sources[0].Rallies[0].ID != "raw" {
		t.Fatalf("active source was not saved: %+v", saved.Sources)
	}
}

func TestInstallAdoptsCandidatesForLegacyEmptyTimeline(t *testing.T) {
	p := project.New(project.Video{Path: "source.mp4", Duration: 20})
	p.RawRallies = []project.Rally{{ID: "raw", Start: 1, End: 8}}
	p.Rallies = []project.Rally{}
	p.ManualTimeline = true
	p.SyncActive()
	a, path := newTestApp(t, p)
	if err := a.install(p, path); err != nil {
		t.Fatal(err)
	}
	if len(a.current.Rallies) != 1 || a.current.ManualTimeline || len(a.current.Sources[0].Rallies) != 1 {
		t.Fatalf("loaded empty timeline was not adopted and synchronized: %+v", a.current)
	}
}

func TestStreamEventUsesManagerJobID(t *testing.T) {
	a := &App{}
	block := make(chan struct{})
	job, err := a.manager.Start(context.Background(), "analysis", func(project.Job) {},
		func(ctx context.Context, p func(float64, string)) (string, error) {
			<-block
			return "", nil
		})
	if err != nil {
		t.Fatal(err)
	}
	event := a.streamEvent(analysis.Stream{
		JobID:       "worker-internal",
		Tracks:      []project.BallTrack{{ID: "track-1"}},
		TableBounds: []float64{.1, .2, .3, .4},
	})
	if event.JobID != job.ID || event.JobID == "worker-internal" {
		t.Fatalf("stream job id %q, want manager id %q", event.JobID, job.ID)
	}
	if len(event.Tracks) != 1 || len(event.TableBounds) != 4 {
		t.Fatalf("overlay payload dropped: %+v", event)
	}
	close(block)
	a.manager.Wait()
	if a.manager.CurrentID() != "" {
		t.Fatalf("id kept after finish")
	}
}

func TestDedupeVideos(t *testing.T) {
	existing := []project.Source{{Video: project.Video{Path: "/match/a.mp4", Fingerprint: "aaa"}}}
	got := dedupeVideos(existing, []project.Video{
		{Path: "/match/a.mp4", Fingerprint: "aaa"},      // same path
		{Path: "/match/a-copy.mp4", Fingerprint: "aaa"}, // same content
		{Path: "/match/b.mp4", Fingerprint: "bbb"},
		{Path: "/match/b.mp4", Fingerprint: "bbb"}, // duplicate in the same batch
	})
	if len(got) != 1 || got[0].Path != "/match/b.mp4" {
		t.Fatalf("dedupe = %+v, want only b.mp4", got)
	}
}

func TestRevealExportOnlyUsesCompletedExportJob(t *testing.T) {
	for _, job := range []*project.Job{
		nil,
		{Kind: "analysis", Status: "completed", Output: "/tmp/x.mp4"},
		{Kind: "export", Status: "failed", Output: "/tmp/x.mp4"},
		{Kind: "export", Status: "completed"},
	} {
		a, _ := newTestApp(t, &project.Project{ID: "x", Job: job})
		if _, err := a.exportOutput(); err == nil {
			t.Fatal("unexpected reveal target", job)
		}
	}
	a, _ := newTestApp(t, &project.Project{ID: "x", Job: &project.Job{Kind: "export", Status: "completed", Output: "/tmp/out.mp4"}})
	if path, err := a.exportOutput(); err != nil || path != "/tmp/out.mp4" {
		t.Fatal(path, err)
	}
	// A completed job whose file was moved away reports an error, not a crash.
	a.current.Job.Output = filepath.Join(t.TempDir(), "gone.mp4")
	if err := a.RevealExport(); err == nil {
		t.Fatal("missing export should error")
	}
}
