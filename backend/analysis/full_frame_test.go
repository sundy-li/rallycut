package analysis

import (
	"rallycut/backend/project"
	"strings"
	"testing"
)

func noTableResult() *Result {
	return &Result{ProtocolVersion: 1, Model: Model,
		Rallies: []project.Rally{{ID: "unit", Start: .1, End: 2, Confidence: .8, Score: 70, Selected: true}},
		Tracks:  []project.BallTrack{{ID: "track", Points: []project.TrackPoint{{T: .1, X: .9, Y: .85, Confidence: .9}, {T: .2, X: .88, Y: .85, Confidence: .9}, {T: .3, X: .86, Y: .85, Confidence: .9}}}},
		Summary: &project.AnalysisSummary{Method: Model, WeightsSHA256: WeightsSHA256, DecodedFrames: 48, SampledFrames: 48, TrackCount: 1, ElapsedSeconds: 1, TableMode: "off", TableBounds: []float64{}, TableSegments: []project.TableSegment{{Start: 0, End: 5, Bounds: []float64{}, Method: "unavailable"}}}}
}

func TestNoTableResultsAreLegalButMalformedGeometryIsNot(t *testing.T) {
	for _, bounds := range [][]float64{nil, {}} {
		r := noTableResult()
		r.Summary.TableBounds = bounds
		if err := Validate(r, 5); err != nil {
			t.Fatal("legal full-frame result rejected", err)
		}
		line := event(t, Event{ProtocolVersion: 1, JobID: "x", Type: "result", Result: r})
		if _, err := Parse(strings.NewReader(line), "x", 5, func(float64, string) {}); err != nil {
			t.Fatal(err)
		}
	}
	for _, bounds := range [][]float64{{0, 0, 1}, {.8, .4, .2, .6}, {0, 0, 2, 1}} {
		r := noTableResult()
		r.Summary.TableBounds = bounds
		if err := Validate(r, 5); err == nil {
			t.Fatal("invalid geometry accepted", bounds)
		}
	}
}

func TestEmptyGeometryUpdateReachesUIWithoutNeedingAnyTracks(t *testing.T) {
	line := event(t, Event{ProtocolVersion: 1, JobID: "x", Type: "candidates", TableBounds: []float64{}, ProcessedSeconds: 2})
	line += event(t, Event{ProtocolVersion: 1, JobID: "x", Type: "result", Result: noTableResult()})
	calls := 0
	_, err := parseObserved(strings.NewReader(line), "x", 5, func(float64, string) {}, nil, func(s Stream) {
		calls++
		if s.TableBounds == nil || len(s.TableBounds) != 0 {
			t.Fatal("empty clear lost", s)
		}
	})
	if err != nil || calls != 1 {
		t.Fatal(err, calls)
	}
}
