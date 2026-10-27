package backend

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"rallycut/backend/project"
)

func TestNormalizeProjectFilePath(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "中文 项目")
	cases := map[string]string{
		"比赛":                    "比赛-rallycut.json",
		"比赛.json":               "比赛-rallycut.json",
		"比赛-rallycut.json":      "比赛-rallycut.json",
		"比赛-rallycut":           "比赛-rallycut.json",
		"another-RALLYCUT.JSON": "another-RALLYCUT.JSON",
	}
	for name, expected := range cases {
		input, want := filepath.Join(dir, name), filepath.Join(dir, expected)
		if got := normalizeProjectFilePath(input); got != want {
			t.Errorf("normalizeProjectFilePath(%q) = %q, want %q", input, got, want)
		}
	}
}

func TestInternalProjectPathUsesTimestampAndAvoidsCollision(t *testing.T) {
	a := &App{dataDir: t.TempDir()}
	at := time.Date(2026, 10, 24, 15, 24, 33, 0, time.Local)
	p := project.NewAt(project.Video{Path: "/videos/match.mp4", Duration: 20}, at)
	first := filepath.Join(a.dataDir, "projects", "20261024-152433-rallycut.json")
	if got := a.internalProjectPath(p); got != first {
		t.Fatalf("internal path = %q, want %q", got, first)
	}
	if p.Name != "20261024-152433" {
		t.Fatalf("project name = %q", p.Name)
	}
	if err := os.MkdirAll(filepath.Dir(first), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(first, []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	second := filepath.Join(a.dataDir, "projects", "20261024-152433-2-rallycut.json")
	if got := a.internalProjectPath(p); got != second {
		t.Fatalf("collision path = %q, want %q", got, second)
	}
	if p.Name != "20261024-152433-2" {
		t.Fatalf("collision-safe project name = %q", p.Name)
	}
}
