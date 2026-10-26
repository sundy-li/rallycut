package project

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestOffPlayTrackFlagRoundTripsAndIsOptional(t *testing.T) {
	var tracks []BallTrack
	raw := `[{"id":"1","points":[]},{"id":"2","points":[],"off_play":true}]`
	if err := json.Unmarshal([]byte(raw), &tracks); err != nil {
		t.Fatal(err)
	}
	if tracks[0].OffPlay || !tracks[1].OffPlay {
		t.Fatalf("flags = %v %v", tracks[0].OffPlay, tracks[1].OffPlay)
	}
	cloned := CloneTracks(tracks)
	if !cloned[1].OffPlay {
		t.Fatal("clone dropped off_play")
	}
	out, err := json.Marshal(cloned)
	if err != nil {
		t.Fatal(err)
	}
	// Old projects / unmarked tracks stay byte-compatible: no false field.
	if strings.Count(string(out), "off_play") != 1 {
		t.Fatalf("encoded %s", out)
	}
}
