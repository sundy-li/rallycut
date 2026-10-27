package media

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestManagedToolsResolveWithoutGlobalPATHChanges(t *testing.T) {
	data := t.TempDir()
	name := "ffmpeg"
	if runtime.GOOS == "windows" {
		name += ".exe"
	}
	bin := filepath.Join(data, "runtime", "bin", name)
	os.MkdirAll(filepath.Dir(bin), 0700)
	os.WriteFile(bin, []byte("fixture"), 0755)
	t.Setenv("RALLYCUT_FFMPEG", "")
	before := os.Getenv("PATH")
	if BinaryFor(data, "ffmpeg") != bin {
		t.Fatal("managed media tool was not selected")
	}
	if os.Getenv("PATH") != before {
		t.Fatal("modified global PATH")
	}
	t.Setenv("RALLYCUT_FFMPEG", "explicit-tool")
	if BinaryFor(data, "ffmpeg") != "explicit-tool" {
		t.Fatal("overrode explicit user configuration")
	}
}
