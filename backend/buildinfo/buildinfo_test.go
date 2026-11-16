package buildinfo

import "testing"

func TestGetUsesLinkTimeValues(t *testing.T) {
	saved := [4]string{Version, Commit, Dirty, BuildTime}
	t.Cleanup(func() { Version, Commit, Dirty, BuildTime = saved[0], saved[1], saved[2], saved[3] })

	Version, Commit, Dirty, BuildTime = "v0.1.0-alpha.4", "8bb27b772238399ca61db80e", "true", "2026-11-16T04:30:00Z"
	got := Get()
	if got.Version != "0.1.0-alpha.4" || got.Commit != "8bb27b772238" || !got.Dirty || got.BuildTime != "2026-11-16T04:30:00Z" {
		t.Fatalf("%+v", got)
	}

	Version, Commit, Dirty, BuildTime = "", "", "", ""
	if got := Get(); got.Version != "dev" {
		t.Fatalf("unstamped build must say dev, got %+v", got)
	}
}
