// Package runtimeenv resolves immutable, versioned app-managed environments.
package runtimeenv

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
)

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
	if root := Active(dataDir); root != "" {
		return filepath.Join(root, "python", "python.exe")
	}
	return ""
}
