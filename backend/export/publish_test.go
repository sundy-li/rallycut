package export

import (
	"os"
	"path/filepath"
	"testing"
)

func TestPublishCompletedNeverReplacesExistingOutput(t *testing.T) {
	dir := t.TempDir()
	source := filepath.Join(dir, "ready.mp4")
	dest := filepath.Join(dir, "原片 #1.mp4")
	os.WriteFile(source, []byte("new"), 0600)
	os.WriteFile(dest, []byte("original"), 0600)
	if err := publishCompleted(source, dest); err == nil {
		t.Fatal("replaced existing output")
	}
	got, _ := os.ReadFile(dest)
	if string(got) != "original" {
		t.Fatal("original was changed")
	}
	os.Remove(dest)
	if err := publishCompleted(source, dest); err != nil {
		t.Fatal(err)
	}
	got, _ = os.ReadFile(dest)
	if string(got) != "new" {
		t.Fatal("incorrect published output")
	}
}

func TestReplaceCompletedSwapsExistingOutput(t *testing.T) {
	dir := t.TempDir()
	source := filepath.Join(dir, "ready.mp4")
	dest := filepath.Join(dir, "集锦 #1.mp4")
	os.WriteFile(source, []byte("new"), 0600)
	os.WriteFile(dest, []byte("old"), 0600)
	if err := replaceCompleted(source, dest); err != nil {
		t.Fatal(err)
	}
	if got, _ := os.ReadFile(dest); string(got) != "new" {
		t.Fatalf("got %q", got)
	}
	if _, err := os.Stat(source); !os.IsNotExist(err) {
		t.Fatal("temporary file left behind")
	}
}
