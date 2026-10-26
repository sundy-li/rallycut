package vision

import (
	"bytes"
	"crypto/sha256"
	"embed"
	"encoding/hex"
	"io/fs"
	"os"
	"path/filepath"
)

// Weights are deliberately NOT embedded. Keep upstream MIT notices with code.
//
//go:embed worker.py visual.py audio_features.py backends.py pretrained.py neural_analysis.py inference_pipeline.py performance.py video_decode.py table_locator.py table_jump.py shot_boundary.py rally_state.py rally_activity.py rally_transits.py rally_serves.py play_area.py net_geometry.py detection_cache.py vendor/blurball/network.py vendor/blurball/config.json vendor/blurball/LICENSE.md vendor/blurball/HRNET-LICENSE vendor/blurball/NOTICE.md
var files embed.FS

// Requirements are installed into the app-managed runtime on first launch.
//
//go:embed requirements.txt requirements-model.txt requirements-windows.txt
var Requirements embed.FS

func Digest() string {
	hash := sha256.New()
	_ = fs.WalkDir(files, ".", func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			return nil
		}
		data, err := files.ReadFile(path)
		if err != nil {
			return err
		}
		hash.Write([]byte(path))
		hash.Write(data)
		return nil
	})
	return hex.EncodeToString(hash.Sum(nil))
}

func Install(dir string) (string, error) {
	err := fs.WalkDir(files, ".", func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			return nil
		}
		target := filepath.Join(dir, filepath.FromSlash(path))
		if err := os.MkdirAll(filepath.Dir(target), 0700); err != nil {
			return err
		}
		data, err := files.ReadFile(path)
		if err != nil {
			return err
		}
		if current, err := os.ReadFile(target); err == nil && bytes.Equal(current, data) {
			return nil
		}
		// Publish complete modules atomically; simultaneous same-version startups
		// must not truncate a Python file another process is importing.
		file, err := os.CreateTemp(filepath.Dir(target), ".worker-*")
		if err != nil {
			return err
		}
		defer os.Remove(file.Name())
		if _, err = file.Write(data); err != nil {
			file.Close()
			return err
		}
		if err = file.Close(); err != nil {
			return err
		}
		return os.Rename(file.Name(), target)
	})
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "worker.py"), nil
}
