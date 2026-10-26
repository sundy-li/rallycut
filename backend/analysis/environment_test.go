package analysis

import (
	"os"
	"rallycut/vision"
	"testing"
)

func TestModelRuntimeFindsRepositoryWeightsFromDifferentWorkingDirectory(t *testing.T) {
	if os.Getenv("RALLYCUT_RUN_MODEL_TESTS") != "1" {
		t.Skip("explicit opt-in for local checkpoint")
	}
	python := Python("")
	worker, err := vision.Install(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	// Finder / installed workers do not necessarily run in the repository CWD.
	t.Chdir(t.TempDir())
	if !CheckModel(python, worker) {
		t.Fatal("venv/weight lookup failed outside repository cwd")
	}
}
