package runtimeenv

import (
	"os"
	"path/filepath"
	"testing"
)

func TestInstalledLayoutIsPinnedToExecutableAndVersion(t *testing.T) {
	base := t.TempDir()
	exe := filepath.Join(base, "RallyCut.exe")
	id := "windows-x64-preview-3"
	root := filepath.Join(base, "runtimes", id)
	os.MkdirAll(root, 0700)
	os.WriteFile(filepath.Join(root, "bundle-manifest.json"), []byte("{}"), 0600)
	if got := InstalledAt(exe, id); got != root {
		t.Fatalf("wrong installed path: %s", got)
	}
	for _, bad := range []string{"", "..", "../elsewhere", "another-version"} {
		if InstalledAt(exe, bad) != "" {
			t.Fatalf("accepted unpinned runtime: %s", bad)
		}
	}
}
