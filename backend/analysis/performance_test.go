package analysis

import (
	"rallycut/backend/project"
	"strings"
	"testing"
)

func TestPerformanceProgressOptionalValidatedAndObservedBeforeProgress(t *testing.T) {
	result := Event{ProtocolVersion: 1, JobID: "x", Type: "result", Result: &Result{ProtocolVersion: 1, Model: Model,
		Rallies: []project.Rally{}, Summary: &project.AnalysisSummary{Method: Model, DecodedFrames: 120,
			WeightsSHA256: WeightsSHA256, TableBounds: []float64{.1, .4, .9, .6}}}}
	metrics := &project.Performance{Stage: "inference", ProcessedFrames: 120, ElapsedSeconds: 1, RecentFPS: 120, AverageFPS: 120}
	progress := Event{ProtocolVersion: 1, JobID: "x", Type: "progress", Progress: .5, Performance: metrics}
	order := []string{}
	_, err := parseObserved(strings.NewReader(event(t, progress)+event(t, result)), "x", 10,
		func(float64, string) { order = append(order, "progress") }, func(p *project.Performance) {
			if p.ProcessedFrames != 120 || p.AverageFPS != 120 {
				t.Fatal(p)
			}
			order = append(order, "performance")
		}, nil)
	if err != nil || strings.Join(order, ",") != "performance,progress" {
		t.Fatal(err, order)
	}
	if _, err := Parse(strings.NewReader(event(t, progress)+event(t, result)), "x", 10, func(float64, string) {}); err != nil {
		t.Fatal(err)
	}
	for _, invalid := range []project.Performance{{Stage: "gpu"}, {Stage: "inference", AverageFPS: -1}, {Stage: "inference", ProcessedFrames: -1}} {
		progress.Performance = &invalid
		if _, err := Parse(strings.NewReader(event(t, progress)+event(t, result)), "x", 10, func(float64, string) {}); err == nil {
			t.Fatal("invalid performance accepted", invalid)
		}
	}
}
