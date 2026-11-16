package setup

import (
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestImportWeightsFileVerifiesPinnedContent(t *testing.T) {
	payload := []byte("pinned-model-bytes")
	sum := sha256.Sum256(payload)
	spec := weightsSpec{SHA256: hex.EncodeToString(sum[:]), Bytes: int64(len(payload))}
	dir := t.TempDir()
	dest := filepath.Join(dir, "models", "weights", "blurball_best.pth")

	write := func(name string, data []byte) string {
		path := filepath.Join(dir, name)
		if err := os.WriteFile(path, data, 0600); err != nil {
			t.Fatal(err)
		}
		return path
	}
	wrongSize := write("short", payload[:4])
	wrongHash := write("tampered", []byte(strings.Repeat("x", len(payload))))
	for _, src := range []string{wrongSize, wrongHash, filepath.Join(dir, "missing"), dir} {
		if err := importWeightsFile(src, dest, spec); err == nil {
			t.Fatalf("accepted %s", src)
		}
		if _, err := os.Stat(dest); !os.IsNotExist(err) {
			t.Fatalf("installed an unverified file from %s", src)
		}
	}

	good := write("blurball_best", payload)
	if err := importWeightsFile(good, dest, spec); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(dest)
	if err != nil || string(got) != string(payload) {
		t.Fatalf("installed %q, %v", got, err)
	}
	if _, err := os.Stat(good); err != nil {
		t.Fatal("import must not move the user's source file")
	}
	// Re-importing the installed file itself is a no-op, not a self-truncation.
	if err := importWeightsFile(dest, dest, spec); err != nil {
		t.Fatal(err)
	}
	if got, _ := os.ReadFile(dest); string(got) != string(payload) {
		t.Fatal("self-import damaged the installed weights")
	}
	leftovers, _ := filepath.Glob(filepath.Join(filepath.Dir(dest), ".import-*"))
	if len(leftovers) != 0 {
		t.Fatalf("left temp files: %v", leftovers)
	}
}

func TestImportWeightsRejectsWhileRunning(t *testing.T) {
	p := New(Options{DataDir: t.TempDir()})
	p.running = true
	if err := p.ImportWeights(filepath.Join(t.TempDir(), "w")); err == nil {
		t.Fatal("import must not race a running setup")
	}
}
