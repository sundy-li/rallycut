package setup

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func fastDownloads(t *testing.T) {
	t.Helper()
	rounds, base, stall := downloadRounds, downloadBackoffBase, downloadStallTimeout
	downloadBackoffBase, downloadStallTimeout = time.Millisecond, 200*time.Millisecond
	t.Cleanup(func() { downloadRounds, downloadBackoffBase, downloadStallTimeout = rounds, base, stall })
}

func TestDownloadFromSourcesFailsOverAndResumesAcrossSources(t *testing.T) {
	fastDownloads(t)
	data := []byte("0123456789abcdef")
	// The first source drops the connection after 6 bytes; the mirror then
	// must be asked only for the remainder.
	broken := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", "16")
		w.Write(data[:6])
		w.(http.Flusher).Flush()
		panic(http.ErrAbortHandler)
	}))
	defer broken.Close()
	var ranges []string
	mirror := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ranges = append(ranges, r.Header.Get("Range"))
		w.Header().Set("Content-Range", "bytes 6-15/16")
		w.WriteHeader(http.StatusPartialContent)
		w.Write(data[6:])
	}))
	defer mirror.Close()
	dest := filepath.Join(t.TempDir(), "w")
	if err := downloadFromSources(context.Background(), newDownloadClient(), []string{broken.URL, mirror.URL}, dest, 16, hashBytes(data), nil); err != nil {
		t.Fatal(err)
	}
	if got, _ := os.ReadFile(dest); string(got) != string(data) {
		t.Fatalf("got %q", got)
	}
	if len(ranges) != 1 || ranges[0] != "bytes=6-" {
		t.Fatalf("mirror ranges %v", ranges)
	}
}

func TestDownloadFromSourcesDropsWrongContentAndPermanentErrors(t *testing.T) {
	fastDownloads(t)
	data := []byte("pinned-bytes")
	var wrongHits, goneHits atomic.Int32
	wrong := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		wrongHits.Add(1)
		w.Write([]byte("other-bytes!"))
	}))
	defer wrong.Close()
	gone := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		goneHits.Add(1)
		http.NotFound(w, r)
	}))
	defer gone.Close()
	var flakyHits atomic.Int32
	flaky := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if flakyHits.Add(1) < 3 {
			http.Error(w, "busy", http.StatusServiceUnavailable)
			return
		}
		w.Write(data)
	}))
	defer flaky.Close()
	dest := filepath.Join(t.TempDir(), "w")
	sources := []string{wrong.URL, gone.URL, flaky.URL}
	if err := downloadFromSources(context.Background(), newDownloadClient(), sources, dest, int64(len(data)), hashBytes(data), nil); err != nil {
		t.Fatal(err)
	}
	if wrongHits.Load() != 1 || goneHits.Load() != 1 || flakyHits.Load() != 3 {
		t.Fatalf("hits wrong=%d gone=%d flaky=%d", wrongHits.Load(), goneHits.Load(), flakyHits.Load())
	}
}

func TestDownloadFromSourcesStallSwitchesSourceAndReportsHosts(t *testing.T) {
	fastDownloads(t)
	downloadRounds = 2
	release := make(chan struct{})
	defer close(release)
	stalled := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", "10")
		w.Write([]byte("01"))
		w.(http.Flusher).Flush()
		select {
		case <-release:
		case <-r.Context().Done():
		}
	}))
	defer stalled.Close()
	start := time.Now()
	dest := filepath.Join(t.TempDir(), "w")
	err := downloadFromSources(context.Background(), newDownloadClient(), []string{stalled.URL, "http://127.0.0.1:1/unreachable"}, dest, 10, hashBytes([]byte("0123456789")), nil)
	if err == nil {
		t.Fatal("expected failure")
	}
	if time.Since(start) > 5*time.Second {
		t.Fatalf("stall was not cut off: %s", time.Since(start))
	}
	msg := err.Error()
	if !strings.Contains(msg, strings.TrimPrefix(stalled.URL, "http://")) || !strings.Contains(msg, "127.0.0.1:1") || !strings.Contains(msg, "没有收到数据") {
		t.Fatalf("unclear error: %s", msg)
	}
	if info, statErr := os.Stat(dest + ".part"); statErr != nil || info.Size() == 0 {
		t.Fatal("progress from the stalled source should be kept for resume")
	}
}

func TestWeightsSourcesOrderAndValidation(t *testing.T) {
	spec := weightsSpec{URL: "https://official/w", Mirrors: []string{"https://mirror/w", "https://official/w"}}
	t.Setenv(modelMirrorsEnv, " https://mine/w ,https://mine/w\nhttp://lan/w")
	got, err := spec.sources()
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"https://mine/w", "http://lan/w", "https://mirror/w", "https://official/w"}
	if strings.Join(got, " ") != strings.Join(want, " ") {
		t.Fatalf("sources %v", got)
	}
	t.Setenv(modelMirrorsEnv, "file:///etc/passwd")
	if _, err := spec.sources(); err == nil {
		t.Fatal("accepted a non-HTTP source")
	}
}

func TestDownloadFromSourcesRejectsAcceleratorErrorPagesWithoutLosingProgress(t *testing.T) {
	fastDownloads(t)
	data := []byte("0123456789")
	var htmlHits atomic.Int32
	html := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		htmlHits.Add(1)
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write([]byte("<html>rate limited</html>"))
	}))
	defer html.Close()
	good := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Range") != "bytes=4-" {
			t.Errorf("progress lost: range %q", r.Header.Get("Range"))
		}
		w.Header().Set("Content-Range", "bytes 4-9/10")
		w.WriteHeader(http.StatusPartialContent)
		w.Write(data[4:])
	}))
	defer good.Close()
	dest := filepath.Join(t.TempDir(), "w")
	os.WriteFile(dest+".part", data[:4], 0600)
	if err := downloadFromSources(context.Background(), newDownloadClient(), []string{html.URL, good.URL}, dest, 10, hashBytes(data), nil); err != nil {
		t.Fatal(err)
	}
	if htmlHits.Load() != 1 {
		t.Fatalf("error page source retried %d times", htmlHits.Load())
	}
}

// TestRealWeightSources probes every manifest source individually so dead
// accelerators are noticed. Network-dependent; opt in explicitly.
func TestRealWeightSources(t *testing.T) {
	if os.Getenv("RALLYCUT_MODEL_SOURCES_E2E") != "1" {
		t.Skip("set RALLYCUT_MODEL_SOURCES_E2E=1 to probe real model sources")
	}
	spec, err := defaultWeights()
	if err != nil {
		t.Fatal(err)
	}
	sources, err := spec.sources()
	if err != nil {
		t.Fatal(err)
	}
	downloadRounds = 1
	t.Cleanup(func() { downloadRounds = 4 })
	ok := 0
	for _, source := range sources {
		dest := filepath.Join(t.TempDir(), "w")
		start := time.Now()
		err := downloadFromSources(context.Background(), newDownloadClient(), []string{source}, dest, spec.Bytes, spec.SHA256, nil)
		if err == nil {
			ok++
		}
		t.Logf("%-6v %5.1fs %s %v", err == nil, time.Since(start).Seconds(), source, err)
	}
	if ok == 0 {
		t.Fatal("no model source works")
	}
}
