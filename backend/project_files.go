package backend

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"rallycut/backend/project"
)

const projectFileSuffix = "-rallycut.json"

func isProjectFilePath(path string) bool {
	return strings.HasSuffix(strings.ToLower(filepath.Clean(path)), projectFileSuffix)
}

func projectNameFromPath(path string) string {
	base := filepath.Base(filepath.Clean(path))
	if isProjectFilePath(base) {
		base = base[:len(base)-len(projectFileSuffix)]
	}
	return strings.TrimSpace(base)
}

func projectFileBase(name string) string {
	name = strings.TrimSpace(name)
	replacer := strings.NewReplacer(
		"/", "-", "\\", "-", ":", "-", "*", "-", "?", "-",
		"\"", "-", "<", "-", ">", "-", "|", "-",
	)
	name = strings.Trim(replacer.Replace(name), " .-")
	if name == "" {
		return "project"
	}
	return name
}

// normalizeProjectFilePath enforces the single-file project convention:
// <name>-rallycut.json. A filename chosen as foo.json or foo becomes
// foo-rallycut.json.
func normalizeProjectFilePath(path string) string {
	path = strings.TrimSpace(path)
	if path == "" {
		return ""
	}
	if isProjectFilePath(path) {
		return filepath.Clean(path)
	}
	ext := filepath.Ext(path)
	base := strings.TrimSuffix(path, ext)
	if strings.HasSuffix(strings.ToLower(base), "-rallycut") {
		return filepath.Clean(base + ".json")
	}
	return filepath.Clean(base + projectFileSuffix)
}

func normalizeProjectName(name string) string {
	name = strings.TrimSpace(name)
	if name == "" {
		return project.DefaultName(time.Now())
	}
	runes := []rune(name)
	if len(runes) > 80 {
		name = strings.TrimSpace(string(runes[:80]))
	}
	if name == "" {
		return project.DefaultName(time.Now())
	}
	return name
}

func uniqueProjectPath(dir, base string) string {
	candidate := filepath.Join(dir, base+projectFileSuffix)
	for index := 2; index < 10000; index++ {
		if _, err := os.Stat(candidate); os.IsNotExist(err) {
			return candidate
		}
		candidate = filepath.Join(dir, fmt.Sprintf("%s-%d%s", base, index, projectFileSuffix))
	}
	return filepath.Join(dir, fmt.Sprintf("%s-%s%s", base, project.NewID(), projectFileSuffix))
}

func (a *App) internalProjectPath(p *project.Project) string {
	path := uniqueProjectPath(filepath.Join(a.dataDir, "projects"), projectFileBase(p.Name))
	p.Name = projectNameFromPath(path)
	return path
}
