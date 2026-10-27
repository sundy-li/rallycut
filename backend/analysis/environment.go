package analysis

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"rallycut/backend/media"
	"rallycut/backend/runtimeenv"
	"strings"
	"time"
)

func Python(dataDir string) string {
	if p := os.Getenv("RALLYCUT_PYTHON3"); p != "" {
		return p
	}
	if p := runtimeenv.Python(dataDir); p != "" {
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
			for _, relative := range []string{"runtime/venv/bin/python3", "runtime/venv/Scripts/python.exe", "venv/bin/python3", ".venv/bin/python3", ".venv/Scripts/python.exe"} {
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

// PythonEnv removes interpreter injection while preserving explicit app model
// paths, platform loader variables and normal proxy settings.
func PythonEnv() []string {
	var env []string
	for _, entry := range os.Environ() {
		key, _, _ := strings.Cut(entry, "=")
		if !strings.HasPrefix(strings.ToUpper(key), "PYTHON") {
			env = append(env, entry)
		}
	}
	return append(env, "PYTHONNOUSERSITE=1", "PYTHONUTF8=1")
}
func CheckModel(python, worker string) bool { ok, _ := ModelDetail(python, worker); return ok }
func ModelDetail(python, worker string) (bool, string) {
	return ModelDetailContext(context.Background(), python, worker, os.Getenv("RALLYCUT_DATA_DIR"))
}

// ARM x64 emulation can need longer than 30 seconds on first torch import.
// Report timeouts, exit status and the traceback tail instead of discarding it.
func ModelDetailContext(parent context.Context, python, worker, dataDir string) (bool, string) {
	ctx, cancel := context.WithTimeout(parent, 3*time.Minute)
	defer cancel()
	code := `import sys,hashlib,torch,numpy as np
sys.path.insert(0,sys.argv[1])
from pretrained import locate_weights,WEIGHTS_SHA256,BlurBallDetector
assert torch.from_numpy(np.zeros((1,),dtype=np.float32)).numpy().shape==(1,)
p=locate_weights()
assert hashlib.sha256(p.read_bytes()).hexdigest()==WEIGHTS_SHA256,'model digest mismatch'
d=BlurBallDetector(device='cpu',runtime='torch')
with torch.inference_mode():
 out=d.model(torch.zeros((1,9,288,512),dtype=torch.float32))[0]
 assert torch.isfinite(out).all(),'non-finite model output'
print('model forward OK',tuple(out.shape))`
	cmd := exec.CommandContext(ctx, python, "-I", "-c", code, filepath.Dir(worker))
	cmd.Env = append(PythonEnv(), "RALLYCUT_DATA_DIR="+dataDir)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return false, probeFailure(ctx, "视觉模型加载与前向", out, err)
	}
	return true, ""
}
func CheckPython(python string) bool { ok, _ := PythonDetail(python); return ok }
func PythonDetail(python string) (bool, string) {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	code := `import cv2,numpy,sys,pathlib
root=pathlib.Path(sys.prefix).resolve()
for m in (cv2,numpy):
 p=pathlib.Path(m.__file__).resolve()
 assert p.is_relative_to(root),'dependency outside runtime: '+str(p)
print('dependencies OK')`
	cmd := exec.CommandContext(ctx, python, "-I", "-c", code)
	cmd.Env = PythonEnv()
	out, err := cmd.CombinedOutput()
	if err != nil {
		return false, probeFailure(ctx, "分析依赖导入", out, err)
	}
	return true, ""
}
func probeFailure(ctx context.Context, label string, out []byte, err error) string {
	detail := strings.TrimSpace(string(out))
	r := []rune(detail)
	if len(r) > 4000 {
		detail = string(r[len(r)-4000:])
	}
	if ctx.Err() != nil {
		return fmt.Sprintf("%s超时或取消（首次启动和 ARM 模拟可能较慢）：%v\n%s", label, ctx.Err(), detail)
	}
	hint := ""
	var exit *exec.ExitError
	if errors.As(err, &exit) {
		switch uint32(exit.ExitCode()) {
		case 0xc000001d:
			hint = "\n检测到非法指令：可能是 x64 推理库与 ARM 模拟不兼容，请提供 Windows 版本和虚拟机信息。"
		case 0xc0000135:
			hint = "\n系统报告无法加载 DLL，请展开详情，不要从不明网站下载 DLL。"
		}
	}
	return fmt.Sprintf("%s失败：%v%s\n%s", label, err, hint, detail)
}
