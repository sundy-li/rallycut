package storage

import (
	"os"
	"path/filepath"
	"rallycut/backend/project"
	"testing"
)

func TestRoundTripManualEditsAndRecovery(t *testing.T) {
	path := filepath.Join(t.TempDir(), "project.json")
	p := project.New(project.Video{Path: "/tmp/source.mp4", Duration: 60})
	p.RawRallies = []project.Rally{{ID: "a", Start: 1, End: 8}}
	p.Rallies = []project.Rally{{ID: "a", Start: 2, End: 7, Edited: true, Selected: true}}
	p.ManualTimeline = true
	p.Job = &project.Job{ID: "j", Status: "running"}
	if err := WriteJSON(path, p); err != nil {
		t.Fatal(err)
	}
	loaded, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.Rallies[0].Start != 2 || loaded.RawRallies[0].Start != 1 || loaded.Job.Status != "interrupted" || !loaded.ManualTimeline {
		t.Fatal(loaded)
	}
	info, _ := os.Stat(path)
	if info.Mode().Perm() != 0600 {
		t.Fatal("unsafe permissions")
	}
}
func TestRejectFutureSchemaAndTrailingData(t *testing.T) {
	path := filepath.Join(t.TempDir(), "p.json")
	p := project.New(project.Video{Path: "x", Duration: 2})
	p.SchemaVersion = 99
	if err := WriteJSON(path, p); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(path); err == nil {
		t.Fatal("future schema accepted")
	}
	if err := os.WriteFile(path, []byte("{} {}"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := ReadJSON(path, &p); err == nil {
		t.Fatal("trailing data accepted")
	}
}
