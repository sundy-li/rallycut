package timeline

import (
	"fmt"
	"math"
	"rallycut/backend/project"
	"testing"
)

func rally(id string, s, e float64) project.Rally {
	return project.Rally{ID: id, Start: s, End: e, Selected: true, Score: 50, Confidence: .8}
}
func TestSegmentsClampsSortsAndCoalesces(t *testing.T) {
	rs := []project.Rally{rally("c", 8, 9.8), rally("b", 3, 5), rally("a", .2, 2.5)}
	spans, err := Segments(rs, project.Rules{PreRoll: 1, PostRoll: 1}, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(spans) != 2 || spans[0] != (Segment{0, 6}) || spans[1] != (Segment{7, 10}) {
		t.Fatalf("unexpected spans: %+v", spans)
	}
}
func TestInvalidAndEmptySelection(t *testing.T) {
	for _, rs := range [][]project.Rally{nil, {rally("a", 3, 2)}, {rally("a", 0, math.NaN())}, {rally("a", 0, 2), rally("a", 3, 4)}} {
		if _, err := Segments(rs, project.Rules{}, 10); err == nil {
			t.Fatalf("expected error: %+v", rs)
		}
	}
}
func TestSplitMergePreservesSelection(t *testing.T) {
	original := []project.Rally{rally("a", 1, 8), rally("b", 12, 15)}
	rs, err := Split(original, "a", 4)
	if err != nil {
		t.Fatal(err)
	}
	if len(rs) != 3 || original[0].End != 8 || !rs[0].Edited || !rs[1].Selected {
		t.Fatalf("bad split %+v", rs)
	}
	rs, err = Merge(rs, []string{rs[0].ID, rs[1].ID})
	if err != nil {
		t.Fatal(err)
	}
	if len(rs) != 2 || rs[0].Start != 1 || rs[0].End != 8 {
		t.Fatal(rs)
	}
	if _, err := Split(rs, "a", 8); err == nil {
		t.Fatal("split at end accepted")
	}
}
func TestNonAdjacentMergeRejected(t *testing.T) {
	rs := []project.Rally{rally("a", 0, 1), rally("b", 2, 3), rally("c", 4, 5)}
	if _, err := Merge(rs, []string{"a", "c"}); err == nil {
		t.Fatal("nonadjacent merge accepted")
	}
}

func TestInvalidRalliesAreExcludedFromExport(t *testing.T) {
	rs := []project.Rally{rally("valid", 1, 3), rally("invalid-net-serve", 5, 7)}
	rs[1].Invalid = true
	spans, err := Segments(rs, project.Rules{PreRoll: .5, PostRoll: .5}, 10)
	if err != nil || len(spans) != 1 || spans[0] != (Segment{.5, 3.5}) {
		t.Fatalf("invalid rally leaked into export: %+v %v", spans, err)
	}
	rs[0].Invalid = true
	if _, err := Segments(rs, project.Rules{}, 10); err == nil {
		t.Fatal("all-invalid selection should have nothing to export")
	}
}

func TestResolveOverlapsPolicies(t *testing.T) {
	human := func(id string, s, e float64) project.Rally {
		return project.Rally{ID: "manual-" + id, Start: s, End: e, Selected: true, Edited: true}
	}
	machine := func(id string, s, e float64) project.Rally {
		return project.Rally{ID: id, Start: s, End: e, Selected: true}
	}
	// h1 starts first and overlaps m1; m2 starts first and overlaps h2.
	rs := []project.Rally{
		human("h1", 10, 20), machine("m1", 15, 30),
		machine("m2", 40, 50), human("h2", 45, 60),
		machine("m3", 70, 80), // no conflict
	}
	if n := OverlapConflicts(rs); n != 2 {
		t.Fatalf("conflicts = %d", n)
	}
	kept := func(mode string) []string {
		ids := []string{}
		for _, r := range ResolveOverlaps(rs, mode) {
			if r.Selected {
				ids = append(ids, r.ID)
			}
		}
		return ids
	}
	cases := map[string][]string{
		project.OverlapMerge:      {"manual-h1", "m1", "m2", "manual-h2", "m3"},
		project.OverlapHuman:      {"manual-h1", "manual-h2", "m3"},
		project.OverlapMachine:    {"m1", "m2", "m3"},
		project.OverlapSequential: {"manual-h1", "m2", "m3"},
	}
	for mode, want := range cases {
		if got := kept(mode); fmt.Sprint(got) != fmt.Sprint(want) {
			t.Errorf("%s: got %v want %v", mode, got, want)
		}
	}
	// The loser is skipped entirely, so its non-overlapping footage is gone.
	spans, err := ExportSegments(rs, project.Rules{}, project.ExportSettings{Overlap: project.OverlapHuman}, 100)
	if err != nil || len(spans) != 3 || spans[0] != (Segment{10, 20}) || spans[1] != (Segment{45, 60}) {
		t.Fatalf("human spans %+v %v", spans, err)
	}
	spans, _ = ExportSegments(rs, project.Rules{}, project.ExportSettings{}, 100)
	if len(spans) != 3 || spans[0] != (Segment{10, 30}) || spans[1] != (Segment{40, 60}) {
		t.Fatalf("default merge spans %+v", spans)
	}
	// The input timeline is never mutated.
	for _, r := range rs {
		if !r.Selected {
			t.Fatalf("input mutated: %+v", r)
		}
	}
}

func TestSameKindOverlapsAlwaysMerge(t *testing.T) {
	rs := []project.Rally{
		{ID: "m1", Start: 0, End: 10, Selected: true},
		{ID: "m2", Start: 8, End: 15, Selected: true},
		{ID: "manual-a", Start: 30, End: 40, Selected: true, Edited: true},
		{ID: "manual-b", Start: 35, End: 45, Selected: true, Edited: true},
	}
	for _, mode := range []string{project.OverlapSequential, project.OverlapHuman, project.OverlapMachine} {
		if OverlapConflicts(rs) != 0 {
			t.Fatal("same-kind overlap counted as conflict")
		}
		spans, err := ExportSegments(rs, project.Rules{}, project.ExportSettings{Overlap: mode}, 100)
		if err != nil || len(spans) != 2 || spans[0] != (Segment{0, 15}) || spans[1] != (Segment{30, 45}) {
			t.Fatalf("%s: %+v %v", mode, spans, err)
		}
	}
}

func TestOverlapIgnoresDeselectedAndInvalid(t *testing.T) {
	rs := []project.Rally{
		{ID: "manual-x", Start: 0, End: 10, Selected: true, Edited: true, Invalid: true},
		{ID: "m1", Start: 5, End: 15, Selected: true},
		{ID: "manual-y", Start: 12, End: 20, Edited: true},
	}
	if OverlapConflicts(rs) != 0 {
		t.Fatal("non-exported rallies must not conflict")
	}
	got := ResolveOverlaps(rs, project.OverlapHuman)
	if !got[1].Selected {
		t.Fatal("machine rally dropped by a non-exported human rally")
	}
}

func TestExportSettingsRejectUnknownOverlap(t *testing.T) {
	if project.ValidateExport(project.ExportSettings{Overlap: "bogus"}) == nil {
		t.Fatal("unknown overlap policy accepted")
	}
	if (project.ExportSettings{}).Normalized().Overlap != project.OverlapMerge {
		t.Fatal("default must be merge")
	}
}

func TestExportPlanLabelsRalliesByTimelineNumber(t *testing.T) {
	rules := project.Rules{PreRoll: 1.5, PostRoll: 2}
	rs := []project.Rally{
		{ID: "a", Start: 10, End: 20, Selected: true},
		{ID: "b", Start: 21, End: 30, Selected: true}, // padding merges a+b
		{ID: "c", Start: 40, End: 45, Selected: false},
		{ID: "d", Start: 60, End: 70, Selected: true},
	}
	segs, labels, err := ExportPlan(rs, rules, project.ExportSettings{}, 100)
	if err != nil {
		t.Fatal(err)
	}
	if len(segs) != 2 || len(labels) != 2 {
		t.Fatalf("segs=%v labels=%v", segs, labels)
	}
	want0 := []Label{{Number: 1, From: segs[0].Start}, {Number: 2, From: 21}}
	if len(labels[0]) != 2 || labels[0][0] != want0[0] || labels[0][1] != want0[1] {
		t.Fatalf("merged span labels = %v, want %v", labels[0], want0)
	}
	if len(labels[1]) != 1 || labels[1][0].Number != 4 {
		t.Fatalf("second span labels = %v (deselected rally must keep its number slot)", labels[1])
	}
}
