package setup

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"rallycut/backend/runtimeenv"
	"rallycut/vision"
)

// Uses the actual NSIS-expanded directory on the Windows runner, not the ZIP
// and not a developer Python. This is a runtime test, not a native GUI test.
func TestInstalledRuntimeFirstUse(t *testing.T) {
	root := os.Getenv("RALLYCUT_INSTALLED_ROOT")
	if root == "" {
		t.Skip("requires an installed Windows preview")
	}
	dir := t.TempDir()
	t.Setenv("RALLYCUT_DATA_DIR", dir)
	worker, err := vision.Install(filepath.Join(dir, "worker"))
	if err != nil {
		t.Fatal(err)
	}
	events := make(chan State, 32)
	p := New(Options{DataDir: dir, Worker: worker, InstalledRoot: root, Emit: func(s State) {
		select {
		case events <- s:
		default:
		}
	}})
	spec := p.bundleSpec()
	if spec == nil {
		t.Fatal("missing embedded release pin")
	}
	if runtimeenv.BundledID() != spec.ID {
		t.Fatal("application installer identity does not match environment pin")
	}
	exe := filepath.Join(filepath.Dir(filepath.Dir(root)), "RallyCut.exe")
	if runtimeenv.InstalledAt(exe, spec.ID) != root {
		t.Fatal("application cannot locate this installed payload")
	}
	t.Setenv("PATH", "")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	p.Detect(ctx)
	var before State
	for {
		select {
		case state := <-events:
			if state.State != "checking" {
				before = state
			}
		case <-ctx.Done():
			t.Fatal(ctx.Err())
		}
		if before.State != "" {
			break
		}
	}
	p.Wait()
	if before.RuntimeMode != "installed" || before.State != "required" || !runtimeChecksReady(before.Checks) || checkReady(before.Checks, "model") {
		t.Fatalf("installer dependencies incorrectly shown as missing: %+v", before)
	}
	if _, err := os.Stat(p.runtimeDir()); !os.IsNotExist(err) {
		t.Fatal("local detection wrote a second environment")
	}
	p.Start(ctx)
	var prepared State
	for prepared.State != "ready" {
		select {
		case state := <-events:
			prepared = state
			if state.State == "failed" {
				t.Fatal(state.Error)
			}
		case <-ctx.Done():
			t.Fatal(ctx.Err())
		}
	}
	p.Wait()
	python := prepared.Python
	if python != filepath.Join(root, "python", "python.exe") {
		t.Fatal("recreated environment rather than using installed Python")
	}
	// Real restart: a new provisioner reads the on-disk success receipt. A
	// cache hit must not emit checking or execute even one external probe.
	var restartEvents []State
	restarted := New(Options{DataDir: dir, Worker: worker, InstalledRoot: root, Emit: func(s State) { restartEvents = append(restartEvents, s) }})
	restarted.inspect = func(context.Context) (string, []CheckItem) { t.Fatal("second launch ran full probes"); return "", nil }
	restarted.run = func(context.Context) (string, error) { t.Fatal("second launch ran setup"); return "", nil }
	start := time.Now()
	restarted.Boot(ctx)
	elapsed := time.Since(start)
	if restarted.Status().State != "ready" || len(restartEvents) != 1 || restartEvents[0].State != "ready" {
		t.Fatalf("second launch did not skip setup: %+v", restartEvents)
	}
	if elapsed > 3*time.Second {
		t.Fatalf("cached restart too slow: %s", elapsed)
	}
	t.Logf("PASS: second launch ready in %s without Python/FFmpeg commands or checking events", elapsed)
	if _, err := os.Stat(p.runtimeDir()); !os.IsNotExist(err) {
		t.Fatal("model setup duplicated the installed environment")
	}
	t.Log("PASS: real installer payload ready before consent; only model is prepared; no per-user environment extraction")
}
