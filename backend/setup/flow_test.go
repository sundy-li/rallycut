package setup

import (
	"archive/tar"
	"archive/zip"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func waitEvent(t *testing.T, events <-chan State, wanted string) State {
	t.Helper()
	timer := time.NewTimer(3 * time.Second)
	defer timer.Stop()
	for {
		select {
		case s := <-events:
			if s.State == wanted {
				return s
			}
		case <-timer.C:
			t.Fatalf("never received %s", wanted)
			return State{}
		}
	}
}
func TestInstalledEnvironmentOnlyRequestsMissingModel(t *testing.T) {
	events := make(chan State, 16)
	p := New(Options{DataDir: t.TempDir(), Emit: func(s State) { events <- s }})
	p.inspect = func(context.Context) (string, []CheckItem) {
		return "installed-python", []CheckItem{{ID: "python", Ready: true}, {ID: "media", Ready: true}, {ID: "packages", Ready: true}, {ID: "model", Ready: false}, {ID: "verify", Ready: false}}
	}
	p.Detect(context.Background())
	s := waitEvent(t, events, "required")
	p.Wait()
	if !strings.Contains(s.Message, "约 6 MB") || !runtimeChecksReady(s.Checks) {
		t.Fatalf("misreported installed components: %+v", s)
	}
}
func TestInstalledModelFailureIsNotReportedAsMissingDependencies(t *testing.T) {
	events := make(chan State, 16)
	p := New(Options{DataDir: t.TempDir(), Emit: func(s State) { events <- s }})
	p.inspect = func(context.Context) (string, []CheckItem) {
		return "installed-python", []CheckItem{{ID: "python", Ready: true}, {ID: "media", Ready: true}, {ID: "packages", Ready: true}, {ID: "model", Ready: true}, {ID: "verify", Ready: false, Detail: "illegal instruction"}}
	}
	p.Detect(context.Background())
	s := waitEvent(t, events, "failed")
	p.Wait()
	if s.Step != "verify" || s.Network || s.Error != "illegal instruction" {
		t.Fatalf("lost actual model error: %+v", s)
	}
}

func TestDetectRequiresExplicitConsent(t *testing.T) {
	events := make(chan State, 16)
	p := New(Options{DataDir: t.TempDir(), Emit: func(s State) { events <- s }})
	var installs atomic.Int32
	p.run = func(context.Context) (string, error) { installs.Add(1); return "python", nil }
	p.inspect = func(context.Context) (string, []CheckItem) {
		return "", []CheckItem{{ID: "python", Label: "Python", Ready: false}, {ID: "media", Label: "FFmpeg", Ready: true}}
	}
	p.Detect(context.Background())
	s := waitEvent(t, events, "required")
	p.Wait()
	if installs.Load() != 0 || s.Checks[0].Ready || !s.Checks[1].Ready {
		t.Fatalf("detection installed or hid missing checks: %+v", s)
	}
	if _, err := os.Stat(p.runtimeDir()); !os.IsNotExist(err) {
		t.Fatal("detection wrote runtime before consent")
	}
	p.Start(context.Background())
	waitEvent(t, events, "ready")
	p.Wait()
	if installs.Load() != 1 {
		t.Fatal("explicit click did not install once")
	}
}
func TestDetectAcceptsOnlyFullyReadyRuntime(t *testing.T) {
	events := make(chan State, 16)
	p := New(Options{Emit: func(s State) { events <- s }})
	p.inspect = func(context.Context) (string, []CheckItem) {
		return "existing-python", []CheckItem{{ID: "python", Ready: true}, {ID: "media", Ready: true}, {ID: "model", Ready: true}}
	}
	p.Detect(context.Background())
	s := waitEvent(t, events, "ready")
	p.Wait()
	if s.Python != "existing-python" || s.Progress != 1 || s.Network {
		t.Fatalf("invalid ready state: %+v", s)
	}
	if allReady(nil) {
		t.Fatal("empty checks must fail closed")
	}
}
func TestRepeatedClicksFailureAndRetry(t *testing.T) {
	events := make(chan State, 32)
	p := New(Options{Emit: func(s State) { events <- s }})
	entered := make(chan struct{})
	release := make(chan struct{})
	var runs atomic.Int32
	p.run = func(context.Context) (string, error) {
		if runs.Add(1) == 1 {
			close(entered)
			<-release
			return "", errors.New("network unavailable")
		}
		return "managed-python", nil
	}
	p.Start(context.Background())
	<-entered
	for i := 0; i < 12; i++ {
		p.Start(context.Background())
	}
	close(release)
	failed := waitEvent(t, events, "failed")
	p.Wait()
	if runs.Load() != 1 || failed.Progress >= 1 || failed.Indeterminate || failed.Error == "" {
		t.Fatalf("invalid failure state: %+v", failed)
	}
	p.Start(context.Background())
	ready := waitEvent(t, events, "ready")
	p.Wait()
	if runs.Load() != 2 || ready.Error != "" || ready.Python != "managed-python" {
		t.Fatalf("retry not ready: %+v", ready)
	}
}
func TestStateIsClonedAndProgressIsHonest(t *testing.T) {
	p := New(Options{})
	p.state = State{State: "running", Checks: []CheckItem{{ID: "python", Ready: false}}}
	s := p.Status()
	s.Checks[0].Ready = true
	if p.Status().Checks[0].Ready {
		t.Fatal("caller mutated state checks")
	}
	p.update(.7, "packages", "installing", "")
	p.update(.2, "packages", "working", "")
	if p.Status().Progress != .7 {
		t.Fatal("progress went backwards")
	}
	p.update(2, "verify", "checking", "")
	if p.Status().Progress >= 1 {
		t.Fatal("showed 100% before verification")
	}
}
func TestDownloadDoesNotTrustContentLengthOrLeavePartialOutput(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", "10")
		_, _ = w.Write([]byte("0123456789"))
	}))
	defer server.Close()
	dir := t.TempDir()
	dest := filepath.Join(dir, "runtime")
	if err := download(context.Background(), server.URL, dest, 3, nil); err == nil {
		t.Fatal("accepted more than the pinned size")
	}
	entries, _ := os.ReadDir(dir)
	if len(entries) != 0 {
		t.Fatal("left partial output")
	}
}
func archiveFixture(t *testing.T, format, name string, link bool) string {
	t.Helper()
	var data bytes.Buffer
	if format == "zip" {
		z := zip.NewWriter(&data)
		h := &zip.FileHeader{Name: name, Method: zip.Deflate}
		h.SetMode(0755)
		if link {
			h.SetMode(os.ModeSymlink | 0755)
		}
		w, err := z.CreateHeader(h)
		if err != nil {
			t.Fatal(err)
		}
		w.Write([]byte("tool"))
		z.Close()
	} else {
		g := gzip.NewWriter(&data)
		if format == "tar.gz" {
			w := tar.NewWriter(g)
			kind := byte(tar.TypeReg)
			if link {
				kind = tar.TypeSymlink
			}
			w.WriteHeader(&tar.Header{Name: name, Size: 4, Mode: 0755, Typeflag: kind, Linkname: "/private"})
			if !link {
				w.Write([]byte("tool"))
			}
			w.Close()
		} else {
			g.Write([]byte("tool"))
		}
		g.Close()
	}
	f := filepath.Join(t.TempDir(), "archive")
	if err := os.WriteFile(f, data.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}
	return f
}
func TestExtractsOnlyRequestedRegularExecutable(t *testing.T) {
	for _, format := range []string{"zip", "tar.gz", "gz"} {
		t.Run(format, func(t *testing.T) {
			f := archiveFixture(t, format, "release/uv", false)
			dest := filepath.Join(t.TempDir(), "uv")
			if err := unpackArtifact(context.Background(), f, artifact{Format: format, Entry: "uv"}, dest); err != nil {
				t.Fatal(err)
			}
			b, _ := os.ReadFile(dest)
			if string(b) != "tool" {
				t.Fatal("wrong extracted bytes")
			}
		})
	}
	for _, format := range []string{"zip", "tar.gz"} {
		for _, name := range []string{"../uv", "/uv", "release\\uv", "release/uv"} {
			t.Run(format+name, func(t *testing.T) {
				f := archiveFixture(t, format, name, name == "release/uv")
				dir := t.TempDir()
				if err := unpackArtifact(context.Background(), f, artifact{Format: format, Entry: "uv"}, filepath.Join(dir, "uv")); err == nil {
					t.Fatal("accepted link or traversal")
				}
				entries, _ := os.ReadDir(dir)
				if len(entries) != 0 {
					t.Fatal("published an invalid executable")
				}
			})
		}
	}
}
func TestCachedArtifactMustMatchPinAndInstalledDigest(t *testing.T) {
	p := New(Options{DataDir: t.TempDir()})
	p.state.State = "running"
	f := archiveFixture(t, "gz", "", false)
	data, _ := os.ReadFile(f)
	hash := sha256.Sum256(data)
	digest := hex.EncodeToString(hash[:])
	spec := artifact{URL: "https://github.com/example/releases/download/v1/tool.gz", SHA256: digest, Bytes: int64(len(data)), Format: "gz"}
	cache := filepath.Join(p.runtimeDir(), "downloads", digest)
	os.MkdirAll(filepath.Dir(cache), 0700)
	os.WriteFile(cache, data, 0600)
	dest := filepath.Join(p.runtimeDir(), "bin", "tool")
	if err := p.ensureArtifact(context.Background(), spec, dest, .1, .2, "python", "test"); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(dest, []byte("tampered"), 0600)
	if err := p.ensureArtifact(context.Background(), spec, dest, .1, .2, "python", "test"); err != nil {
		t.Fatal(err)
	}
	got, _ := os.ReadFile(dest)
	if string(got) != "tool" {
		t.Fatal("reused modified executable")
	}
}
func TestPlatformRequirementsMatchAvailableWheels(t *testing.T) {
	for _, tc := range []struct{ goos, arch, torch, numpy string }{{"darwin", "arm64", "2.8.0", "2.2.6"}, {"darwin", "amd64", "2.2.2", "1.26.4"}, {"windows", "amd64", "2.8.0", "2.2.6"}} {
		model, err := platformRequirements("requirements-model.txt", tc.goos, tc.arch)
		if err != nil {
			t.Fatal(err)
		}
		base, err := platformRequirements("requirements.txt", tc.goos, tc.arch)
		if err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(string(model), "torch=="+tc.torch) || !strings.Contains(string(base), "numpy=="+tc.numpy) {
			t.Fatalf("wrong runtime dependencies for %+v", tc)
		}
		if tc.goos == "windows" && !strings.Contains(string(model), "onnxruntime-directml") {
			t.Fatal("Windows dependencies omitted")
		}
	}
}

func TestPlatformArtifactsArePinnedAndIncludeNotices(t *testing.T) {
	c := catalog()
	if c.PythonVersion != "3.12.12" || len(c.Platforms) != 3 {
		t.Fatal("unexpected platform selection")
	}
	for platform, p := range c.Platforms {
		if len(p.Notices) != 2 {
			t.Fatalf("missing license/source notices for %s", platform)
		}
		assets := []artifact{p.UV, p.FFmpeg, p.FFprobe}
		for _, notice := range p.Notices {
			assets = append(assets, notice)
		}
		for _, a := range assets {
			if !strings.HasPrefix(a.URL, "https://github.com/") || strings.Contains(a.URL, "/latest/") || len(a.SHA256) != 64 || a.Bytes <= 0 {
				t.Fatalf("unpinned artifact: %+v", a)
			}
			if _, err := hex.DecodeString(a.SHA256); err != nil {
				t.Fatal(err)
			}
		}
	}
}
