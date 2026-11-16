// Package buildinfo reports which source the running binary was built from,
// so users can tell whether an installed copy is current.
package buildinfo

import (
	"runtime/debug"
	"strings"
)

// Set at link time by scripts/package.sh, build-desktop.sh and
// build-windows.ps1 via -ldflags "-X rallycut/backend/buildinfo.Version=…".
var (
	Version   = ""
	Commit    = ""
	Dirty     = "" // "true" when built from a worktree with uncommitted changes
	BuildTime = "" // UTC RFC 3339
)

// Info is shown in the setup screen, project home and settings.
type Info struct {
	Version   string `json:"version"`
	Commit    string `json:"commit"`
	Dirty     bool   `json:"dirty"`
	BuildTime string `json:"build_time"`
}

// Get falls back to Go's VCS stamp when no link-time values were set (for
// example `wails dev` or `go run`); an unknown commit stays empty instead of
// being guessed.
func Get() Info {
	info := Info{Version: Version, Commit: Commit, Dirty: Dirty == "true", BuildTime: BuildTime}
	if info.Commit == "" {
		if bi, ok := debug.ReadBuildInfo(); ok {
			for _, s := range bi.Settings {
				switch s.Key {
				case "vcs.revision":
					info.Commit = s.Value
				case "vcs.modified":
					info.Dirty = s.Value == "true"
				case "vcs.time":
					if info.BuildTime == "" {
						info.BuildTime = s.Value
					}
				}
			}
		}
	}
	if len(info.Commit) > 12 {
		info.Commit = info.Commit[:12]
	}
	if info.Version == "" {
		info.Version = "dev"
	}
	info.Version = strings.TrimPrefix(info.Version, "v")
	return info
}
