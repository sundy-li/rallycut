package analysis

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"rallycut/backend/media"
	"strings"
	"time"
)

// Prefer an explicit override, an app-local runtime, then the repository venv.
// Walking executable ancestors also works when Finder launches build/bin/*.app.
func Python(dataDir string) string {
	if p := os.Getenv("RALLYCUT_PYTHON3"); p != "" {
		return p
	}
	roots := []string{dataDir}
	if cwd, err := os.Getwd(); err == nil {
		roots = append(roots, cwd)
	}
	if exe, err := os.Executable(); err == nil {
		roots = append(roots, filepath.Dir(exe))
	}
	for _, root := range roots {
		for i := 0; i < 8 && root != ""; i++ {
			for _, relative := range []string{
				"runtime/venv/bin/python3",
				"runtime/venv/Scripts/python.exe",
				"venv/bin/python3",
				".venv/bin/python3",
				".venv/Scripts/python.exe",
			} {
				p := filepath.Join(root, relative)
				if info, err := os.Stat(p); err == nil && !info.IsDir() {
					return p
				}
			}
			parent := filepath.Dir(root)
			if parent == root {
				break
			}
			root = parent
		}
	}
	return media.Binary("python3")
}

func CheckModel(python, worker string) bool {
	ok, _ := ModelDetail(python, worker)
	return ok
}

// ModelDetail verifies torch and the pinned weights digest, returning the
// interpreter's combined output so callers can report why the check failed.
func ModelDetail(python, worker string) (bool, string) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	code := "import sys,hashlib,torch,numpy as np;torch.from_numpy(np.zeros((1,),dtype=np.float32)).numpy();sys.path.insert(0,sys.argv[1]);from pretrained import locate_weights,WEIGHTS_SHA256;assert hashlib.sha256(locate_weights().read_bytes()).hexdigest()==WEIGHTS_SHA256"
	out, err := exec.CommandContext(ctx, python, "-c", code, filepath.Dir(worker)).CombinedOutput()
	if err != nil {
		if ctx.Err() != nil {
			return false, "模型自检超时"
		}
		message := strings.TrimSpace(string(out))
		if message == "" {
			message = err.Error()
		}
		if len(message) > 600 {
			message = message[:600]
		}
		return false, message
	}
	return true, ""
}

func CheckPython(python string) bool {
	ok, _ := PythonDetail(python)
	return ok
}

// PythonDetail reports why cv2/numpy cannot be imported, for setup errors.
func PythonDetail(python string) (bool, string) {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, python, "-c", "import cv2, numpy").CombinedOutput()
	if err != nil {
		if ctx.Err() != nil {
			return false, "导入 cv2/numpy 超时"
		}
		return false, strings.TrimSpace(string(out))
	}
	return true, ""
}
