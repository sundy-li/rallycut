package backend

import (
	"context"
	setupenv "rallycut/backend/setup"
	"testing"
)

func TestFirstRunBackendCannotBypassPreparation(t *testing.T) {
	a := &App{ctx: context.Background(), dataDir: t.TempDir(), worker: "test-worker"}
	if a.ready() == nil {
		t.Fatal("nil setup bypassed the runtime gate")
	}
	if a.GetState().Setup.State != "failed" || a.StartSetup().State != "failed" || a.SetupStatus().State != "failed" {
		t.Fatal("missing setup silently reported ready")
	}
	a.setup = setupenv.New(setupenv.Options{DataDir: a.dataDir})
	if a.ready() == nil {
		t.Fatal("checking state bypassed the gate")
	}
	a.setup.MarkRequired()
	if _, err := a.CreateProject("should-not-open-a-dialog"); err == nil {
		t.Fatal("create project bypassed the gate")
	}
	if _, err := a.ImportVideo(); err == nil {
		t.Fatal("import bypassed the gate")
	}
	a.setup.MarkReady("fixture-python")
	if err := a.ready(); err != nil {
		t.Fatalf("verified runtime still blocked: %v", err)
	}
}
