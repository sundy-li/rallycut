package backend

import wruntime "github.com/wailsapp/wails/v2/pkg/runtime"

// macOS UTType expects the final extension, not a compound suffix. Wails v2
// passes 'rallycut.json' to UTType(typeWithFilenameExtension:), which returns nil
// and crashes NSOpenPanel/NSSavePanel. Select JSON and enforce the current
// *-rallycut.json suffix after the dialog returns.
func projectFileFilters() []wruntime.FileFilter {
	return []wruntime.FileFilter{{DisplayName: "RallyCut 项目（*-rallycut.json）", Pattern: "*.json"}}
}
