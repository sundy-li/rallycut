package setup

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLocalInstalledMissingModelNeverBootstrapsPython(t *testing.T) {
	archive, spec := bundleFixture(t)
	root := t.TempDir()
	if err := extractBundle(context.Background(), archive, root, spec); err != nil {
		t.Fatal(err)
	}
	var messages []string
	p := New(Options{DataDir: t.TempDir(), InstalledRoot: root, Emit: func(s State) { messages = append(messages, s.Message) }})
	p.noEmbeddedBundle = true
	// Source checkout: no release archive catalog. A canceled operation must go
	// straight to validating the installed runtime, never download uv or run pip.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := p.provision(ctx)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("wrong installed preparation branch: %v", err)
	}
	for _, message := range messages {
		if strings.Contains(message, "下载环境准备工具") || strings.Contains(message, "虚拟环境") {
			t.Fatalf("installed runtime bootstrapped a second Python: %s", message)
		}
	}
	if _, err := os.Stat(p.runtimeDir()); !os.IsNotExist(err) {
		t.Fatal("created a second runtime before model setup")
	}
}
func TestUnpinnedLocalRuntimeStillVerifiesEveryFile(t *testing.T) {
	archive, spec := bundleFixture(t)
	root := t.TempDir()
	if err := extractBundle(context.Background(), archive, root, spec); err != nil {
		t.Fatal(err)
	}
	if err := verifyInstalledFiles(context.Background(), root, nil); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "python", "python.exe"), []byte("broken"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := verifyInstalledFiles(context.Background(), root, nil); err == nil {
		t.Fatal("local builds silently trust corrupted executables")
	}
}
