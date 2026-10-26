package timeline

import (
	"rallycut/backend/project"
	"testing"
)

func TestDeadBoundaryCapsPaddingAndCannotRejoin(t *testing.T) {
	rallies := []project.Rally{
		{ID: "first", Start: 10, End: 17.92, Selected: true, EndReason: "out_without_table_bounce", EndEventTime: 17.92, EndConfidence: .83},
		{ID: "next", Start: 18.1, End: 23, Selected: true, BoundaryBefore: true, StartReason: "serve_restart"},
	}
	spans, err := Segments(rallies, project.Rules{PreRoll: 2, PostRoll: 2}, 30)
	cut := (rallies[0].End + rallies[1].Start) / 2
	if err != nil || len(spans) != 2 || spans[0].End != cut || spans[1].Start != cut {
		t.Fatal(spans, err)
	}
	rallies[1].Start = 17.92
	spans, err = Segments(rallies, project.Rules{PreRoll: 2, PostRoll: 2}, 30)
	if err != nil || len(spans) != 2 {
		t.Fatal("touching guarded spans merged", spans, err)
	}
	rallies[0].Selected = false
	spans, err = Segments(rallies, project.Rules{PreRoll: 2, PostRoll: 2}, 30)
	if err != nil || len(spans) != 1 || spans[0].Start != 17.92 {
		t.Fatal("unselected prior rally lost fence", spans, err)
	}
	merged, err := Merge(rallies, []string{"first", "next"})
	if err != nil || merged[0].EndReason != "" {
		t.Fatal("manual merge retained internal dead end", merged, err)
	}
	spans, err = Segments(merged, project.Rules{PreRoll: 2, PostRoll: 2}, 30)
	if err != nil || len(spans) != 1 || spans[0].End != 25 {
		t.Fatal("explicit override failed", spans, err)
	}
}

func TestOverlappingRallyAcrossGuardStillExports(t *testing.T) {
	rules := project.Rules{PreRoll: .5, PostRoll: .8}
	rallies := []project.Rally{
		{ID: "manual", Start: 114.71, End: 119.22, Selected: true, Edited: true},
		{ID: "machine", Start: 116.02, End: 119.9, Selected: true, BoundaryBefore: true, StartReason: "serve_restart"},
		{ID: "after", Start: 125, End: 128, Selected: true, BoundaryBefore: true, StartReason: "serve_restart"},
	}
	spans, err := Segments(rallies, rules, 200)
	if err != nil || len(spans) != 2 || spans[0] != (Segment{114.21, 120.7}) || spans[1] != (Segment{124.5, 128.8}) {
		t.Fatal("overlap should merge without duplicating footage", spans, err)
	}
	// An unselected overlapping rally is not exported, so the guard still caps
	// the machine rally's pre-roll at its own start.
	rallies[0].Selected = false
	spans, err = Segments(rallies, rules, 200)
	if err != nil || len(spans) != 2 || spans[0].Start != 116.02 {
		t.Fatal("unselected overlap removed guard", spans, err)
	}
}
