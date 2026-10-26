package backend

import (
	"testing"

	"rallycut/backend/project"
	"rallycut/backend/storage"
)

func historyTestApp(t *testing.T) (*App, string) {
	t.Helper()
	p := project.New(project.Video{Path: "source.mp4", Name: "source.mp4", Duration: 30})
	p.Rallies = []project.Rally{{ID: "a", Start: 1, End: 5, Selected: true}}
	p.SyncActive()
	return newTestApp(t, p)
}

func TestUndoRedoRestoresAndSavesTimeline(t *testing.T) {
	a, path := historyTestApp(t)
	if a.GetState().CanUndo {
		t.Fatal("fresh project must not be undoable")
	}
	rules := a.current.Rules
	edited := []project.Rally{{ID: "a", Start: 1, End: 7, Selected: true}}
	if _, err := a.UpdateTimeline(edited, rules); err != nil {
		t.Fatal(err)
	}
	if _, err := a.SplitRally("a", 4); err != nil {
		t.Fatal(err)
	}
	state := a.GetState()
	if !state.CanUndo || state.CanRedo {
		t.Fatalf("flags after edits: undo=%v redo=%v", state.CanUndo, state.CanRedo)
	}

	got, err := a.Undo()
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Rallies) != 1 || got.Rallies[0].End != 7 {
		t.Fatalf("undo split: %+v", got.Rallies)
	}
	saved, err := storage.Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(saved.Rallies) != 1 || saved.Rallies[0].End != 7 {
		t.Fatalf("undo must be saved immediately: %+v", saved.Rallies)
	}

	got, err = a.Undo()
	if err != nil {
		t.Fatal(err)
	}
	if got.Rallies[0].End != 5 || got.ManualTimeline {
		t.Fatalf("undo first edit must restore machine timeline: %+v manual=%v", got.Rallies, got.ManualTimeline)
	}
	if _, err := a.Undo(); err == nil {
		t.Fatal("undo beyond history must fail")
	}

	got, err = a.Redo()
	if err != nil {
		t.Fatal(err)
	}
	if got.Rallies[0].End != 7 || !got.ManualTimeline {
		t.Fatalf("redo: %+v", got.Rallies)
	}
	// A new edit after undo discards the redo branch.
	if _, err := a.UpdateTimeline([]project.Rally{{ID: "a", Start: 2, End: 7, Selected: true}}, rules); err != nil {
		t.Fatal(err)
	}
	if a.GetState().CanRedo {
		t.Fatal("new edit must clear redo")
	}
}

func TestHistoryIgnoresNoOpsAndClearsOnSourceSwitch(t *testing.T) {
	a, _ := historyTestApp(t)
	if _, err := a.UpdateTimeline(a.current.Rallies, a.current.Rules); err != nil {
		t.Fatal(err)
	}
	if a.GetState().CanUndo {
		t.Fatal("unchanged timeline must not create an undo step")
	}
	if _, err := a.UpdateTimeline([]project.Rally{{ID: "a", Start: 1, End: 8, Selected: true}}, a.current.Rules); err != nil {
		t.Fatal(err)
	}
	if _, err := a.SetExportSettings(project.ExportSettings{Codec: "h264", Encoder: "auto"}); err != nil {
		t.Fatal(err)
	}
	if !a.GetState().CanUndo {
		t.Fatal("export settings must not drop cutting history")
	}
	a.mu.Lock()
	second := a.current.AddSource(project.Video{Path: "second.mp4", Name: "second.mp4", Duration: 20})
	a.mu.Unlock()
	if _, err := a.SelectSource(second); err != nil {
		t.Fatal(err)
	}
	if a.GetState().CanUndo {
		t.Fatal("switching source must clear history of the previous timeline")
	}
}
