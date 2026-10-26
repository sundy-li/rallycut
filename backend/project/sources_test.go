package project

import "testing"

func TestSyncActiveMigratesLegacyProject(t *testing.T) {
	p := &Project{ID: "p1", Video: Video{Name: "a", Duration: 10}, Rallies: []Rally{{ID: "r1", Start: 1, End: 2}}}
	p.SyncActive()
	if len(p.Sources) != 1 || p.ActiveSourceID != "p1" {
		t.Fatalf("legacy project was not migrated: %+v", p.Sources)
	}
	if len(p.Sources[0].Rallies) != 1 || p.Sources[0].Rallies[0].ID != "r1" {
		t.Fatalf("legacy rallies missing from source: %+v", p.Sources[0].Rallies)
	}
}

func TestAddReorderActivate(t *testing.T) {
	p := New(Video{Name: "a", Duration: 10})
	first := p.ID
	second := p.AddSource(Video{Name: "b", Duration: 20})
	if len(p.Sources) != 2 || p.ActiveSourceID != first {
		t.Fatalf("unexpected sources: %d active=%s", len(p.Sources), p.ActiveSourceID)
	}
	if !p.ActivateSource(second) || p.Video.Name != "b" {
		t.Fatalf("activate failed: %s", p.Video.Name)
	}
	p.Rallies = []Rally{{ID: "b1", Start: 1, End: 2}}
	p.SyncActive()
	if len(p.Sources[1].Rallies) != 1 {
		t.Fatalf("active rallies were not synced: %+v", p.Sources[1].Rallies)
	}
	if err := p.ReorderSources([]string{second, first}); err != nil || p.Sources[0].ID != second {
		t.Fatalf("reorder failed: %v", err)
	}
	if err := p.RemoveSource(second); err != nil || len(p.Sources) != 1 || p.ActiveSourceID != first {
		t.Fatalf("remove failed: %v sources=%d", err, len(p.Sources))
	}
	if err := p.RemoveSource(first); err == nil {
		t.Fatal("the last source must not be removable")
	}
}

func TestRemoveSourceDropsItsRallies(t *testing.T) {
	p := New(Video{Name: "a.mp4", Duration: 10})
	second := p.AddSource(Video{Name: "b.mp4", Duration: 20})
	if !p.ActivateSource(second) {
		t.Fatal("activate second source")
	}
	p.Rallies = []Rally{{ID: "b-rally", Start: 1, End: 2, Selected: true}}
	p.SyncActive()
	if len(p.Sources[1].Rallies) != 1 {
		t.Fatalf("second source rallies = %d, want 1", len(p.Sources[1].Rallies))
	}
	if err := p.RemoveSource(second); err != nil {
		t.Fatal(err)
	}
	if len(p.Sources) != 1 || p.Sources[0].Video.Name != "a.mp4" {
		t.Fatalf("sources after remove = %+v", p.Sources)
	}
	if p.ActiveSourceID != p.Sources[0].ID || len(p.Rallies) != 0 {
		t.Fatalf("active source not reset: id=%s rallies=%d", p.ActiveSourceID, len(p.Rallies))
	}
	if len(p.Sources[0].Rallies) != 0 {
		t.Fatalf("removed source rallies leaked into survivor")
	}
}
