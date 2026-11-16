package analysis

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCacheKeyIsStableAndSourceSpecific(t *testing.T) {
	if CacheKey("a", "x") != CacheKey("a", "x") || CacheKey("a", "x") == CacheKey("b", "x") || CacheKey("a", "x") == CacheKey("a", "y") {
		t.Fatal("cache key must be stable and per-source")
	}
}

func TestBackendIdentityTracksCoreMLSidecar(t *testing.T) {
	dir := t.TempDir()
	before := BackendIdentity(dir)
	derived := filepath.Join(dir, "models", "derived")
	if err := os.MkdirAll(derived, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(derived, "BlurBall.mlpackage.json"), []byte(`{"converter":"a"}`), 0600); err != nil {
		t.Fatal(err)
	}
	with := BackendIdentity(dir)
	os.WriteFile(filepath.Join(derived, "BlurBall.mlpackage.json"), []byte(`{"converter":"b"}`), 0600)
	if before == with || with == BackendIdentity(dir) {
		t.Fatal("cache identity must change with the Core ML package")
	}
	t.Setenv("RALLYCUT_RUNTIME", "torch")
	if BackendIdentity(dir) == with {
		t.Fatal("runtime override must change the identity")
	}
}
