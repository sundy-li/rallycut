package project

import "testing"

func TestValidateTableSegments(t *testing.T) {
	valid := []TableSegment{
		{Start: 0, End: 30, Bounds: []float64{.1, .3, .9, .5}},
		{Start: 30, End: 60, Bounds: []float64{0, .3, .74, .49}},
		{Start: 60, End: 90},
	}
	if err := ValidateTableSegments(valid, 90); err != nil {
		t.Fatalf("valid segments rejected: %v", err)
	}
	if err := ValidateTableSegments(nil, 90); err != nil {
		t.Fatalf("empty segments rejected: %v", err)
	}
	for name, segments := range map[string][]TableSegment{
		"overlap":  {{Start: 0, End: 10}, {Start: 5, End: 20}},
		"bad box":  {{Start: 0, End: 10, Bounds: []float64{.1, .2, .3}}},
		"outside":  {{Start: 0, End: 99}},
		"negative": {{Start: -1, End: 10}},
	} {
		if err := ValidateTableSegments(segments, 20); err == nil {
			t.Fatalf("%s accepted", name)
		}
	}
}
