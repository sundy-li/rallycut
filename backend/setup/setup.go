// Package setup provisions the app-managed Python runtime and model weights.
package setup

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"rallycut/backend/analysis"
	"rallycut/models"
	"rallycut/vision"
)

// State is the single source of truth for the first-run setup screen.
type State struct {
	State    string  `json:"state"` // required | running | ready | failed
	Step     string  `json:"step"`  // python | packages | model | verify | ready
	Message  string  `json:"message"`
	Detail   string  `json:"detail"`
	Progress float64 `json:"progress"`
	Error    string  `json:"error,omitempty"`
	Python   string  `json:"python,omitempty"`
	Network  bool    `json:"needs_network"`
}

type Options struct {
	DataDir string
	Worker  string
	Log     *slog.Logger
	Emit    func(State)
}

// Provisioner installs and verifies the runtime the worker needs.
type Provisioner struct {
	options Options

	mu      sync.Mutex
	state   State
	running bool
}

func New(options Options) *Provisioner {
	if options.Log == nil {
		options.Log = slog.Default()
	}
	return &Provisioner{
		options: options,
		state:   State{State: "required", Step: "python", Message: "等待准备运行环境", Network: true},
	}
}

func (p *Provisioner) runtimeDir() string { return filepath.Join(p.options.DataDir, "runtime") }
func (p *Provisioner) venvDir() string    { return filepath.Join(p.runtimeDir(), "venv") }

// VenvPython is the interpreter path used inside the managed runtime.
func VenvPython(dataDir string) string { return venvPython(filepath.Join(dataDir, "runtime", "venv")) }

func venvPython(dir string) string {
	if runtime.GOOS == "windows" {
		return filepath.Join(dir, "Scripts", "python.exe")
	}
	return filepath.Join(dir, "bin", "python3")
}

func (p *Provisioner) Status() State {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.state
}

// Ready reports whether the managed runtime already satisfies the app.
func (p *Provisioner) Ready() (string, bool) {
	python := venvPython(p.venvDir())
	if _, err := os.Stat(python); err != nil {
		return "", false
	}
	if !analysis.CheckPython(python) {
		return "", false
	}
	if ok, _ := analysis.ModelDetail(python, p.options.Worker); !ok {
		return "", false
	}
	return python, true
}

func (p *Provisioner) MarkReady(python string) {
	p.setState(State{State: "ready", Step: "ready", Progress: 1, Message: "运行环境已就绪", Python: python})
}

func (p *Provisioner) MarkRequired() {
	p.setState(State{State: "required", Step: "python", Message: "首次启动需要准备运行环境", Network: true})
}

func (p *Provisioner) setState(state State) {
	p.mu.Lock()
	p.state = state
	p.mu.Unlock()
	p.emit(state)
}

func (p *Provisioner) emit(state State) {
	if p.options.Emit != nil {
		p.options.Emit(state)
	}
}

// Start provisions the runtime in the background. Repeated calls are no-ops.
func (p *Provisioner) Start(parent context.Context) {
	if python, ok := p.Ready(); ok {
		p.MarkReady(python)
		return
	}
	p.mu.Lock()
	if p.running || p.state.State == "ready" {
		p.mu.Unlock()
		return
	}
	p.running = true
	p.state = State{State: "running", Step: "python", Progress: 0.02, Message: "检查 Python 运行时…", Network: true}
	state := p.state
	p.mu.Unlock()
	p.emit(state)

	go func() {
		python, err := p.provision(parent)
		p.mu.Lock()
		p.running = false
		switch {
		case err == nil:
			p.state = State{State: "ready", Step: "ready", Progress: 1, Message: "运行环境已就绪", Python: python}
		case parent.Err() != nil:
			p.state.State = "required"
			p.state.Message = "初始化已中断"
			p.state.Error = "已取消，可重试"
		default:
			p.state.State = "failed"
			p.state.Message = "运行环境准备失败"
			p.state.Error = err.Error()
			p.options.Log.Error("setup failed", "error", err)
		}
		state := p.state
		p.mu.Unlock()
		p.emit(state)
	}()
}

func (p *Provisioner) provision(ctx context.Context) (string, error) {
	base, err := FindPython()
	if err != nil {
		return "", err
	}
	p.update(0.06, "python", "使用 Python "+base, "")
	if err := p.ensureVenv(ctx, base); err != nil {
		return "", err
	}
	python := venvPython(p.venvDir())
	if err := p.installPackages(ctx, python); err != nil {
		return "", fmt.Errorf("安装视觉依赖失败：%w", err)
	}
	if err := p.ensureWeights(ctx); err != nil {
		return "", fmt.Errorf("下载模型权重失败：%w", err)
	}
	p.update(0.96, "verify", "自检运行环境…", "导入 OpenCV / NumPy / PyTorch")
	if ok, detail := analysis.PythonDetail(python); !ok {
		return "", fmt.Errorf("依赖安装完成，但仍无法导入 OpenCV / NumPy：%s", strings.TrimSpace(detail))
	}
	if ok, detail := analysis.ModelDetail(python, p.options.Worker); !ok {
		return "", fmt.Errorf("模型自检失败：%s", strings.TrimSpace(detail))
	}
	return python, nil
}

func (p *Provisioner) ensureVenv(ctx context.Context, base string) error {
	if _, err := os.Stat(venvPython(p.venvDir())); err == nil {
		return nil
	}
	p.update(0.10, "python", "创建隔离的虚拟环境…", p.venvDir())
	if err := os.MkdirAll(p.runtimeDir(), 0700); err != nil {
		return err
	}
	out, err := exec.CommandContext(ctx, base, "-m", "venv", p.venvDir()).CombinedOutput()
	if err != nil {
		return fmt.Errorf("创建虚拟环境失败：%s", tail(string(out), 400))
	}
	if _, err := os.Stat(venvPython(p.venvDir())); err != nil {
		return errors.New("虚拟环境创建后找不到 Python 解释器")
	}
	return nil
}

func (p *Provisioner) installPackages(ctx context.Context, python string) error {
	names := []string{"requirements.txt", "requirements-model.txt"}
	for _, name := range names {
		data, err := vision.Requirements.ReadFile(name)
		if err != nil {
			return err
		}
		if name == "requirements-model.txt" && runtime.GOOS == "windows" {
			// The ONNX backend needs DirectML on Windows; one pip pass installs both.
			if extra, readErr := vision.Requirements.ReadFile("requirements-windows.txt"); readErr == nil {
				data = append(append(data, '\n'), extra...)
			}
		}
		if err := os.WriteFile(filepath.Join(p.runtimeDir(), name), data, 0600); err != nil {
			return err
		}
	}
	if err := p.pip(ctx, python, 0.12, 0.42, "安装基础依赖 numpy / OpenCV", filepath.Join(p.runtimeDir(), names[0])); err != nil {
		return err
	}
	return p.pip(ctx, python, 0.42, 0.84, "安装推理依赖 PyTorch（首次下载较大）", filepath.Join(p.runtimeDir(), names[1]))
}

func (p *Provisioner) pip(ctx context.Context, python string, from, to float64, label, requirements string) error {
	p.update(from, "packages", label, "")
	args := []string{"-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--progress-bar", "off", "-r", requirements}
	cmd := exec.CommandContext(ctx, python, args...)
	cmd.Env = append(os.Environ(), "PIP_DISABLE_PIP_VERSION_CHECK=1")

	var last time.Time
	writer := &lineWriter{onLine: func(line string) {
		if time.Since(last) < 150*time.Millisecond {
			return
		}
		last = time.Now()
		p.update(from, "packages", label, truncate(line, 160))
	}}
	cmd.Stdout = writer
	cmd.Stderr = writer
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("%s：%s", label, tail(writer.text(), 400))
	}
	p.update(to, "packages", label, "完成")
	return nil
}

type lineWriter struct {
	mu     sync.Mutex
	buf    []byte
	all    bytes.Buffer
	onLine func(string)
}

func (w *lineWriter) Write(data []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.all.Write(data)
	w.buf = append(w.buf, data...)
	for {
		index := bytes.IndexAny(w.buf, "\r\n")
		if index < 0 {
			break
		}
		line := strings.TrimSpace(string(w.buf[:index]))
		w.buf = w.buf[index+1:]
		if line != "" && w.onLine != nil {
			w.onLine(line)
		}
	}
	if len(w.buf) > 8192 {
		w.buf = w.buf[len(w.buf)-8192:]
	}
	return len(data), nil
}

func (w *lineWriter) text() string {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.all.String()
}

type weightsManifest struct {
	Default string `json:"default_detector"`
	Models  []struct {
		ID     string `json:"id"`
		URL    string `json:"weights_url"`
		SHA256 string `json:"weights_sha256"`
		Bytes  int64  `json:"weights_bytes"`
	} `json:"models"`
}

type weightsSpec struct {
	ID     string
	URL    string
	SHA256 string
	Bytes  int64
}

func defaultWeights() (weightsSpec, error) {
	var manifest weightsManifest
	if err := json.Unmarshal(models.Manifest, &manifest); err != nil {
		return weightsSpec{}, err
	}
	for _, model := range manifest.Models {
		if model.URL == "" || (manifest.Default != "" && model.ID != manifest.Default) {
			continue
		}
		return weightsSpec{ID: model.ID, URL: model.URL, SHA256: model.SHA256, Bytes: model.Bytes}, nil
	}
	return weightsSpec{}, errors.New("模型清单里没有可下载的权重")
}

func (p *Provisioner) weightsPath() string {
	// pretrained.locate_weights looks for this exact filename under models/weights.
	return filepath.Join(p.options.DataDir, "models", "weights", "blurball_best.pth")
}

func (p *Provisioner) ensureWeights(ctx context.Context) error {
	spec, err := defaultWeights()
	if err != nil {
		return err
	}
	dest := p.weightsPath()
	if info, statErr := os.Stat(dest); statErr == nil && info.Size() == spec.Bytes {
		if digest, hashErr := fileSHA256(dest); hashErr == nil && strings.EqualFold(digest, spec.SHA256) {
			p.update(0.86, "model", "模型权重已存在", filepath.Base(dest))
			return nil
		}
	}
	if err := os.MkdirAll(filepath.Dir(dest), 0700); err != nil {
		return err
	}
	p.update(0.84, "model", "下载模型权重…", "连接模型源")
	var last time.Time
	err = download(ctx, spec.URL, dest, spec.Bytes, func(written, total int64) {
		if time.Since(last) < 200*time.Millisecond {
			return
		}
		last = time.Now()
		progress := 0.84
		if total > 0 {
			progress += 0.12 * float64(written) / float64(total)
		}
		p.update(progress, "model", "下载模型权重…", fmt.Sprintf("%.1f / %.1f MB", mb(written), mb(total)))
	})
	if err != nil {
		return err
	}
	digest, err := fileSHA256(dest)
	if err != nil {
		return err
	}
	if !strings.EqualFold(digest, spec.SHA256) {
		_ = os.Remove(dest)
		return fmt.Errorf("权重 SHA-256 不匹配（期望 %s，实际 %s）", spec.SHA256[:12], digest[:12])
	}
	return nil
}

func download(ctx context.Context, url, dest string, size int64, progress func(written, total int64)) error {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	request.Header.Set("User-Agent", "RallyCut/1.0")
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("下载失败：HTTP %d", response.StatusCode)
	}
	total := response.ContentLength
	if total <= 0 {
		total = size
	}
	temp := dest + ".part"
	file, err := os.Create(temp)
	if err != nil {
		return err
	}
	defer func() {
		file.Close()
		_ = os.Remove(temp)
	}()
	reader := &progressReader{reader: response.Body, total: total, onProgress: progress}
	if _, err := io.Copy(file, reader); err != nil {
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	if total > 0 {
		if info, err := os.Stat(temp); err == nil && info.Size() != total {
			return fmt.Errorf("下载不完整：%d / %d 字节", info.Size(), total)
		}
	}
	return os.Rename(temp, dest)
}

type progressReader struct {
	reader     io.Reader
	written    int64
	total      int64
	onProgress func(written, total int64)
}

func (r *progressReader) Read(buffer []byte) (int, error) {
	n, err := r.reader.Read(buffer)
	if n > 0 {
		r.written += int64(n)
		if r.onProgress != nil {
			r.onProgress(r.written, r.total)
		}
	}
	return n, err
}

func (p *Provisioner) update(progress float64, step, message, detail string) {
	p.mu.Lock()
	if p.state.State != "running" {
		p.mu.Unlock()
		return
	}
	if progress > p.state.Progress {
		p.state.Progress = mathMin(progress, 0.99)
	}
	if step != "" {
		p.state.Step = step
	}
	if message != "" {
		p.state.Message = message
	}
	if detail != "" {
		p.state.Detail = detail
	}
	state := p.state
	p.mu.Unlock()
	p.emit(state)
}

// FindPython locates a base interpreter that can create virtual environments.
func FindPython() (string, error) {
	var candidates []string
	if runtime.GOOS == "windows" {
		if out, err := exec.Command("py", "-3.12", "-c", "import sys;print(sys.executable)").Output(); err == nil {
			if path := strings.TrimSpace(string(out)); path != "" && supportsVenv(path) {
				return path, nil
			}
		}
		candidates = []string{"python", "python3", "python3.12"}
	} else {
		candidates = []string{
			"python3.12", "python3",
			"/opt/homebrew/bin/python3.12", "/opt/homebrew/bin/python3",
			"/usr/local/bin/python3.12", "/usr/local/bin/python3",
		}
	}
	for _, candidate := range candidates {
		path, err := exec.LookPath(candidate)
		if err != nil {
			path = candidate
			if _, statErr := os.Stat(path); statErr != nil {
				continue
			}
		}
		if supportsVenv(path) {
			return path, nil
		}
	}
	return "", errors.New("未找到可用的 Python 3.10+。请安装 Python 3.12（需包含 venv）后重试")
}

func supportsVenv(path string) bool {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, path, "-c", "import sys,venv;print('%d.%d' % sys.version_info[:2])").Output()
	if err != nil {
		return false
	}
	parts := strings.Split(strings.TrimSpace(string(out)), ".")
	if len(parts) != 2 {
		return false
	}
	major, err := strconv.Atoi(parts[0])
	if err != nil {
		return false
	}
	minor, err := strconv.Atoi(parts[1])
	if err != nil {
		return false
	}
	return major == 3 && minor >= 10
}

func fileSHA256(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func truncate(text string, limit int) string {
	if len(text) <= limit {
		return text
	}
	return text[:limit] + "…"
}

func tail(text string, limit int) string {
	text = strings.TrimSpace(text)
	if len(text) <= limit {
		return text
	}
	return "…" + text[len(text)-limit:]
}

func mb(bytes int64) float64 { return float64(bytes) / (1024 * 1024) }

func mathMin(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}
