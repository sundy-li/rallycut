package agent

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"rallycut/backend/project"
)

func sample() *project.Project {
	v := project.Video{Path: "/videos/a.mp4", Name: "a.mp4", Fingerprint: "fp-a", Duration: 100, HasAudio: true}
	w := project.Video{Path: "/videos/b.mp4", Name: "b.mp4", Fingerprint: "fp-b", Duration: 50}
	p := &project.Project{SchemaVersion: 1, ID: "p", Name: "match", Rules: project.Rules{PreRoll: .5, PostRoll: .8},
		ExportSettings: project.ExportSettings{}.Normalized(),
		Sources: []project.Source{
			{ID: "s1", Video: v, Rallies: []project.Rally{
				{ID: "visual-00002", Start: 40, End: 48, Score: 60, Selected: true},
				{ID: "visual-00001", Start: 10, End: 15, Score: 30, Selected: true},
				{ID: "manual-1", Start: 70, End: 74, Selected: true, Favorite: true},
				{ID: "visual-00003", Start: 80, End: 90, Score: 90, Selected: true, Invalid: true},
			}},
			{ID: "s2", Video: w, Rallies: []project.Rally{
				{ID: "visual-00001", Start: 5, End: 9, Score: 50, Selected: true},
			}},
		}}
	p.ActiveSourceID = "s1"
	p.Video, p.Rallies = v, p.Sources[0].Rallies
	return p
}

func TestBriefNumbersRalliesAndRoundTrips(t *testing.T) {
	b := NewBrief(sample(), "/projects/match-rallycut.json")
	got := b.Sources[0].Rallies
	if got[0].Number != 1 || got[0].ID != "visual-00001" || got[0].Key != "s1/visual-00001" || !got[2].Human {
		t.Fatalf("numbering / keys / human flag wrong: %+v", got)
	}
	data, err := CompactJSON(b)
	if err != nil {
		t.Fatal(err)
	}
	var generic map[string]any
	if err := json.Unmarshal(data, &generic); err != nil {
		t.Fatalf("compact JSON invalid: %v\n%s", err, data)
	}
	if strings.Contains(string(data), `"rallies":null`) {
		t.Fatal("duplicate / null rallies key")
	}
	p, kind, err := Parse(data)
	if err != nil || kind != BriefKind {
		t.Fatal(kind, err)
	}
	want, _ := NewPlan(sample(), 0)
	plan, err := NewPlan(p, 0)
	if err != nil {
		t.Fatal(err)
	}
	if plan.TotalDuration != want.TotalDuration || len(plan.Spans) != len(want.Spans) {
		t.Fatalf("brief round trip changed the plan: %+v vs %+v", plan, want)
	}
	text, err := Markdown(b)
	if err != nil || !strings.Contains(text, "'/projects/match-rallycut.json'") || !strings.Contains(text, "rallycut.py\" export") {
		t.Fatalf("markdown missing project path or commands: %v", err)
	}
	if strings.Contains(text, "```json") || strings.Contains(text, "visual-00002") {
		t.Fatal("clipboard text must reference the file, not embed rally JSON")
	}
	if _, err := Markdown(NewBrief(sample(), "")); err == nil {
		t.Fatal("unsaved project must not produce a brief without a file")
	}
}

func TestApplySelection(t *testing.T) {
	p := sample()
	n, err := Apply(p, Selection{MaxRallies: 2})
	if err != nil || n != 2 {
		t.Fatal(n, err)
	}
	selected := map[string]bool{}
	for _, s := range p.Sources {
		for _, r := range s.Rallies {
			if r.Selected {
				selected[s.ID+"/"+r.ID] = true
			}
		}
	}
	// Favorite first, then the highest score; the invalid 90-score rally never counts.
	if !selected["s1/manual-1"] || !selected["s1/visual-00002"] || len(selected) != 2 {
		t.Fatalf("max-rallies picked %v", selected)
	}

	p = sample()
	if _, err := Apply(p, Selection{Keys: []string{"visual-00001"}}); err == nil {
		t.Fatal("ambiguous bare id across sources must fail")
	}
	n, err = Apply(p, Selection{Keys: []string{"s2/visual-00001", "manual-1"}})
	if err != nil || n != 2 {
		t.Fatal(n, err)
	}
	// Card numbers: source 1 is sorted 10 s, 40 s, 70 s, 80 s.
	p = sample()
	if _, err := Apply(p, Selection{Keys: []string{"2"}}); err == nil {
		t.Fatal("bare number in a two-source project must fail")
	}
	n, err = Apply(p, Selection{Keys: []string{"1:2", "2:1", "1:4"}})
	if err != nil || n != 2 { // 1:4 is invalid and never exported
		t.Fatal(n, err)
	}
	if _, err := Apply(sample(), Selection{Keys: []string{"1:9"}}); err == nil {
		t.Fatal("out-of-range number accepted")
	}
	pre, post := 2.0, 1.0
	p = sample()
	if _, err := Apply(p, Selection{PreRoll: &pre, PostRoll: &post, MinDuration: 5}); err != nil {
		t.Fatal(err)
	}
	if p.Rules.PreRoll != 2 || p.Rules.PostRoll != 1 {
		t.Fatal("padding not applied")
	}
	plan, err := NewPlan(p, 0)
	if err != nil {
		t.Fatal(err)
	}
	for _, s := range plan.Spans {
		if s.Source == "s2" {
			t.Fatal("4 s rally must be dropped by min-duration 5")
		}
	}
	bad := 61.0
	if _, err := Apply(sample(), Selection{PreRoll: &bad}); err == nil {
		t.Fatal("pre-roll over 60 s accepted")
	}
}

func TestParseSegmentsAndProjectFiles(t *testing.T) {
	segments := `{"schema_version":1,"kind":"rallycut.segments","model":"blurball-pretrained-v1",
	 "source":{"path":"/videos/a.mp4","name":"a.mp4","fingerprint":"fp","duration":60},
	 "segments":[{"id":"visual-00001","start":1,"end":5,"duration":4,"start_timecode":"x","selected":true,"confidence":0.5,"score":10}]}`
	p, kind, err := Parse([]byte(segments))
	if err != nil || kind != SegmentsKind || len(p.Sources[0].Rallies) != 1 || p.Rules != project.DefaultRules() {
		t.Fatal(kind, err)
	}
	if _, _, err := Parse([]byte(strings.Replace(segments, `"fingerprint":"fp",`, "", 1))); err == nil {
		t.Fatal("a source without fingerprint must be rejected")
	}
	if _, _, err := Parse([]byte(strings.Replace(segments, `"end":5`, `"end":99`, 1))); err == nil {
		t.Fatal("rally past the video end must be rejected")
	}
	if _, _, err := Parse([]byte(`{"kind":"other","schema_version":1}`)); err == nil {
		t.Fatal("unknown kind accepted")
	}
	data, _ := json.Marshal(sample())
	path := filepath.Join(t.TempDir(), "match-rallycut.json")
	os.WriteFile(path, data, 0600)
	p, kind, err = Load(path)
	if err != nil || kind != "rallycut.project" || len(p.Sources) != 2 {
		t.Fatal(kind, err)
	}
}
