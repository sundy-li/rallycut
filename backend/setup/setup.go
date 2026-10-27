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
	"rallycut/backend/runtimeenv"
	"rallycut/models"
	"rallycut/vision"
)

// State is the single source of truth for the first-run setup screen.
type CheckItem struct {
	ID     string `json:"id"`
	Label  string `json:"label"`
	Ready  bool   `json:"ready"`
	Detail string `json:"detail,omitempty"`
}

type State struct {
	Revision      uint64      `json:"revision"`
	Platform      string      `json:"platform"`
	RuntimeMode   string      `json:"runtime_mode,omitempty"`
	Checks        []CheckItem `json:"checks,omitempty"`
	Indeterminate bool        `json:"indeterminate"`
	State         string      `json:"state"` // checking | required | running | ready | failed
	Step          string      `json:"step"`  // check | python | media | packages | model | verify | ready
	Message       string      `json:"message"`
	Detail        string      `json:"detail"`
	Progress      float64     `json:"progress"`
	Error         string      `json:"error,omitempty"`
	Python        string      `json:"python,omitempty"`
	Network       bool        `json:"needs_network"`
}

type Options struct {
	DataDir            string
	Worker             string
	Log                *slog.Logger
	Emit               func(State)
	ForceManagedPython bool        // Fresh-install integration tests must not reuse host Python.
	ForceManagedMedia  bool        // Also exercise FFmpeg / FFprobe downloads on developer machines.
	Bundle             *BundleSpec // A build-pinned portable runtime, never a server-selected executable.
	BundlePath         string      // Explicit local/offline bundle path for release verification.
	InstalledRoot      string      // An expanded installer payload, also injectable by tests.
}

// Provisioner installs and verifies the runtime the worker needs.
type Provisioner struct {
	options Options

	mu       sync.Mutex
	state    State
	running  bool
	revision uint64
	wg       sync.WaitGroup
	run      func(context.Context) (string, error)
	inspect  func(context.Context) (string, []CheckItem)
}

func New(options Options) *Provisioner {
	if options.Log == nil {
		options.Log = slog.Default()
	}
	p := &Provisioner{
		options: options,
		state:   State{State: "checking", Step: "check", Message: "正在检查运行环境…", Indeterminate: true, Platform: platformName()},
	}
	p.run, p.inspect = p.provision, p.inspectRuntime
	return p
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

func (p *Provisioner) snapshotLocked() State {
	p.revision++
	p.state.Revision = p.revision
	p.state.RuntimeMode = "legacy"
	if p.bundleSpec() != nil {
		p.state.RuntimeMode = "bundle"
		if p.expandedRoot() != "" {
			p.state.RuntimeMode = "installed"
		}
	}
	state := p.state
	state.Checks = append([]CheckItem(nil), state.Checks...)
	return state
}

func (p *Provisioner) Status() State {
	p.mu.Lock()
	defer p.mu.Unlock()
	state := p.state
	state.Checks = append([]CheckItem(nil), state.Checks...)
	return state
}

func (p *Provisioner) inspectRuntime(ctx context.Context) (string, []CheckItem) {
	python := analysis.Python(p.options.DataDir)
	root := p.expandedRoot()
	if root != "" {
		python = filepath.Join(root, "python", "python.exe")
	}
	mediaBinary := func(name string) string {
		if root != "" {
			return filepath.Join(root, "bin", name+".exe")
		}
		return p.mediaBinary(name)
	}
	checks := []CheckItem{
		{ID: "python", Label: "Python 运行时", Ready: supportsVenv(python)},
		{ID: "media", Label: "视频处理工具 FFmpeg / FFprobe", Ready: commandWorks(ctx, mediaBinary("ffmpeg"), "-version") && commandWorks(ctx, mediaBinary("ffprobe"), "-version")},
		{ID: "packages", Label: "视觉分析依赖"},
		{ID: "model", Label: "视觉模型"},
	}
	if spec := p.bundleSpec(); spec != nil {
		if root == "" {
			root = runtimeenv.Active(p.options.DataDir)
		}
		if root == "" {
			checks[0].Ready = false
			checks[0].Detail = "需要准备本版预制环境"
		} else if err := verifyBundleFiles(ctx, root, *spec); err != nil {
			checks[0].Ready = false
			checks[0].Detail = err.Error()
		}
	}
	if checks[0].Ready && ctx.Err() == nil {
		checks[2].Ready, checks[2].Detail = analysis.PythonDetail(python)
	}
	weights, weightErr := defaultWeights()
	if weightErr == nil {
		if got, err := fileSHA256(p.weightsPath()); err == nil && strings.EqualFold(got, weights.SHA256) {
			checks[3].Ready = true
		} else {
			checks[3].Detail = "仅缺少模型文件，约 6 MB；下载并校验后继续"
		}
	} else {
		checks[3].Detail = weightErr.Error()
	}
	verify := CheckItem{ID: "verify", Label: "模型加载与运行自检"}
	if checks[0].Ready && checks[1].Ready && checks[2].Ready && checks[3].Ready && ctx.Err() == nil {
		verify.Ready, verify.Detail = analysis.ModelDetailContext(ctx, python, p.options.Worker, p.options.DataDir)
	}
	// Preserve explicit developer/repository model discovery for non-bundled
	// checkouts; installed releases use their own model files and strict pin.
	if p.bundleSpec() == nil && runtimeChecksReady(checks) && !checks[3].Ready && ctx.Err() == nil {
		verify.Ready, verify.Detail = analysis.ModelDetailContext(ctx, python, p.options.Worker, p.options.DataDir)
		if verify.Ready {
			checks[3].Ready = true
			checks[3].Detail = ""
		}
	}
	checks = append(checks, verify)
	return python, checks
}
func allReady(checks []CheckItem) bool {
	if len(checks) == 0 {
		return false
	}
	for _, check := range checks {
		if !check.Ready {
			return false
		}
	}
	return true
}

// Detect never downloads anything. A missing dependency leaves the consent
// screen visible until the user explicitly calls Start.
func (p *Provisioner) Detect(ctx context.Context) {
	p.mu.Lock()
	if p.running {
		p.mu.Unlock()
		return
	}
	p.running = true
	p.state = State{State: "checking", Step: "check", Message: "正在检查运行环境…", Platform: platformName(), Indeterminate: true}
	state := p.snapshotLocked()
	p.wg.Add(1)
	p.mu.Unlock()
	p.emit(state)
	go func() {
		defer p.wg.Done()
		python, checks := p.inspect(ctx)
		p.mu.Lock()
		p.running = false
		p.state = State{State: "required", Step: "check", Message: "首次使用需要准备运行环境", Platform: platformName(), Checks: checks, Network: true}
		if runtimeChecksReady(checks) && !checkReady(checks, "model") {
			p.state.Message = "运行环境已随软件安装，仅需首次下载模型（约 6 MB）"
		}
		if runtimeChecksReady(checks) && checkReady(checks, "model") && !checkReady(checks, "verify") {
			p.state.State = "failed"
			p.state.Step = "verify"
			p.state.Message = "环境已安装，模型运行自检未通过"
			for _, check := range checks {
				if check.ID == "verify" {
					p.state.Error = check.Detail
				}
			}
			p.state.Network = false
		}
		if allReady(checks) && ctx.Err() == nil {
			p.state = State{State: "ready", Step: "ready", Message: "运行环境已就绪", Platform: platformName(), Checks: checks, Python: python, Progress: 1}
		}
		state := p.snapshotLocked()
		p.mu.Unlock()
		if ctx.Err() == nil {
			p.emit(state)
		}
	}()
}
func (p *Provisioner) Wait() { p.wg.Wait() }

func (p *Provisioner) Ready() (string, bool) {
	python, checks := p.inspect(context.Background())
	return python, allReady(checks)
}

func (p *Provisioner) MarkReady(python string) {
	p.setState(State{State: "ready", Step: "ready", Progress: 1, Message: "运行环境已就绪", Python: python})
}

func (p *Provisioner) MarkRequired() {
	p.setState(State{State: "required", Step: "python", Message: "首次启动需要准备运行环境", Network: true})
}

func (p *Provisioner) setState(state State) {
	state.Platform = platformName()
	p.mu.Lock()
	p.state = state
	state = p.snapshotLocked()
	p.mu.Unlock()
	p.emit(state)
}

func (p *Provisioner) emit(state State) {
	if p.options.Emit != nil {
		p.options.Emit(state)
	}
}

// Start only runs after explicit consent. Repeated clicks never start a second job.
func (p *Provisioner) Start(parent context.Context) {
	p.mu.Lock()
	if p.running || p.state.State == "ready" {
		p.mu.Unlock()
		return
	}
	p.running = true
	p.state = State{State: "running", Step: "python", Platform: platformName(), Checks: p.state.Checks, Progress: 0.02, Message: "准备 Python 运行时…", Network: true}
	state := p.snapshotLocked()
	p.wg.Add(1)
	p.mu.Unlock()
	p.emit(state)

	go func() {
		defer p.wg.Done()
		ctx, cancel := context.WithTimeout(parent, time.Hour)
		defer cancel()
		python, err := p.run(ctx)
		p.mu.Lock()
		p.running = false
		switch {
		case err == nil:
			p.state = State{State: "ready", Step: "ready", Progress: 1, Message: "运行环境已就绪", Python: python, Platform: platformName(), Checks: p.state.Checks}
		case parent.Err() != nil:
			p.state.State = "required"
			p.state.Message = "初始化已中断"
			p.state.Error = "已取消，可重试"
		default:
			p.state.State = "failed"
			p.state.Message = "运行环境准备失败（旧环境与项目保留）"
			p.state.Error = err.Error()
			p.options.Log.Error("setup failed", "error", err)
		}
		p.state.Indeterminate = false
		state := p.snapshotLocked()
		p.mu.Unlock()
		if parent.Err() == nil {
			p.emit(state)
		}
	}()
}

func (p *Provisioner) provision(ctx context.Context) (string, error) {
	if spec := p.bundleSpec(); spec != nil {
		return p.provisionBundle(ctx, *spec)
	}
	target, err := p.target()
	if err != nil {
		return "", err
	}
	base, err := p.ensurePython(ctx, target)
	if err != nil {
		return "", err
	}
	p.update(0.16, "python", "创建应用专用 Python 环境…", "")
	if err := p.ensureVenv(ctx, base); err != nil {
		return "", err
	}
	python := venvPython(p.venvDir())
	if err := p.ensureMedia(ctx, target); err != nil {
		return "", fmt.Errorf("准备视频处理工具失败：%w", err)
	}
	if err := p.installPackages(ctx, python); err != nil {
		return "", fmt.Errorf("安装视觉依赖失败：%w", err)
	}
	if err := p.ensureWeights(ctx); err != nil {
		return "", fmt.Errorf("下载模型权重失败：%w", err)
	}
	p.update(0.96, "verify", "检查视频工具、依赖与模型…", "只有全部通过才会进入剪辑界面")
	p.setIndeterminate(true)
	defer p.setIndeterminate(false)
	verifiedPython, checks := p.inspect(ctx)
	p.mu.Lock()
	p.state.Checks = checks
	p.mu.Unlock()
	if !allReady(checks) {
		var missing []string
		for _, check := range checks {
			if !check.Ready {
				missing = append(missing, check.Label+": "+check.Detail)
			}
		}
		return "", fmt.Errorf("环境自检未通过：%s，请重试或联系维护者", strings.Join(missing, "、"))
	}
	return verifiedPython, ctx.Err()
}

func (p *Provisioner) ensureVenv(ctx context.Context, base string) error {
	if commandWorks(ctx, venvPython(p.venvDir()), "-c", "import sys,venv,pip") {
		return nil
	}
	if err := os.RemoveAll(p.venvDir()); err != nil {
		return err
	}
	p.update(0.18, "python", "创建隔离的虚拟环境…", p.venvDir())
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
		data, err := platformRequirements(name, runtime.GOOS, runtime.GOARCH)
		if err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(p.runtimeDir(), name), data, 0600); err != nil {
			return err
		}
	}
	if err := p.pip(ctx, python, 0.45, 0.56, "安装基础依赖 numpy / OpenCV", filepath.Join(p.runtimeDir(), names[0])); err != nil {
		return err
	}
	return p.pip(ctx, python, 0.56, 0.82, "安装推理依赖 PyTorch（首次下载较大）", filepath.Join(p.runtimeDir(), names[1]))
}

func platformRequirements(name, goos, arch string) ([]byte, error) {
	data, err := vision.Requirements.ReadFile(name)
	if err != nil {
		return nil, err
	}
	// PyTorch stopped publishing Intel macOS wheels after 2.2.x. Its last
	// Python 3.12 build also requires NumPy 1.x for the NumPy bridge.
	if goos == "darwin" && arch == "amd64" {
		data = bytes.ReplaceAll(data, []byte("numpy==2.2.6"), []byte("numpy==1.26.4"))
		data = bytes.ReplaceAll(data, []byte("torch==2.8.0"), []byte("torch==2.2.2"))
	}
	if name == "requirements-model.txt" && goos == "windows" {
		extra, err := vision.Requirements.ReadFile("requirements-windows.txt")
		if err != nil {
			return nil, err
		}
		data = append(append(data, '\n'), extra...)
	}
	return data, nil
}

func (p *Provisioner) pip(ctx context.Context, python string, from, to float64, label, requirements string) error {
	p.update(from, "packages", label, "")
	p.setIndeterminate(true)
	defer p.setIndeterminate(false)
	args := []string{"-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--progress-bar", "off", "-r", requirements}
	cmd := exec.CommandContext(ctx, python, args...)
	cmd.Env = append(os.Environ(), "PIP_DISABLE_PIP_VERSION_CHECK=1", "PIP_CACHE_DIR="+filepath.Join(p.runtimeDir(), "cache", "pip"), "PYTHONNOUSERSITE=1")

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
	if w.all.Len() > 16384 {
		keep := append([]byte(nil), w.all.Bytes()[w.all.Len()-8192:]...)
		w.all.Reset()
		w.all.Write(keep)
	}
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
	err = downloadResumable(ctx, &http.Client{Timeout: 30 * time.Minute}, spec.URL, dest, spec.Bytes, spec.SHA256, func(written, total int64) {
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
	client := &http.Client{Timeout: 30 * time.Minute}
	response, err := client.Do(request)
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
	file, err := os.CreateTemp(filepath.Dir(dest), ".download-*")
	if err != nil {
		return err
	}
	temp := file.Name()
	defer func() {
		file.Close()
		_ = os.Remove(temp)
	}()
	reader := &progressReader{reader: response.Body, total: total, onProgress: progress}
	var source io.Reader = reader
	if size > 0 {
		source = io.LimitReader(reader, size+1)
	}
	written, err := io.Copy(file, source)
	if err != nil {
		return err
	}
	if size > 0 && written != size {
		return fmt.Errorf("下载大小不匹配：%d / %d 字节", written, size)
	}
	if err := file.Close(); err != nil {
		return err
	}
	if total > 0 {
		if info, err := os.Stat(temp); err == nil && info.Size() != total {
			return fmt.Errorf("下载不完整：%d / %d 字节", info.Size(), total)
		}
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if runtime.GOOS == "windows" {
		if err := os.Remove(dest); err != nil && !os.IsNotExist(err) {
			return err
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

func (p *Provisioner) setIndeterminate(value bool) {
	p.mu.Lock()
	p.state.Indeterminate = value
	state := p.snapshotLocked()
	p.mu.Unlock()
	p.emit(state)
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
	p.state.Detail = detail
	state := p.snapshotLocked()
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
		candidates = []string{"python3.12", "python3.11", "python3.10", "python", "python3"}
	} else {
		candidates = []string{
			"python3.12", "python3.11", "python3.10", "python3",
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
	// Windows Store app-execution aliases can open the Store instead of running
	// Python. Detection must not trigger an interactive system installation.
	if strings.Contains(strings.ToLower(filepath.ToSlash(strings.ReplaceAll(path, "\\", "/"))), "/microsoft/windowsapps/") {
		return false
	}
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
	return major == 3 && minor >= 10 && minor <= 12
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
