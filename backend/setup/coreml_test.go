package setup

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"rallycut/backend/analysis"
	"rallycut/vision"
)

// TestCoreMLConversionWithRealRuntime converts the pinned weights with a real
// Python that has torch + coremltools, then checks the readiness probe.
// Enable with RALLYCUT_COREML_E2E=<python> and RALLYCUT_COREML_WEIGHTS=<pth>.
func TestCoreMLConversionWithRealRuntime(t *testing.T) {
	python, weights := os.Getenv("RALLYCUT_COREML_E2E"), os.Getenv("RALLYCUT_COREML_WEIGHTS")
	if python == "" || weights == "" || !analysis.CoreMLSupported() {
		t.Skip("set RALLYCUT_COREML_E2E=<python> and RALLYCUT_COREML_WEIGHTS=<blurball_best.pth> on Apple silicon")
	}
	dir := t.TempDir()
	t.Setenv("RALLYCUT_DATA_DIR", dir)
	worker, err := vision.Install(filepath.Join(dir, "worker"))
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(weights)
	if err != nil {
		t.Fatal(err)
	}
	p := New(Options{DataDir: dir, Worker: worker})
	if err := os.MkdirAll(filepath.Dir(p.weightsPath()), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p.weightsPath(), data, 0600); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	if got := analysis.CoreMLStatus(ctx, python, worker, dir); got != "missing" {
		t.Fatalf("fresh data dir status %q", got)
	}
	before := analysis.BackendIdentity(dir)
	start := time.Now()
	p.ensureCoreML(ctx, python, "")
	t.Logf("conversion took %s", time.Since(start).Round(time.Second))
	if got := analysis.CoreMLStatus(ctx, python, worker, dir); got != "ready" {
		t.Fatalf("after conversion status %q", got)
	}
	if analysis.BackendIdentity(dir) == before {
		t.Fatal("cache identity must change once the Core ML package exists")
	}
	if ok, detail := analysis.CoreMLToolsDetail(python); !ok {
		t.Fatal(detail)
	}
}
