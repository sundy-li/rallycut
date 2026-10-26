package project

import "testing"

func TestRallyEvidenceValidationAndClone(t *testing.T) {
	summary := &AnalysisSummary{RallyStateVersion: "dead-ball-v1", RallyEvents: []RallyEvent{{Type: "dead_ball", Time: 17.92, ConfirmedAt: 18.15, Reason: "out_without_table_bounce", Confidence: .83, X: .89, Y: .26, Signals: []string{"beyond_target_end"}}}}
	if err := ValidateRallyEvents(summary, 30); err != nil {
		t.Fatal(err)
	}
	p := New(Video{Path: "source", Duration: 30})
	p.Analysis = summary
	clone := Clone(p)
	clone.Analysis.RallyEvents[0].Signals[0] = "mutated"
	if summary.RallyEvents[0].Signals[0] != "beyond_target_end" {
		t.Fatal("aliased event evidence")
	}
	summary.RallyEvents[0].ConfirmedAt = 17
	if err := ValidateRallyEvents(summary, 30); err == nil {
		t.Fatal("reverse event timing accepted")
	}
}
