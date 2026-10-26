package project

import "testing"

func TestCloneOwnsPipelineMetadata(t *testing.T) {
	enabled := true
	p := New(Video{Path: "source.mp4", Duration: 30})
	p.Analysis = &AnalysisSummary{Pipeline: &enabled, PipelineTimings: map[string]float64{"batches": 25, "wall_seconds": 2.1}}
	q := Clone(p)
	*q.Analysis.Pipeline = false
	q.Analysis.PipelineTimings["batches"] = 999
	if !*p.Analysis.Pipeline || p.Analysis.PipelineTimings["batches"] != 25 {
		t.Fatal("clone aliases analysis metadata")
	}
	if q.Analysis.PipelineTimings["wall_seconds"] != 2.1 {
		t.Fatal("clone lost phase timings")
	}
}
