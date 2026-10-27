package main

import (
	"path"
	"regexp"
	"strings"
	"testing"
)

func TestEmbeddedFrontendHasEntryAndAssets(t *testing.T) {
	html, err := assets.ReadFile("frontend/dist/index.html")
	if err != nil {
		t.Fatalf("frontend is missing: run the frontend/Wails build before compiling: %v", err)
	}
	refs := regexp.MustCompile(`(?:src|href)="(/assets/[^"?]+\.(?:js|css))"`).FindAllSubmatch(html, -1)
	if len(refs) < 2 {
		t.Fatal("frontend entry is missing its JS/CSS build references")
	}
	for _, ref := range refs {
		filename := path.Join("frontend/dist", strings.TrimPrefix(string(ref[1]), "/"))
		if data, err := assets.ReadFile(filename); err != nil || len(data) == 0 {
			t.Fatalf("embedded asset missing: %s (%v)", filename, err)
		}
	}
}
