package setup

import (
	"archive/zip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"rallycut/backend/runtimeenv"
	"rallycut/backend/storage"
	"rallycut/vision"
)

func hashBytes(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func TestResumableDownloadAndServerIgnoringRange(t *testing.T) {
	for _, ignore := range []bool{false, true} {
		t.Run(fmt.Sprint(ignore), func(t *testing.T) {
			data := []byte("0123456789")
			dest := filepath.Join(t.TempDir(), "file")
			os.WriteFile(dest+".part", data[:4], 0600)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Header.Get("Range") != "bytes=4-" {
					t.Errorf("wrong range: %s", r.Header.Get("Range"))
				}
				if !ignore {
					w.Header().Set("Content-Range", "bytes 4-9/10")
					w.WriteHeader(206)
					w.Write(data[4:])
				} else {
					w.Write(data)
				}
			}))
			defer server.Close()
			if err := downloadResumable(context.Background(), server.Client(), server.URL, dest, int64(len(data)), hashBytes(data), nil); err != nil {
				t.Fatal(err)
			}
			got, _ := os.ReadFile(dest)
			if string(got) != string(data) {
				t.Fatal("appended a full response to a partial file")
			}
		})
	}
}
func TestResumeRejectsWrongRangeAndHash(t *testing.T) {
	for _, badRange := range []bool{true, false} {
		t.Run(fmt.Sprint(badRange), func(t *testing.T) {
			data := []byte("0123456789")
			dest := filepath.Join(t.TempDir(), "file")
			os.WriteFile(dest+".part", data[:4], 0600)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if badRange {
					w.Header().Set("Content-Range", "bytes 0-9/10")
					w.WriteHeader(206)
				}
				w.Write(data)
			}))
			defer server.Close()
			digest := hashBytes(data)
			if !badRange {
				digest = strings.Repeat("a", 64)
			}
			if err := downloadResumable(context.Background(), server.Client(), server.URL, dest, 10, digest, nil); err == nil {
				t.Fatal("accepted unsafe bytes")
			}
			if _, err := os.Stat(dest); !os.IsNotExist(err) {
				t.Fatal("published unverified bytes")
			}
		})
	}
}
func bundleFixture(t *testing.T) (string, BundleSpec) {
	t.Helper()
	files := map[string][]byte{"python/python.exe": []byte("python"), "bin/ffmpeg.exe": []byte("ffmpeg"), "bin/ffprobe.exe": []byte("ffprobe")}
	m := bundleManifest{ID: "test-v1", Platform: "windows/amd64", Files: map[string]bundleFile{}}
	for name, b := range files {
		m.Files[name] = bundleFile{SHA256: hashBytes(b), Bytes: int64(len(b))}
	}
	manifest, _ := json.Marshal(m)
	files["bundle-manifest.json"] = manifest
	path := filepath.Join(t.TempDir(), "bundle.zip")
	f, _ := os.Create(path)
	z := zip.NewWriter(f)
	var installed int64
	for name, b := range files {
		w, err := z.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		w.Write(b)
		installed += int64(len(b))
	}
	z.Close()
	f.Close()
	digest, _ := fileSHA256(path)
	info, _ := os.Stat(path)
	return path, BundleSpec{ID: m.ID, Filename: "bundle.zip", SHA256: digest, ManifestSHA256: hashBytes(manifest), Bytes: info.Size(), InstalledBytes: installed}
}
func TestBundleActivationOnlyAfterSelfTest(t *testing.T) {
	for _, fail := range []bool{false, true} {
		t.Run(fmt.Sprint(fail), func(t *testing.T) {
			archive, spec := bundleFixture(t)
			dir := t.TempDir()
			p := New(Options{DataDir: dir})
			old := runtimeenv.ActiveState{ID: "old", Directory: "old-version"}
			active := filepath.Join(dir, "runtime/active.json")
			if err := storage.WriteJSON(active, old); err != nil {
				t.Fatal(err)
			}
			before, _ := os.ReadFile(active)
			python, err := p.installBundle(context.Background(), archive, spec, func(root string) error {
				now, _ := os.ReadFile(active)
				if string(now) != string(before) {
					t.Fatal("switched active environment before self-test")
				}
				if fail {
					return errors.New("torch DLL failed to load")
				}
				return nil
			})
			if fail {
				if err == nil || !strings.Contains(err.Error(), "torch DLL") {
					t.Fatal("lost diagnostic")
				}
				now, _ := os.ReadFile(active)
				if string(now) != string(before) {
					t.Fatal("damaged old active environment")
				}
				entries, _ := os.ReadDir(filepath.Join(dir, "runtime/versions"))
				if len(entries) != 0 {
					t.Fatal("left failed staging environment")
				}
			} else {
				if err != nil {
					t.Fatal(err)
				}
				if python != runtimeenv.Python(dir) {
					t.Fatal("activated wrong interpreter")
				}
				if _, err := os.Stat(filepath.Join(dir, "runtime/active.previous.json")); err != nil {
					t.Fatal("missing rollback pointer")
				}
			}
		})
	}
}
func TestBundleExtractionRejectsTraversal(t *testing.T) {
	archive, spec := bundleFixture(t)
	f, _ := os.OpenFile(archive, os.O_APPEND|os.O_WRONLY, 0600)
	f.Close()
	bad := filepath.Join(t.TempDir(), "bad.zip")
	out, _ := os.Create(bad)
	z := zip.NewWriter(out)
	w, _ := z.Create("../outside")
	w.Write([]byte("bad"))
	z.Close()
	out.Close()
	root := t.TempDir()
	if err := extractBundle(context.Background(), bad, root, spec); err == nil {
		t.Fatal("accepted traversal")
	}
}

// A real relocated portable runtime is built on Windows CI. This test uses the
// exact catalog embedded in the application; it does not borrow runner Python.
func TestPrebuiltBundleInstallation(t *testing.T) {
	if os.Getenv("RALLYCUT_BUNDLE_E2E") == "" {
		t.Skip("explicit networked Windows runtime test")
	}
	dir := t.TempDir()
	t.Setenv("RALLYCUT_DATA_DIR", dir)
	worker, err := vision.Install(filepath.Join(dir, "worker"))
	if err != nil {
		t.Fatal(err)
	}
	p := New(Options{DataDir: dir, Worker: worker, BundlePath: os.Getenv("RALLYCUT_BUNDLE_PATH"), Emit: func(s State) { t.Logf("%s %.0f%% %s %s", s.Step, s.Progress*100, s.Message, s.Detail) }})
	spec := p.bundleSpec()
	if spec == nil {
		t.Fatal("missing build-pinned runtime catalog")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	python, err := p.provisionBundle(ctx, *spec)
	if err != nil {
		t.Fatal(err)
	}
	if python != runtimeenv.Python(dir) {
		t.Fatal("relocated environment did not become active")
	}
	if _, checks := p.inspectRuntime(ctx); !allReady(checks) {
		t.Fatalf("activated environment not usable: %+v", checks)
	}
}
