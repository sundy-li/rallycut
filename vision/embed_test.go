package vision

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"testing"
)

func TestEmbeddedLocalPythonImportClosure(t *testing.T) {
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("stdlib Python required for dependency check")
	}
	root := t.TempDir()
	if _, err := Install(root); err != nil {
		t.Fatal(err)
	}
	source, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	script := filepath.Join(source, "..", "scripts", "check_runtime_imports.py")
	out, err := exec.Command(python, script, "--source", source, "--installed", root).CombinedOutput()
	if err != nil {
		t.Fatalf("embedded Python dependency missing: %s: %v", out, err)
	}
}

func TestInstallImmutableWorkerResources(t *testing.T) {
	root := t.TempDir()
	path, err := Install(root)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := files.ReadFile("worker.py")
	if err != nil {
		t.Fatal(err)
	}
	before, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = Install(root); err != nil {
		t.Fatal(err)
	}
	after, _ := os.Stat(path)
	if !os.SameFile(before, after) {
		t.Fatal("identical worker was replaced during startup")
	}
	if err = os.WriteFile(path, []byte("corrupt"), 0600); err != nil {
		t.Fatal(err)
	}
	var wait sync.WaitGroup
	for range 4 {
		wait.Add(1)
		go func() {
			defer wait.Done()
			if _, err := Install(root); err != nil {
				t.Error(err)
			}
		}()
	}
	wait.Wait()
	actual, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(expected, actual) {
		t.Fatal("incomplete resource", err)
	}
	if leftovers, _ := filepath.Glob(filepath.Join(root, ".worker-*")); len(leftovers) != 0 {
		t.Fatal(leftovers)
	}
}
