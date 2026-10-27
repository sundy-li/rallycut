// Package runtimeenv resolves immutable, versioned app-managed environments.
package runtimeenv

import (
	_ "embed"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
)

// The release builder pins the installed directory to this executable. Do not
// discover arbitrary versions from neighboring files or a writable JSON URL.
//
//go:embed bundled-id.txt
var bundledID string

func BundledID() string { return strings.TrimSpace(bundledID) }

// InstalledAt resolves only this build's versioned installer payload. Existence
// is not a readiness signal: setup still verifies its pinned file manifest.
func InstalledAt(executable, id string) string {
	if executable == "" || !SafeName(id) {
		return ""
	}
	root := filepath.Join(filepath.Dir(executable), "runtimes", id)
	if info, err := os.Stat(filepath.Join(root, "bundle-manifest.json")); err == nil && info.Mode().IsRegular() {
		return root
	}
	return ""
}
func Installed() string {
	exe, err := os.Executable()
	if err != nil {
		return ""
	}
	return InstalledAt(exe, BundledID())
}

// Root prefers the current installer's environment over previous per-user
// versions. Neither location needs a first-run extraction if already installed.
func Root(dataDir string) string {
	if root := Installed(); root != "" {
		return root
	}
	return Active(dataDir)
}

type ActiveState struct {
	ID        string `json:"id"`
	Directory string `json:"directory"`
}

func Active(dataDir string) string {
	data, err := os.ReadFile(filepath.Join(dataDir, "runtime", "active.json"))
	if err != nil {
		return ""
	}
	var state ActiveState
	if json.Unmarshal(data, &state) != nil || state.ID == "" || !SafeName(state.Directory) {
		return ""
	}
	return filepath.Join(dataDir, "runtime", "versions", state.Directory)
}
func SafeName(name string) bool {
	if name == "" || name == "." || name == ".." {
		return false
	}
	for _, r := range name {
		if !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || strings.ContainsRune("-_.", r)) {
			return false
		}
	}
	return true
}
func Python(dataDir string) string {
	if root := Root(dataDir); root != "" {
		return filepath.Join(root, "python", "python.exe")
	}
	return ""
}
