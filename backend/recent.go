package backend

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"rallycut/backend/project"
	"rallycut/backend/storage"
)

const (
	recentProjectsSchema = 2
	recentProjectsFile   = "recent-projects.json"
	maxRecentProjects    = 30
)

// RecentProject is a lightweight, local-only entry for the project picker.
// Paths can point outside the app data directory because Save As supports any
// location chosen by the user.
type RecentProject struct {
	Path      string  `json:"path"`
	Name      string  `json:"name"`
	VideoName string  `json:"video_name"`
	UpdatedAt string  `json:"updated_at"`
	OpenedAt  string  `json:"opened_at"`
	Duration  float64 `json:"duration"`
	Rallies   int     `json:"rallies"`
	Sources   int     `json:"sources"`
	Analyzed  bool    `json:"analyzed"`
	Available bool    `json:"available"`
	Error     string  `json:"error,omitempty"`
}

type recentProjectIndex struct {
	Version  int             `json:"version"`
	Projects []RecentProject `json:"projects"`
}

type recentProjectFile struct {
	SchemaVersion int    `json:"schema_version"`
	ID            string `json:"id"`
	Name          string `json:"name"`
	UpdatedAt     string `json:"updated_at"`
	Video         struct {
		Name     string  `json:"name"`
		Path     string  `json:"path"`
		Duration float64 `json:"duration"`
	} `json:"video"`
	Sources []struct {
		Video struct {
			Name     string  `json:"name"`
			Path     string  `json:"path"`
			Duration float64 `json:"duration"`
		} `json:"video"`
	} `json:"sources"`
	Rallies  []struct{} `json:"rallies"`
	Analysis *struct{}  `json:"analysis"`
}

func cleanProjectPath(path string) string {
	if path == "" {
		return ""
	}
	if absolute, err := filepath.Abs(path); err == nil {
		path = absolute
	}
	return filepath.Clean(path)
}

func projectTime(p *project.Project, path string) string {
	if p != nil && p.UpdatedAt != "" {
		return p.UpdatedAt
	}
	if info, err := os.Stat(path); err == nil {
		return info.ModTime().UTC().Format(time.RFC3339)
	}
	return ""
}

func projectName(p *project.Project, path string) string {
	if p != nil {
		if name := strings.TrimSpace(p.Name); name != "" {
			return name
		}
		if name := strings.TrimSpace(p.Video.Name); name != "" {
			return name
		}
	}
	return projectNameFromPath(path)
}

func videoName(v project.Video, path string) string {
	if name := strings.TrimSpace(v.Name); name != "" {
		return name
	}
	if name := strings.TrimSpace(v.Path); name != "" {
		return filepath.Base(name)
	}
	return filepath.Base(path)
}

func recentFromProject(path string, p *project.Project, openedAt string) RecentProject {
	path = cleanProjectPath(path)
	updated := projectTime(p, path)
	if openedAt == "" {
		openedAt = updated
	}
	sources := 1
	if p != nil && len(p.Sources) > 0 {
		sources = len(p.Sources)
	}
	rallies := 0
	analyzed := false
	var duration float64
	var v project.Video
	if p != nil {
		rallies = len(p.Rallies)
		analyzed = p.Analysis != nil
		duration = p.Video.Duration
		v = p.Video
	}
	return RecentProject{
		Path:      path,
		Name:      projectName(p, path),
		VideoName: videoName(v, path),
		UpdatedAt: updated,
		OpenedAt:  openedAt,
		Duration:  duration,
		Rallies:   rallies,
		Sources:   sources,
		Analyzed:  analyzed,
		Available: true,
	}
}

func readRecentProjectFile(path string) (RecentProject, error) {
	path = cleanProjectPath(path)
	info, err := os.Stat(path)
	if err != nil {
		return RecentProject{Path: path, Name: projectName(nil, path), Available: false, Error: "项目文件不存在"}, err
	}
	if !info.Mode().IsRegular() {
		return RecentProject{Path: path, Name: projectName(nil, path), Available: false, Error: "项目路径不是文件"}, fmt.Errorf("项目路径不是文件")
	}
	f, err := os.Open(path)
	if err != nil {
		return RecentProject{Path: path, Name: projectName(nil, path), Available: false, Error: "项目文件无法读取"}, err
	}
	defer f.Close()
	if info.Size() > 32<<20 {
		return RecentProject{Path: path, Name: projectName(nil, path), Available: false, Error: "项目文件超过大小上限"}, fmt.Errorf("项目文件超过大小上限")
	}
	var meta recentProjectFile
	if err := json.NewDecoder(f).Decode(&meta); err != nil {
		return RecentProject{Path: path, Name: projectName(nil, path), Available: false, Error: "项目文件格式无效"}, err
	}
	if meta.SchemaVersion <= 0 || strings.TrimSpace(meta.ID) == "" {
		return RecentProject{Path: path, Name: projectName(nil, path), Available: false, Error: "项目文件格式无效"}, fmt.Errorf("项目文件格式无效")
	}
	name := strings.TrimSpace(meta.Name)
	if name == "" {
		name = projectName(nil, path)
	}
	vname := strings.TrimSpace(meta.Video.Name)
	if vname == "" && meta.Video.Path != "" {
		vname = filepath.Base(meta.Video.Path)
	}
	if vname == "" {
		vname = filepath.Base(path)
	}
	updated := meta.UpdatedAt
	if updated == "" {
		updated = info.ModTime().UTC().Format(time.RFC3339)
	}
	sources := 1
	if len(meta.Sources) > 0 {
		sources = len(meta.Sources)
	}
	return RecentProject{
		Path:      path,
		Name:      name,
		VideoName: vname,
		UpdatedAt: updated,
		OpenedAt:  updated,
		Duration:  meta.Video.Duration,
		Rallies:   len(meta.Rallies),
		Sources:   sources,
		Analyzed:  meta.Analysis != nil,
		Available: true,
	}, nil
}

// readRecentLocked requires recentMu to be held.
func (a *App) readRecentLocked() []RecentProject {
	var index recentProjectIndex
	if err := storage.ReadJSON(filepath.Join(a.dataDir, recentProjectsFile), &index); err != nil {
		return nil
	}
	if index.Version != recentProjectsSchema {
		return nil
	}
	return index.Projects
}

// writeRecentLocked requires recentMu to be held.
func (a *App) writeRecentLocked(entries []RecentProject) {
	index := recentProjectIndex{Version: recentProjectsSchema, Projects: entries}
	if err := storage.WriteJSON(filepath.Join(a.dataDir, recentProjectsFile), index); err != nil && a.log != nil {
		a.log.Error("save recent projects", "error", err)
	}
}

func findRecent(entries []RecentProject, path string) int {
	path = cleanProjectPath(path)
	for index, entry := range entries {
		if cleanProjectPath(entry.Path) == path {
			return index
		}
	}
	return -1
}

func (a *App) rememberProject(path string, p *project.Project, opened bool) {
	path = cleanProjectPath(path)
	if path == "" || p == nil {
		return
	}
	a.recentMu.Lock()
	defer a.recentMu.Unlock()
	entries := a.readRecentLocked()
	index := findRecent(entries, path)
	openedAt := ""
	if index >= 0 {
		openedAt = entries[index].OpenedAt
	}
	if opened {
		openedAt = time.Now().UTC().Format(time.RFC3339)
	}
	entry := recentFromProject(path, p, openedAt)
	if index >= 0 {
		if opened {
			entries = append([]RecentProject{entry}, append(entries[:index], entries[index+1:]...)...)
		} else {
			entries[index] = entry
		}
	} else {
		entries = append([]RecentProject{entry}, entries...)
	}
	if len(entries) > maxRecentProjects {
		entries = entries[:maxRecentProjects]
	}
	a.writeRecentLocked(entries)
}

func (a *App) forgetRecentProject(path string) {
	path = cleanProjectPath(path)
	a.recentMu.Lock()
	defer a.recentMu.Unlock()
	entries := a.readRecentLocked()
	index := findRecent(entries, path)
	if index < 0 {
		return
	}
	entries = append(entries[:index], entries[index+1:]...)
	a.writeRecentLocked(entries)
}

// seedRecentLocked discovers current-format projects that are not in the
// recent index yet. It reads lightweight metadata only; full tracks are
// ignored by the decoder into recentProjectFile.
func (a *App) seedRecentLocked(entries []RecentProject) []RecentProject {
	known := make(map[string]bool, len(entries))
	for _, entry := range entries {
		known[cleanProjectPath(entry.Path)] = true
	}
	addPath := func(path string) {
		path = cleanProjectPath(path)
		if path == "" || known[path] {
			return
		}
		if _, err := os.Stat(path); err != nil {
			return
		}
		entry, err := readRecentProjectFile(path)
		if err != nil {
			return
		}
		known[path] = true
		entries = append(entries, entry)
	}

	var last struct {
		Path string `json:"path"`
	}
	if err := storage.ReadJSON(filepath.Join(a.dataDir, "last-project.json"), &last); err == nil && last.Path != "" && isProjectFilePath(last.Path) {
		addPath(last.Path)
	}
	paths, _ := filepath.Glob(filepath.Join(a.dataDir, "projects", "*"+projectFileSuffix))
	type candidate struct {
		path    string
		modTime time.Time
	}
	candidates := make([]candidate, 0, len(paths))
	for _, path := range paths {
		if info, err := os.Stat(path); err == nil && info.Mode().IsRegular() {
			candidates = append(candidates, candidate{path: path, modTime: info.ModTime()})
		}
	}
	sort.Slice(candidates, func(i, j int) bool { return candidates[i].modTime.After(candidates[j].modTime) })
	for _, item := range candidates {
		addPath(item.path)
		if len(entries) >= maxRecentProjects {
			break
		}
	}
	return entries
}

func projectSortTime(entry RecentProject) time.Time {
	for _, value := range []string{entry.OpenedAt, entry.UpdatedAt} {
		if parsed, err := time.Parse(time.RFC3339, value); err == nil {
			return parsed
		}
	}
	if info, err := os.Stat(entry.Path); err == nil {
		return info.ModTime()
	}
	return time.Time{}
}

// ListRecentProjects returns local project metadata. It never includes media
// contents and never uploads or resolves remote paths.
func (a *App) ListRecentProjects() []RecentProject {
	a.mu.RLock()
	current := project.Clone(a.current)
	currentPath := a.projectPath
	a.mu.RUnlock()

	a.recentMu.Lock()
	defer a.recentMu.Unlock()
	entries := a.readRecentLocked()
	changed := false
	if !a.recentSeeded {
		before := len(entries)
		entries = a.seedRecentLocked(entries)
		a.recentSeeded = true
		changed = changed || len(entries) != before
	}
	if current != nil && currentPath != "" {
		index := findRecent(entries, currentPath)
		openedAt := ""
		if index >= 0 {
			openedAt = entries[index].OpenedAt
		}
		entry := recentFromProject(currentPath, current, openedAt)
		if index >= 0 {
			entries[index] = entry
		} else {
			entries = append([]RecentProject{entry}, entries...)
		}
		changed = true
	}
	for index := range entries {
		entry := &entries[index]
		entry.Path = cleanProjectPath(entry.Path)
		if !isProjectFilePath(entry.Path) {
			entry.Available = false
			entry.Error = "旧格式项目已忽略"
			continue
		}
		info, err := os.Stat(entry.Path)
		if err != nil || !info.Mode().IsRegular() {
			entry.Available = false
			if entry.Error == "" {
				entry.Error = "项目文件不存在"
			}
			continue
		}
		entry.Available = true
		entry.Error = ""
		if current == nil || cleanProjectPath(currentPath) != entry.Path {
			if entry.Name == "" || entry.UpdatedAt == "" {
				if refreshed, err := readRecentProjectFile(entry.Path); err == nil {
					openedAt := entry.OpenedAt
					*entry = refreshed
					if openedAt != "" {
						entry.OpenedAt = openedAt
					}
					changed = true
				}
			}
		}
	}
	sort.SliceStable(entries, func(i, j int) bool {
		return projectSortTime(entries[i]).After(projectSortTime(entries[j]))
	})
	if len(entries) > maxRecentProjects {
		entries = entries[:maxRecentProjects]
		changed = true
	}
	if changed {
		a.writeRecentLocked(entries)
	}
	result := make([]RecentProject, len(entries))
	copy(result, entries)
	return result
}
