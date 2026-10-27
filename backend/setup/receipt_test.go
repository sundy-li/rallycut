package setup

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"rallycut/backend/storage"
)

func cachedFixture(t *testing.T, events chan State) (*Provisioner, string, *readyReceipt) {
	t.Helper()
	root := t.TempDir()
	p := New(Options{DataDir: t.TempDir(), InstalledRoot: root, Bundle: &BundleSpec{ID: "unit-runtime"}, Emit: func(s State) { events <- s }})
	python := filepath.Join(root, "python/python.exe")
	snapshot := &readyReceipt{Schema: readyReceiptSchema, Identity: "unit-runtime-and-worker", Files: map[string]fileStamp{"python": {Bytes: 123, Modified: 1}}}
	p.snapshot = func(path string) (readyReceipt, error) {
		if path != python {
			t.Fatalf("wrong interpreter: %s", path)
		}
		return *snapshot, nil
	}
	return p, python, snapshot
}
func TestSecondBootNeverStartsHelpersOrEntersCheckingState(t *testing.T) {
	events := make(chan State, 16)
	p, python, _ := cachedFixture(t, events)
	p.saveReadiness(python)
	p.inspect = func(context.Context) (string, []CheckItem) {
		t.Fatal("cached boot launched full probes")
		return "", nil
	}
	p.run = func(context.Context) (string, error) { t.Fatal("cached boot launched installer"); return "", nil }
	p.Boot(context.Background())
	if p.Status().State != "ready" {
		t.Fatalf("cache not accepted: %+v", p.Status())
	}
	select {
	case s := <-events:
		if s.State != "ready" || s.Python != python {
			t.Fatalf("setup UI would flash: %+v", s)
		}
	default:
		t.Fatal("ready not published")
	}
	if len(events) != 0 {
		t.Fatal("cached boot emitted extra setup events")
	}
}
func TestChangedReceiptFallsBackToFullDetection(t *testing.T) {
	for _, change := range []string{"identity", "size", "mtime", "missing", "corrupt", "snapshot-error"} {
		t.Run(change, func(t *testing.T) {
			events := make(chan State, 16)
			p, python, snapshot := cachedFixture(t, events)
			p.saveReadiness(python)
			switch change {
			case "identity":
				snapshot.Identity = "different-model-or-runtime"
			case "size":
				snapshot.Files = map[string]fileStamp{"python": {Bytes: 124, Modified: 1}}
			case "mtime":
				snapshot.Files = map[string]fileStamp{"python": {Bytes: 123, Modified: 2}}
			case "missing":
				os.Remove(p.receiptPath())
			case "corrupt":
				os.WriteFile(p.receiptPath(), []byte("broken json"), 0600)
			case "snapshot-error":
				p.snapshot = func(string) (readyReceipt, error) { return readyReceipt{}, errors.New("runtime file missing") }
			}
			called := false
			p.inspect = func(context.Context) (string, []CheckItem) {
				called = true
				return "", []CheckItem{{ID: "python", Ready: false}}
			}
			p.Boot(context.Background())
			s := waitEvent(t, events, "required")
			p.Wait()
			if !called || s.State == "ready" {
				t.Fatal("changed environment incorrectly skipped validation")
			}
			if _, err := os.Stat(p.receiptPath()); !os.IsNotExist(err) {
				t.Fatal("stale receipt was not invalidated")
			}
		})
	}
}
func TestExplicitRecheckIgnoresSuccessfulCache(t *testing.T) {
	events := make(chan State, 16)
	p, python, _ := cachedFixture(t, events)
	p.saveReadiness(python)
	p.inspect = func(context.Context) (string, []CheckItem) {
		return "", []CheckItem{{ID: "verify", Ready: false, Detail: "forward failed"}}
	}
	p.Detect(context.Background())
	waitEvent(t, events, "required")
	p.Wait()
	if _, err := os.Stat(p.receiptPath()); !os.IsNotExist(err) {
		t.Fatal("failed recheck left cached success")
	}
}
func TestSuccessOnlyWritesReceiptAfterVerifiedRun(t *testing.T) {
	events := make(chan State, 16)
	p, python, _ := cachedFixture(t, events)
	p.run = func(context.Context) (string, error) { return "", errors.New("forward failed") }
	p.Start(context.Background())
	waitEvent(t, events, "failed")
	p.Wait()
	if _, err := os.Stat(p.receiptPath()); !os.IsNotExist(err) {
		t.Fatal("cached a failed setup")
	}
	p.run = func(context.Context) (string, error) { return python, nil }
	p.Start(context.Background())
	waitEvent(t, events, "ready")
	p.Wait()
	var receipt readyReceipt
	if err := storage.ReadJSON(p.receiptPath(), &receipt); err != nil {
		t.Fatal(err)
	}
	if receipt.Identity == "" {
		t.Fatal("missing successful runtime identity")
	}
}
func TestLightweightSnapshotTracksPinnedExecutableChanges(t *testing.T) {
	archive, spec := bundleFixture(t)
	root := t.TempDir()
	if err := extractBundle(context.Background(), archive, root, spec); err != nil {
		t.Fatal(err)
	}
	p := New(Options{DataDir: t.TempDir(), InstalledRoot: root, Bundle: &spec})
	// This fixture deliberately has no valid real model; a receipt must not be
	// generated from executable presence alone.
	if _, err := p.readinessSnapshot(filepath.Join(root, "python/python.exe")); err == nil {
		t.Fatal("accepted missing model")
	}
	var manifest bundleManifest
	data, _ := os.ReadFile(filepath.Join(root, "bundle-manifest.json"))
	json.Unmarshal(data, &manifest)
	if len(manifest.Files) != 3 {
		t.Fatal("bad fixture")
	}
}
