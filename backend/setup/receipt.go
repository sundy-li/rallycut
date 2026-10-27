package setup

import (
	"context"
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"strings"

	"rallycut/backend/runtimeenv"
	"rallycut/backend/storage"
	"rallycut/models"
	"rallycut/vision"
)

const readyReceiptSchema = 1

func receiptPathKey(path string) string {
	path = filepath.Clean(path)
	if runtime.GOOS == "windows" {
		path = strings.ToLower(path)
	}
	return path
}

type fileStamp struct {
	Bytes    int64  `json:"bytes"`
	Modified int64  `json:"modified_ns"`
	Mode     uint32 `json:"mode"`
}
type readyReceipt struct {
	Schema   int                  `json:"schema"`
	Identity string               `json:"identity"`
	Files    map[string]fileStamp `json:"files"`
}

func (p *Provisioner) receiptPath() string {
	return filepath.Join(p.options.DataDir, "runtime-ready.json")
}
func (p *Provisioner) invalidateReceipt() {
	if err := os.Remove(p.receiptPath()); err != nil && !os.IsNotExist(err) {
		p.options.Log.Warn("cannot invalidate runtime readiness receipt", "error", err)
	}
}

// Receipt checks are all in-process file operations: no Python, FFmpeg, network,
// package import or model forward. This is a startup cache, not a defense against
// an attacker who can change both the user's receipt and installation files.
func (p *Provisioner) readinessSnapshot(python string) (readyReceipt, error) {
	spec := p.bundleSpec()
	if spec == nil {
		return readyReceipt{}, fmt.Errorf("no pinned runtime")
	}
	root := p.expandedRoot()
	if root == "" {
		root = runtimeenv.Active(p.options.DataDir)
	}
	expected := filepath.Join(root, "python", "python.exe")
	if root == "" || receiptPathKey(python) != receiptPathKey(expected) {
		return readyReceipt{}, fmt.Errorf("runtime interpreter changed")
	}
	manifestPath := filepath.Join(root, "bundle-manifest.json")
	info, err := os.Stat(manifestPath)
	if err != nil || info.Size() > 16<<20 {
		return readyReceipt{}, fmt.Errorf("runtime manifest missing or oversized")
	}
	digest, err := fileSHA256(manifestPath)
	if err != nil || digest != spec.ManifestSHA256 {
		return readyReceipt{}, fmt.Errorf("runtime manifest changed")
	}
	data, err := os.ReadFile(manifestPath)
	if err != nil {
		return readyReceipt{}, err
	}
	var manifest bundleManifest
	if json.Unmarshal(data, &manifest) != nil || manifest.ID != spec.ID || manifest.Platform != "windows/amd64" || len(manifest.Files) == 0 {
		return readyReceipt{}, fmt.Errorf("runtime identity changed")
	}
	weights, err := defaultWeights()
	if err != nil {
		return readyReceipt{}, err
	}
	// The model is only ~6 MB; hash it in-process rather than trust mtime alone.
	if digest, err := fileSHA256(p.weightsPath()); err != nil || !strings.EqualFold(digest, weights.SHA256) {
		return readyReceipt{}, fmt.Errorf("model missing or changed")
	}
	identityData, _ := json.Marshal(struct {
		OS, Arch, Root, Python, Worker, WorkerDigest, ModelManifest string
		Spec                                                        BundleSpec
		Overrides                                                   map[string]string
	}{runtime.GOOS, runtime.GOARCH, receiptPathKey(root), receiptPathKey(python), receiptPathKey(p.options.Worker), vision.Digest(), string(models.Manifest), *spec, map[string]string{
		"python": os.Getenv("RALLYCUT_PYTHON3"), "ffmpeg": os.Getenv("RALLYCUT_FFMPEG"), "ffprobe": os.Getenv("RALLYCUT_FFPROBE"), "model": os.Getenv("RALLYCUT_MODEL_PATH"), "onnx": os.Getenv("RALLYCUT_ONNX_MODEL"), "coreml": os.Getenv("RALLYCUT_COREML_MODEL"),
	}})
	result := readyReceipt{Schema: readyReceiptSchema, Identity: string(identityData), Files: map[string]fileStamp{}}
	add := func(path string) error {
		info, err := os.Stat(path)
		if err != nil {
			return err
		}
		if !info.Mode().IsRegular() {
			return fmt.Errorf("runtime file is not regular: %s", path)
		}
		result.Files[receiptPathKey(path)] = fileStamp{Bytes: info.Size(), Modified: info.ModTime().UnixNano(), Mode: uint32(info.Mode())}
		return nil
	}
	for _, required := range []string{"python/python.exe", "bin/ffmpeg.exe", "bin/ffprobe.exe"} {
		if _, ok := manifest.Files[required]; !ok {
			return readyReceipt{}, fmt.Errorf("missing runtime executable")
		}
	}
	for relative, file := range manifest.Files {
		if !safeBundlePath(relative) {
			return readyReceipt{}, fmt.Errorf("invalid runtime path")
		}
		// Only loader-critical metadata on repeated launches; a manual recheck
		// still hashes the complete manifest and runs import/model-forward tests.
		ext := strings.ToLower(filepath.Ext(relative))
		critical := ext == ".exe" || ext == ".dll" || ext == ".pyd" || ext == ".zip" || relative == "python/Lib/site-packages/torch/__init__.py" || relative == "python/Lib/site-packages/numpy/__init__.py" || relative == "python/Lib/site-packages/cv2/__init__.py"
		if !critical {
			continue
		}
		path := filepath.Join(root, filepath.FromSlash(relative))
		if err := add(path); err != nil {
			return readyReceipt{}, err
		}
		if result.Files[receiptPathKey(path)].Bytes != file.Bytes {
			return readyReceipt{}, fmt.Errorf("runtime file size changed: %s", relative)
		}
	}
	if err := add(manifestPath); err != nil {
		return readyReceipt{}, err
	}
	if err := add(p.weightsPath()); err != nil {
		return readyReceipt{}, err
	}
	if p.options.Worker == "" {
		return readyReceipt{}, fmt.Errorf("worker not installed")
	}
	if err := filepath.WalkDir(filepath.Dir(p.options.Worker), func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if entry.Name() == "__pycache__" {
				return filepath.SkipDir
			}
			return nil
		}
		if strings.HasSuffix(entry.Name(), ".pyc") {
			return nil
		}
		return add(path)
	}); err != nil {
		return readyReceipt{}, err
	}
	return result, nil
}
func (p *Provisioner) saveReadiness(python string) {
	if p.bundleSpec() == nil {
		return
	}
	snapshot, err := p.snapshot(python)
	if err == nil {
		err = storage.WriteJSON(p.receiptPath(), snapshot)
	}
	if err != nil {
		p.options.Log.Warn("could not save startup readiness cache; next launch will recheck", "error", err)
	}
}
func (p *Provisioner) cachedReadiness() (string, bool) {
	if p.bundleSpec() == nil {
		return "", false
	}
	var previous readyReceipt
	if err := storage.ReadJSON(p.receiptPath(), &previous); err != nil || previous.Schema != readyReceiptSchema {
		return "", false
	}
	root := p.expandedRoot()
	if root == "" {
		root = runtimeenv.Active(p.options.DataDir)
	}
	python := filepath.Join(root, "python", "python.exe")
	current, err := p.snapshot(python)
	if err != nil || previous.Identity != current.Identity || len(previous.Files) != len(current.Files) {
		return "", false
	}
	for path, stamp := range current.Files {
		if old, ok := previous.Files[path]; !ok || old != stamp {
			return "", false
		}
	}
	return python, true
}

// Boot synchronously resolves an existing success receipt before publishing any
// checking state. Detect is reserved for first use, invalidation or explicit
// rechecks, and never performs automatic installation.
func (p *Provisioner) Boot(ctx context.Context) {
	p.mu.Lock()
	if p.running || ctx.Err() != nil {
		p.mu.Unlock()
		return
	}
	python, ok := p.cachedReadiness()
	if ok {
		p.state = State{State: "ready", Step: "ready", Progress: 1, Message: "运行环境已就绪", Platform: platformName(), Python: python, Checks: []CheckItem{{ID: "python", Ready: true}, {ID: "media", Ready: true}, {ID: "packages", Ready: true}, {ID: "model", Ready: true}, {ID: "verify", Ready: true}}}
		state := p.snapshotLocked()
		p.mu.Unlock()
		p.emit(state)
		return
	}
	p.mu.Unlock()
	p.Detect(ctx)
}
