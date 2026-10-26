package storage

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestOversizedAnnotationProjectNeverReplacesReadableFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "project.json")
	if err := WriteJSON(path, map[string]string{"note": "saved"}); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(path)
	if err := WriteJSON(path, map[string]string{"note": strings.Repeat("x", 32<<20)}); err == nil {
		t.Fatal("unreadable oversized JSON published")
	}
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("prior project changed on failure")
	}
}
