package project

import (
	"testing"
	"time"
)

func TestNewProjectUsesIndependentTimestampName(t *testing.T) {
	at := time.Date(2026, 10, 24, 15, 24, 33, 0, time.Local)
	p := NewAt(Video{Path: "/videos/match.mp4", Name: "match.mp4", Duration: 20}, at)
	if p.Name != "20261024-152433" {
		t.Fatalf("unexpected default project name: %q", p.Name)
	}
	if p.Name == p.Video.Name {
		t.Fatal("project name must not inherit the video filename")
	}
}

func TestAnalysisTimelinePolicy(t *testing.T) {
	raw := []Rally{{ID: "raw", Start: 1, End: 8}}
	t.Run("re-analysis replaces machine rallies but keeps human ones", func(t *testing.T) {
		p := New(Video{Path: "source.mp4", Duration: 60})
		p.Rallies = []Rally{
			{ID: "m1", Start: 1, End: 5, Selected: true},                       // untouched machine: replaced
			{ID: "m2", Start: 10, End: 14, Selected: true, Edited: true},       // corrected: kept
			{ID: "manual-1", Start: 30, End: 34, Selected: true, Edited: true}, // added: kept
			{ID: "m3", Start: 40, End: 45},                                     // deselected machine
		}
		p.ManualTimeline = true
		fresh := []Rally{
			{ID: "m1", Start: 1.5, End: 6, Selected: true},    // new machine version
			{ID: "m2", Start: 11, End: 15, Selected: true},    // overlaps corrected m2: both kept
			{ID: "n1", Start: 20, End: 25, Selected: true},    // brand new
			{ID: "m3b", Start: 40.5, End: 45, Selected: true}, // matches deselected m3
		}
		stats := p.ApplyAnalysis(fresh, "mock-v1")
		got := map[string]Rally{}
		for _, r := range p.Rallies {
			got[r.ID] = r
		}
		if len(p.Rallies) != 6 {
			t.Fatalf("want m1,m2,m2-r2,n1,manual-1,m3b; got %+v", p.Rallies)
		}
		if c, ok := got["m2-r2"]; !ok || c.Edited || c.Start != 11 || !c.Selected {
			t.Fatalf("machine candidate overlapping a correction must stay as its own machine rally: %+v", p.Rallies)
		}
		if got["m1"].Start != 1.5 || got["m1"].Edited {
			t.Fatalf("machine rally not replaced: %+v", got["m1"])
		}
		if got["m2"].Start != 10 || !got["m2"].Edited {
			t.Fatalf("corrected rally overwritten: %+v", got["m2"])
		}
		if _, ok := got["manual-1"]; !ok {
			t.Fatal("manually added rally lost")
		}
		if got["m3b"].Selected {
			t.Fatal("deselected machine rally must stay deselected")
		}
		for i := 1; i < len(p.Rallies); i++ {
			if p.Rallies[i].Start < p.Rallies[i-1].Start {
				t.Fatalf("not sorted: %+v", p.Rallies)
			}
		}
		if stats != (AnalysisMerge{KeptHuman: 2, Machine: 4, OverlapHuman: 1, KeptDeselected: 1}) {
			t.Fatalf("stats: %+v", stats)
		}
		if !p.ManualTimeline || len(p.RawRallies) != 4 {
			t.Fatalf("manual flag / raw candidates: %v %d", p.ManualTimeline, len(p.RawRallies))
		}
		if err := p.Validate(); err != nil {
			t.Fatalf("merged timeline invalid: %v", err)
		}
	})
	t.Run("new candidate ids never collide with kept human ids", func(t *testing.T) {
		p := New(Video{Path: "source.mp4", Duration: 60})
		p.Rallies = []Rally{{ID: "r1", Start: 1, End: 5, Selected: true, Edited: true}}
		p.ManualTimeline = true
		p.ApplyAnalysis([]Rally{{ID: "r1", Start: 20, End: 25, Selected: true}}, "mock-v1")
		if len(p.Rallies) != 2 || p.Rallies[1].ID == "r1" {
			t.Fatalf("duplicate id: %+v", p.Rallies)
		}
		if err := p.Validate(); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("only machine selection changes: machine result replaces, flag cleared", func(t *testing.T) {
		p := New(Video{Path: "source.mp4", Duration: 60})
		p.Rallies = []Rally{{ID: "m1", Start: 1, End: 5, Selected: true}}
		p.ManualTimeline = true
		p.ApplyAnalysis([]Rally{{ID: "x", Start: 20, End: 25, Selected: true}}, "mock-v1")
		if len(p.Rallies) != 1 || p.Rallies[0].ID != "x" || p.ManualTimeline {
			t.Fatalf("machine timeline not replaced: %+v manual=%v", p.Rallies, p.ManualTimeline)
		}
	})
	t.Run("empty timeline always adopts machine result", func(t *testing.T) {
		for _, manual := range []bool{false, true} {
			p := New(Video{Path: "source.mp4", Duration: 20})
			p.Rallies = []Rally{}
			p.ManualTimeline = manual
			p.ApplyAnalysis(raw, "mock-v1")
			if len(p.Rallies) != 1 || p.Rallies[0].ID != "raw" || p.ManualTimeline {
				t.Fatalf("empty timeline not adopted (manual=%t): %+v", manual, p.Rallies)
			}
		}
	})
	t.Run("analysis arrays do not alias", func(t *testing.T) {
		p := New(Video{Path: "source.mp4", Duration: 20})
		p.ApplyAnalysis(raw, "mock-v1")
		p.Rallies[0].Start = 3
		if p.RawRallies[0].Start != 1 || raw[0].Start != 1 {
			t.Fatal("analysis arrays alias")
		}
	})
}

func TestAdoptAnalysisCandidatesIfEmpty(t *testing.T) {
	p := New(Video{Path: "source.mp4", Duration: 20})
	p.RawRallies = []Rally{{ID: "raw", Start: 1, End: 8}}
	p.ManualTimeline = true
	if !p.AdoptAnalysisCandidatesIfEmpty() || len(p.Rallies) != 1 || p.ManualTimeline {
		t.Fatalf("empty timeline not adopted: %+v", p)
	}
	p.Rallies = []Rally{{ID: "manual", Start: 2, End: 7, Edited: true}}
	p.ManualTimeline = true
	if p.AdoptAnalysisCandidatesIfEmpty() || p.Rallies[0].ID != "manual" {
		t.Fatal("non-empty manual timeline was replaced")
	}
}
