package media

import (
	"context"
	"path/filepath"
	"runtime"
	"testing"
)

func TestRevealCommandSelectsFileWithoutShell(t *testing.T) {
	path := "/tmp/a b; rm -rf x/RallyCut-highlights.mp4"
	name, args := RevealCommand(path)
	if runtime.GOOS == "darwin" && (name != "open" || len(args) != 2 || args[0] != "-R" || args[1] != path) {
		t.Fatal(name, args)
	}
}

func TestRevealRejectsMissingRelativeAndDirectory(t *testing.T) {
	dir := t.TempDir()
	for _, path := range []string{"relative.mp4", filepath.Join(dir, "missing.mp4"), dir} {
		if err := Reveal(context.Background(), path); err == nil {
			t.Fatal("expected error for", path)
		}
	}
}
