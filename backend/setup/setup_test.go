package setup

import (
	"context"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	"rallycut/backend/analysis"
	"rallycut/vision"
)

func TestDefaultWeightsMatchesManifest(t *testing.T) {
	spec, err := defaultWeights()
	if err != nil {
		t.Fatal(err)
	}
	if spec.ID != "blurball-pretrained-v1" || spec.URL == "" || len(spec.SHA256) != 64 || spec.Bytes <= 0 {
		t.Fatalf("unexpected spec: %+v", spec)
	}
}

func TestDownloadVerifiesContent(t *testing.T) {
	payload := []byte("model-bytes")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", strconv.Itoa(len(payload)))
		_, _ = w.Write(payload)
	}))
	defer server.Close()

	dest := filepath.Join(t.TempDir(), "blurball_best.pth")
	var last int64
	if err := download(context.Background(), server.URL, dest, int64(len(payload)), func(written, _ int64) {
		last = written
	}); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(dest)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(payload) || last != int64(len(payload)) {
		t.Fatalf("downloaded %q after %d bytes", got, last)
	}
}

func TestDownloadRejectsHTTPError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "nope", http.StatusNotFound)
	}))
	defer server.Close()
	if err := download(context.Background(), server.URL, filepath.Join(t.TempDir(), "w.pth"), 10, nil); err == nil {
		t.Fatal("expected an error for HTTP 404")
	}
}

// TestProvisionerInstallsRuntime downloads torch and the pinned weights.
// Enable with RALLYCUT_SETUP_E2E=1; it is intentionally slow and networked.
func TestProvisionerInstallsRuntime(t *testing.T) {
	if os.Getenv("RALLYCUT_SETUP_E2E") == "" {
		t.Skip("set RALLYCUT_SETUP_E2E=1 to provision a real runtime")
	}
	dir := t.TempDir()
	t.Setenv("RALLYCUT_DATA_DIR", dir)
	worker, err := vision.Install(filepath.Join(dir, "worker"))
	if err != nil {
		t.Fatal(err)
	}
	provisioner := New(Options{
		DataDir: dir,
		Worker:  worker,
		Log:     slog.Default(),
		Emit:    func(State) {},
	})
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	provisioner.Start(ctx)
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		state := provisioner.Status()
		switch state.State {
		case "ready":
			if !analysis.CheckPython(state.Python) {
				t.Fatal("provisioned python cannot import cv2")
			}
			if ok, detail := analysis.ModelDetail(state.Python, worker); !ok {
				t.Fatalf("provisioned python cannot load weights: %s", detail)
			}
			return
		case "failed", "required":
			t.Fatalf("setup ended in %s: %s", state.State, state.Error)
		}
		select {
		case <-ctx.Done():
			t.Fatalf("setup timed out: %+v", state)
		case <-ticker.C:
		}
	}
}
