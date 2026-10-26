package backend

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"rallycut/backend/project"
	"rallycut/backend/storage"
)

func recentTestProject(name, videoName string, duration float64) *project.Project {
	p := project.New(project.Video{Path: videoName, Name: videoName, Duration: duration})
	p.Name = name
	p.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	p.RawRallies = []project.Rally{{ID: "raw", Start: 1, End: 8, Selected: true}}
	p.Rallies = append([]project.Rally{}, p.RawRallies...)
	p.Analysis = &project.AnalysisSummary{RallyEvents: []project.RallyEvent{}}
	p.SyncActive()
	return p
}

func TestListRecentProjectsIncludesCurrentAndMetadata(t *testing.T) {
	p := recentTestProject("夜场训练", "match.mp4", 75)
	a, path := newTestApp(t, p)
	if err := storage.WriteJSON(path, p); err != nil {
		t.Fatal(err)
	}
	a.rememberProject(path, p, true)

	entries := a.ListRecentProjects()
	if len(entries) != 1 {
		t.Fatalf("expected one recent project, got %+v", entries)
	}
	entry := entries[0]
	if entry.Path != path || entry.Name != "夜场训练" || entry.VideoName != "match.mp4" {
		t.Fatalf("unexpected metadata: %+v", entry)
	}
	if !entry.Available || !entry.Analyzed || entry.Rallies != 1 || entry.Duration != 75 {
		t.Fatalf("unexpected project summary: %+v", entry)
	}
}

func TestListRecentProjectsMarksMissingFileUnavailable(t *testing.T) {
	p := recentTestProject("已移动的项目", "missing.mp4", 30)
	a, path := newTestApp(t, p)
	if err := storage.WriteJSON(path, p); err != nil {
		t.Fatal(err)
	}
	a.rememberProject(path, p, true)
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}

	entries := a.ListRecentProjects()
	if len(entries) != 1 || entries[0].Available || entries[0].Error == "" {
		t.Fatalf("missing project should remain visible but unavailable: %+v", entries)
	}
}

func TestListRecentProjectsSeedsInternalProjectDirectory(t *testing.T) {
	a, _ := newTestApp(t, nil)
	p := recentTestProject("旧项目", "old.mp4", 42)
	path := filepath.Join(a.dataDir, "projects", "old-rallycut.json")
	if err := storage.WriteJSON(path, p); err != nil {
		t.Fatal(err)
	}

	entries := a.ListRecentProjects()
	if len(entries) != 1 || entries[0].Path != path || entries[0].Name != "旧项目" {
		t.Fatalf("internal project was not discovered: %+v", entries)
	}
}

func TestEmptyRecentProjectsSerializeAsArray(t *testing.T) {
	a, _ := newTestApp(t, nil)
	entries := a.ListRecentProjects()
	if entries == nil {
		t.Fatal("empty recent projects must be an empty slice, not nil")
	}
	data, err := json.Marshal(entries)
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "[]" {
		t.Fatalf("empty recent projects JSON = %s, want []", data)
	}
}

func TestLegacyRecentIndexIsIgnored(t *testing.T) {
	a, _ := newTestApp(t, nil)
	legacy := recentProjectIndex{Version: 1, Projects: []RecentProject{{
		Path: filepath.Join(a.dataDir, "20261024-152433-rallycut.json"), Name: "旧索引", Available: true,
	}}}
	if err := storage.WriteJSON(filepath.Join(a.dataDir, recentProjectsFile), legacy); err != nil {
		t.Fatal(err)
	}
	if entries := a.ListRecentProjects(); len(entries) != 0 {
		t.Fatalf("legacy recent index was not discarded: %+v", entries)
	}
}

func TestRememberProjectMovesReopenedProjectToFront(t *testing.T) {
	a, _ := newTestApp(t, nil)
	first := recentTestProject("第一场", "one.mp4", 20)
	second := recentTestProject("第二场", "two.mp4", 20)
	firstPath := filepath.Join(a.dataDir, "one-rallycut.json")
	secondPath := filepath.Join(a.dataDir, "two-rallycut.json")
	a.rememberProject(firstPath, first, true)
	a.rememberProject(secondPath, second, true)
	a.rememberProject(firstPath, first, true)

	entries := a.ListRecentProjects()
	if len(entries) != 2 || entries[0].Path != firstPath || entries[1].Path != secondPath {
		t.Fatalf("unexpected recent order: %+v", entries)
	}
}

func TestRenameProjectRenamesMetadataOnly(t *testing.T) {
	p := recentTestProject("原项目", "source.mp4", 20)
	a, oldPath := newTestApp(t, p)
	videoPath := filepath.Join(a.dataDir, "source.mp4")
	p.Video.Path = videoPath
	p.Sources[0].Video.Path = videoPath
	if err := os.WriteFile(videoPath, []byte("video data"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := a.install(p, oldPath); err != nil {
		t.Fatal(err)
	}
	if _, err := a.RenameProject("新项目"); err != nil {
		t.Fatal(err)
	}
	newPath := filepath.Join(filepath.Dir(oldPath), "新项目-rallycut.json")
	if _, err := os.Stat(oldPath); !os.IsNotExist(err) {
		t.Fatalf("old project metadata still exists: %v", err)
	}
	renamed, err := storage.Load(newPath)
	if err != nil || renamed.Name != "新项目" {
		t.Fatalf("renamed metadata = %+v, err=%v", renamed, err)
	}
	if a.current == nil || a.current.Name != "新项目" || a.projectPath != newPath {
		t.Fatalf("current project not updated: %+v path=%q", a.current, a.projectPath)
	}
	if info, err := os.Stat(videoPath); err != nil || info.Size() == 0 {
		t.Fatalf("source video was touched: info=%v err=%v", info, err)
	}
	entries := a.ListRecentProjects()
	if len(entries) != 1 || entries[0].Path != newPath || entries[0].Name != "新项目" {
		t.Fatalf("recent project not updated: %+v", entries)
	}
	var last struct {
		Path string `json:"path"`
	}
	if err := storage.ReadJSON(filepath.Join(a.dataDir, "last-project.json"), &last); err != nil || last.Path != newPath {
		t.Fatalf("last project = %q, err=%v", last.Path, err)
	}
}

func TestDeleteProjectRemovesMetadataOnly(t *testing.T) {
	p := recentTestProject("待删除", "source.mp4", 20)
	a, path := newTestApp(t, p)
	videoPath := filepath.Join(a.dataDir, "source.mp4")
	p.Video.Path = videoPath
	p.Sources[0].Video.Path = videoPath
	if err := storage.WriteJSON(path, p); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(videoPath, []byte("video data"), 0600); err != nil {
		t.Fatal(err)
	}
	a.rememberProject(path, p, true)
	if err := a.DeleteProject(path); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("project metadata still exists: %v", err)
	}
	if info, err := os.Stat(videoPath); err != nil || info.Size() == 0 {
		t.Fatalf("source video was touched: info=%v err=%v", info, err)
	}
	if a.current != nil || a.projectPath != "" {
		t.Fatalf("current project was not cleared: %+v path=%q", a.current, a.projectPath)
	}
	if entries := a.ListRecentProjects(); len(entries) != 0 {
		t.Fatalf("deleted project remained in recent list: %+v", entries)
	}
}
