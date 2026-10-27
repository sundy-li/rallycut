package childproc

import (
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

func TestBackendHelpersAlwaysUseQuietLauncher(t *testing.T) {
	direct := regexp.MustCompile(`\bexec\.Command(?:Context)?\(`)
	err := filepath.WalkDir("..", func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			return nil
		}
		normalized := filepath.ToSlash(path)
		if !strings.HasSuffix(path, ".go") || strings.HasSuffix(path, "_test.go") || strings.Contains(normalized, "/childproc/") {
			return nil
		}
		// Explorer/Finder is a user-requested GUI, not an internal console helper.
		if normalized == "../media/reveal.go" {
			return nil
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		if direct.Match(data) {
			t.Errorf("raw console-capable command in %s; use backend/childproc", path)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}
