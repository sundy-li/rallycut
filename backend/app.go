package backend

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"sync"
	"time"

	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
	"rallycut/backend/analysis"
	exporter "rallycut/backend/export"
	"rallycut/backend/jobs"
	"rallycut/backend/media"
	"rallycut/backend/project"
	setupenv "rallycut/backend/setup"
	"rallycut/backend/storage"
	"rallycut/backend/timeline"
	"rallycut/vision"
)

type State struct {
	Project      *project.Project `json:"project"`
	ProjectPath  string           `json:"project_path"`
	Dependencies map[string]bool  `json:"dependencies"`
	Error        string           `json:"error"`
	Setup        setupenv.State   `json:"setup"`
	CanUndo      bool             `json:"can_undo"`
	CanRedo      bool             `json:"can_redo"`
}

type App struct {
	ctx          context.Context
	cancel       context.CancelFunc
	opMu         sync.Mutex
	mu           sync.RWMutex
	current      *project.Project
	history      timelineHistory
	recentMu     sync.Mutex
	recentSeeded bool
	projectPath  string
	dataDir      string
	worker       string
	initError    string
	python       string
	visionReady  bool
	modelReady   bool
	modelError   string
	manager      jobs.Manager
	setup        *setupenv.Provisioner
	log          *slog.Logger
	logFile      *os.File
}

func NewApp() *App { return &App{log: slog.Default()} }

func (a *App) Startup(ctx context.Context) {
	a.ctx, a.cancel = context.WithCancel(ctx)
	dir, err := os.UserConfigDir()
	if err != nil {
		a.initError = err.Error()
		return
	}
	a.dataDir = filepath.Join(dir, "RallyCut")
	if override := os.Getenv("RALLYCUT_DATA_DIR"); override != "" {
		a.dataDir = override
	}
	// Python helpers resolve weights through this; Windows has no hardcoded path.
	_ = os.Setenv("RALLYCUT_DATA_DIR", a.dataDir)
	if err = os.MkdirAll(a.dataDir, 0700); err != nil {
		a.initError = err.Error()
		return
	}
	if f, e := os.OpenFile(filepath.Join(a.dataDir, "rallycut.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600); e == nil {
		a.logFile = f
		a.log = slog.New(slog.NewJSONHandler(f, nil))
	}
	a.worker, err = vision.Install(filepath.Join(a.dataDir, "workers", analysis.Model+"-"+vision.Digest()[:16]))
	a.python = analysis.Python(a.dataDir)
	a.visionReady = analysis.CheckPython(a.python)
	if err == nil {
		a.modelReady, a.modelError = analysis.ModelDetail(a.python, a.worker)
	}
	if a.log != nil {
		a.log.Info("environment check", "python", a.python, "worker", a.worker, "vision_ready", a.visionReady, "model_ready", a.modelReady, "model_error", a.modelError)
	}
	if err != nil {
		a.initError = err.Error()
		return
	}
	a.setup = setupenv.New(setupenv.Options{
		DataDir: a.dataDir,
		Worker:  a.worker,
		Log:     a.log,
		Emit: func(state setupenv.State) {
			if state.State == "ready" && state.Python != "" {
				a.mu.Lock()
				a.python = state.Python
				a.visionReady = true
				a.modelReady = true
				a.modelError = ""
				a.mu.Unlock()
			}
			if a.ctx != nil {
				wruntime.EventsEmit(a.ctx, "setup:progress", state)
			}
		},
	})
	if python, ok := a.setup.Ready(); ok {
		a.python = python
		a.visionReady, a.modelReady = true, true
		a.setup.MarkReady(python)
	} else if a.visionReady && a.modelReady {
		// A developer checkout with a complete .venv needs no provisioning.
		a.setup.MarkReady(a.python)
	} else {
		a.setup.MarkRequired()
		go a.setup.Start(a.ctx)
	}
	var last struct {
		Path string `json:"path"`
	}
	if err = storage.ReadJSON(filepath.Join(a.dataDir, "last-project.json"), &last); err == nil && last.Path != "" {
		if !isProjectFilePath(last.Path) {
			a.log.Info("legacy project format ignored", "path", last.Path)
		} else {
			p, e := storage.Load(last.Path)
			if e != nil {
				a.initError = "上次项目恢复失败: " + e.Error()
			} else {
				adopted := p.AdoptAnalysisCandidatesIfEmpty()
				p.SyncActive()
				if adopted {
					if e := storage.WriteJSON(last.Path, p); e != nil {
						a.initError = "空时间轴自动采用机器候选后保存失败: " + e.Error()
					}
				}
				a.current = p
				a.projectPath = last.Path
				a.rememberProject(last.Path, p, false)
			}
		}
	}
	a.log.Info("application started", "data_dir", a.dataDir, "worker_digest", vision.Digest(), "python", a.python)
}

func (a *App) Shutdown(context.Context) {
	if a.cancel != nil {
		a.cancel()
	}
	a.manager.Cancel()
	a.manager.Wait()
	if a.logFile != nil {
		_ = a.logFile.Close()
	}
}

func (a *App) GetState() State {
	a.mu.RLock()
	defer a.mu.RUnlock()
	deps := map[string]bool{}
	for _, name := range []string{"ffmpeg", "ffprobe", "python3"} {
		_, err := exec.LookPath(media.Binary(name))
		deps[name] = err == nil
	}
	deps["opencv_numpy"] = a.visionReady
	deps["blurball_weights_torch"] = a.modelReady
	state := State{Project: project.Clone(a.current), ProjectPath: a.projectPath, Dependencies: deps, Error: a.initError, CanUndo: a.current != nil && len(a.history.undo) > 0, CanRedo: a.current != nil && len(a.history.redo) > 0}
	if a.setup != nil {
		state.Setup = a.setup.Status()
	} else {
		state.Setup = setupenv.State{State: "ready", Progress: 1}
	}
	return state
}

// RefreshDependencies re-runs the Python and model probes so a transient
// failure (slow torch import, freshly installed weights) can be retried
// without restarting the app.
func (a *App) RefreshDependencies() State {
	a.mu.RLock()
	python, worker := a.python, a.worker
	a.mu.RUnlock()
	if python != "" && worker != "" {
		visionReady := analysis.CheckPython(python)
		var modelReady bool
		var modelError string
		if visionReady {
			modelReady, modelError = analysis.ModelDetail(python, worker)
		}
		a.mu.Lock()
		a.visionReady, a.modelReady, a.modelError = visionReady, modelReady, modelError
		a.mu.Unlock()
		if a.log != nil {
			a.log.Info("environment recheck", "python", python, "vision_ready", visionReady, "model_ready", modelReady, "model_error", modelError)
		}
	}
	return a.GetState()
}

func (a *App) ready() error {
	if a.ctx == nil || a.dataDir == "" || a.worker == "" {
		return fmt.Errorf("应用尚未初始化")
	}
	if a.setup != nil && a.setup.Status().State != "ready" {
		return fmt.Errorf("运行环境尚未准备好，请等待初始化完成")
	}
	if a.manager.Busy() {
		return fmt.Errorf("请先等待或取消当前任务")
	}
	return nil
}

func (a *App) persistLocked() error {
	a.current.SyncActive()
	a.current.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	if err := storage.WriteJSON(a.projectPath, a.current); err != nil {
		return err
	}
	a.rememberProject(a.projectPath, a.current, false)
	return nil
}

func (a *App) install(p *project.Project, path string) error {
	path = filepath.Clean(path)
	if !isProjectFilePath(path) {
		return fmt.Errorf("项目文件必须使用 *%s 后缀", projectFileSuffix)
	}
	p.AdoptAnalysisCandidatesIfEmpty()
	p.SyncActive()
	if err := storage.WriteJSON(path, p); err != nil {
		return err
	}
	a.mu.Lock()
	if a.current == nil || a.current.ID != p.ID {
		a.clearHistoryLocked()
	}
	a.current = p
	a.projectPath = path
	a.mu.Unlock()
	if err := storage.WriteJSON(filepath.Join(a.dataDir, "last-project.json"), map[string]string{"path": path}); err != nil {
		a.log.Error("save recent project", "error", err)
	}
	a.rememberProject(path, p, true)
	return nil
}

func (a *App) ImportVideo() (*project.Project, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if err := a.ready(); err != nil {
		return nil, err
	}
	path, err := wruntime.OpenFileDialog(a.ctx, wruntime.OpenDialogOptions{Title: "导入比赛视频", Filters: []wruntime.FileFilter{{DisplayName: "视频文件", Pattern: "*.mp4;*.mov;*.mkv;*.m4v;*.avi;*.webm"}}})
	if err != nil || path == "" {
		return nil, err
	}
	return a.importPath(path)
}

// dedupeVideos drops clips already present by absolute path or by content
// fingerprint, so re-selecting the same file (or a copy of it) is a no-op.
func dedupeVideos(existing []project.Source, candidates []project.Video) []project.Video {
	seen := make(map[string]bool, len(existing)*2)
	for _, source := range existing {
		if source.Video.Path != "" {
			seen["path:"+filepath.Clean(source.Video.Path)] = true
		}
		if source.Video.Fingerprint != "" {
			seen["fp:"+source.Video.Fingerprint] = true
		}
	}
	unique := make([]project.Video, 0, len(candidates))
	for _, video := range candidates {
		pathKey := "path:" + filepath.Clean(video.Path)
		fingerprintKey := "fp:" + video.Fingerprint
		if seen[pathKey] || (video.Fingerprint != "" && seen[fingerprintKey]) {
			continue
		}
		seen[pathKey] = true
		if video.Fingerprint != "" {
			seen[fingerprintKey] = true
		}
		unique = append(unique, video)
	}
	return unique
}

// CreateProject always starts a new project with the caller-provided name,
// then asks for its video clips. A cancelled picker creates nothing.
func (a *App) CreateProject(name string) (*project.Project, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if err := a.ready(); err != nil {
		return nil, err
	}
	name = normalizeProjectName(name)
	paths := media.PickVideos(a.ctx)
	if len(paths) == 0 {
		return nil, nil
	}
	candidates := make([]project.Video, 0, len(paths))
	for _, path := range paths {
		v, err := media.Inspect(a.ctx, path)
		if err != nil {
			return nil, err
		}
		candidates = append(candidates, v)
	}
	videos := dedupeVideos(nil, candidates)
	if len(videos) == 0 {
		return nil, fmt.Errorf("选择的视频均重复，未创建项目")
	}
	p := project.New(videos[0])
	p.Name = name
	first := ""
	for _, v := range videos[1:] {
		id := p.AddSource(v)
		if first == "" {
			first = id
		}
	}
	if first != "" {
		p.ActivateSource(first)
	}
	path := a.internalProjectPath(p)
	if err := a.install(p, path); err != nil {
		return nil, err
	}
	a.log.Info("project created", "project_id", p.ID, "name", p.Name, "videos", len(videos))
	return project.Clone(p), nil
}

// ImportVideos appends one or more clips to the current project (or starts a
// project from the first clip). Native multi-select is used when available.
func (a *App) ImportVideos() (*project.Project, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if err := a.ready(); err != nil {
		return nil, err
	}
	paths := media.PickVideos(a.ctx)
	a.mu.RLock()
	current := project.Clone(a.current)
	a.mu.RUnlock()
	if len(paths) == 0 {
		return current, nil
	}
	candidates := make([]project.Video, 0, len(paths))
	for _, path := range paths {
		v, err := media.Inspect(a.ctx, path)
		if err != nil {
			return nil, err
		}
		candidates = append(candidates, v)
	}
	existing := []project.Source(nil)
	if current != nil {
		existing = current.Sources
	}
	videos := dedupeVideos(existing, candidates)
	if len(videos) == 0 {
		a.log.Info("duplicate videos skipped", "selected", len(paths))
		return current, nil
	}
	created := false
	if current == nil {
		current = project.New(videos[0])
		videos = videos[1:]
		created = true
	}
	first := ""
	for _, v := range videos {
		id := current.AddSource(v)
		if first == "" {
			first = id
		}
	}
	if first != "" {
		current.ActivateSource(first)
	}
	if created {
		path := a.internalProjectPath(current)
		if err := a.install(current, path); err != nil {
			return nil, err
		}
	} else {
		a.mu.Lock()
		a.current = current
		a.clearHistoryLocked()
		err := a.persistLocked()
		a.mu.Unlock()
		if err != nil {
			return nil, err
		}
	}
	a.log.Info("videos imported", "count", len(paths))
	return project.Clone(current), nil
}

// SelectSource switches the active clip without touching the project layout.
func (a *App) SelectSource(id string) (*project.Project, error) {
	return a.mutate(func(p *project.Project) error {
		if !p.ActivateSource(id) {
			return fmt.Errorf("素材不存在")
		}
		return nil
	})
}

// ReorderSources applies the drag-and-drop order; export follows it.
func (a *App) ReorderSources(ids []string) (*project.Project, error) {
	return a.mutate(func(p *project.Project) error {
		return p.ReorderSources(ids)
	})
}

// RemoveSource drops a clip from the project.
func (a *App) RemoveSource(id string) (*project.Project, error) {
	return a.mutate(func(p *project.Project) error {
		return p.RemoveSource(id)
	})
}

func (a *App) importPath(path string) (*project.Project, error) {
	v, err := media.Inspect(a.ctx, path)
	if err != nil {
		return nil, err
	}
	p := project.New(v)
	path = a.internalProjectPath(p)
	if err := a.install(p, path); err != nil {
		return nil, err
	}
	a.log.Info("video imported", "project_id", p.ID)
	return project.Clone(p), nil
}

func (a *App) openProjectPath(path string) (*project.Project, error) {
	if !isProjectFilePath(path) {
		return nil, fmt.Errorf("请选择 *%s 项目文件", projectFileSuffix)
	}
	p, err := storage.Load(path)
	if err != nil {
		return nil, err
	}
	p.SyncActive()
	// A moved/replaced original must not silently inherit old boundaries.
	v, err := media.Inspect(a.ctx, p.Video.Path)
	if err != nil {
		return nil, fmt.Errorf("原视频不可用: %w", err)
	}
	if v.Fingerprint != p.Video.Fingerprint {
		return nil, fmt.Errorf("原视频内容变化，请重新导入")
	}
	if err := a.install(p, path); err != nil {
		return nil, err
	}
	return project.Clone(p), nil
}

// OpenProject asks for an arbitrary project file. Opening records it in the
// local recent list so it appears on the start page next time.
func (a *App) OpenProject() (*project.Project, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if err := a.ready(); err != nil {
		return nil, err
	}
	path, err := wruntime.OpenFileDialog(a.ctx, wruntime.OpenDialogOptions{Title: "打开 RallyCut 项目", Filters: projectFileFilters()})
	if err != nil || path == "" {
		return nil, err
	}
	return a.openProjectPath(path)
}

// OpenRecentProject opens an item from the start-page list without showing a
// second file dialog.
func (a *App) OpenRecentProject(path string) (*project.Project, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if err := a.ready(); err != nil {
		return nil, err
	}
	path = cleanProjectPath(path)
	if path == "" {
		return nil, fmt.Errorf("项目路径为空")
	}
	a.recentMu.Lock()
	entries := a.readRecentLocked()
	allowed := findRecent(entries, path) >= 0
	a.recentMu.Unlock()
	if !allowed {
		return nil, fmt.Errorf("项目不在最近项目列表中，请通过“打开项目文件”选择")
	}
	return a.openProjectPath(path)
}

// DeleteProject removes only the project metadata file. It never traverses
// Video.Path or any source media referenced by the project.
func (a *App) DeleteProject(path string) error {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	path = cleanProjectPath(path)
	if path == "" || !isProjectFilePath(path) {
		return fmt.Errorf("项目路径无效")
	}
	if a.manager.Busy() {
		return fmt.Errorf("分析或导出进行中，暂时不能删除项目")
	}
	a.mu.RLock()
	isCurrent := cleanProjectPath(a.projectPath) == path
	a.mu.RUnlock()
	a.recentMu.Lock()
	entries := a.readRecentLocked()
	known := findRecent(entries, path) >= 0
	a.recentMu.Unlock()
	if !isCurrent && !known {
		return fmt.Errorf("项目不在最近项目列表中")
	}
	if info, err := os.Stat(path); err == nil {
		if !info.Mode().IsRegular() {
			return fmt.Errorf("项目路径不是文件")
		}
		if _, err := readRecentProjectFile(path); err != nil {
			return fmt.Errorf("项目文件校验失败，未删除: %w", err)
		}
		if err := os.Remove(path); err != nil {
			return fmt.Errorf("删除项目文件失败: %w", err)
		}
	} else if !os.IsNotExist(err) {
		return fmt.Errorf("读取项目文件失败: %w", err)
	}
	a.recentMu.Lock()
	entries = a.readRecentLocked()
	if index := findRecent(entries, path); index >= 0 {
		entries = append(entries[:index], entries[index+1:]...)
		a.writeRecentLocked(entries)
	}
	a.recentMu.Unlock()
	if isCurrent {
		a.mu.Lock()
		if cleanProjectPath(a.projectPath) == path {
			a.current = nil
			a.clearHistoryLocked()
			a.projectPath = ""
		}
		a.mu.Unlock()
		_ = os.Remove(filepath.Join(a.dataDir, "last-project.json"))
	}
	if a.log != nil {
		a.log.Info("project metadata deleted", "path", path, "media_untouched", true)
	}
	return nil
}

// RenameProject updates the current project's independent name and keeps the
// -rallycut.json filename in sync. Source videos are never renamed or moved.
func (a *App) RenameProject(name string) (*project.Project, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if a.manager.Busy() {
		return nil, fmt.Errorf("分析或导出进行中，暂时不能重命名项目")
	}
	name = normalizeProjectName(name)
	a.mu.RLock()
	current := project.Clone(a.current)
	oldPath := cleanProjectPath(a.projectPath)
	a.mu.RUnlock()
	if current == nil || oldPath == "" {
		return nil, fmt.Errorf("当前没有打开的项目")
	}
	if name == current.Name {
		return current, nil
	}
	dir := filepath.Dir(oldPath)
	target := oldPath
	if filepath.Base(oldPath) != projectFileBase(name)+projectFileSuffix {
		target = uniqueProjectPath(dir, projectFileBase(name))
	}
	if target == oldPath {
		current.Name = name
	} else {
		if _, err := os.Stat(oldPath); err != nil {
			return nil, fmt.Errorf("项目文件不可用: %w", err)
		}
		if err := os.Rename(oldPath, target); err != nil {
			return nil, fmt.Errorf("重命名项目文件失败: %w", err)
		}
		current.Name = projectNameFromPath(target)
	}
	current.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	if err := a.install(current, target); err != nil {
		if target != oldPath {
			_ = os.Rename(target, oldPath)
		}
		return nil, err
	}
	if target != oldPath {
		a.forgetRecentProject(oldPath)
	}
	return project.Clone(current), nil
}

func (a *App) SaveProjectAs() (string, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if err := a.ready(); err != nil {
		return "", err
	}
	a.mu.RLock()
	p := project.Clone(a.current)
	a.mu.RUnlock()
	if p == nil {
		return "", fmt.Errorf("请先导入视频")
	}
	defaultName := projectFileBase(p.Name) + projectFileSuffix
	path, err := wruntime.SaveFileDialog(a.ctx, wruntime.SaveDialogOptions{Title: "项目另存为", DefaultFilename: defaultName, Filters: projectFileFilters()})
	if err != nil || path == "" {
		return "", err
	}
	path = normalizeProjectFilePath(path)
	if filepath.Clean(path) == filepath.Clean(p.Video.Path) {
		return "", fmt.Errorf("不能覆盖原视频")
	}
	if name := projectNameFromPath(path); name != "" {
		p.Name = name
	}
	if err := a.install(p, path); err != nil {
		return "", err
	}
	return path, nil
}

func (a *App) mutate(fn func(*project.Project) error) (*project.Project, error) {
	return a.mutateWith(false, fn)
}

// mutateRecorded applies a user cutting edit and makes it undoable.
func (a *App) mutateRecorded(fn func(*project.Project) error) (*project.Project, error) {
	return a.mutateWith(true, fn)
}

func (a *App) mutateWith(record bool, fn func(*project.Project) error) (*project.Project, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if err := a.ready(); err != nil {
		return nil, err
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.current == nil {
		return nil, fmt.Errorf("请先导入视频")
	}
	before := snapshotTimeline(a.current)
	beforeSource := a.current.ActiveSourceID
	next := project.Clone(a.current)
	if err := fn(next); err != nil {
		return nil, err
	}
	next.AdoptAnalysisCandidatesIfEmpty()
	next.SyncActive()
	if err := next.Validate(); err != nil {
		return nil, err
	}
	next.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	if err := storage.WriteJSON(a.projectPath, next); err != nil {
		return nil, err
	}
	if record {
		a.recordLocked(before, next)
	} else if next.ActiveSourceID != beforeSource {
		a.clearHistoryLocked()
	}
	a.current = next
	a.rememberProject(a.projectPath, next, false)
	return project.Clone(next), nil
}

func (a *App) UpdateTimeline(rs []project.Rally, rules project.Rules) (*project.Project, error) {
	return a.mutateRecorded(func(p *project.Project) error {
		next := append([]project.Rally{}, rs...)
		previous := map[string]project.Rally{}
		for _, r := range p.Rallies {
			previous[r.ID] = r
		}
		for i := range next {
			if old, ok := previous[next[i].ID]; ok {
				if next[i].End != old.End {
					next[i].EndReason = ""
					next[i].EndEventTime = 0
					next[i].EndConfidence = 0
				}
				if next[i].Start != old.Start {
					next[i].BoundaryBefore = false
					next[i].StartReason = ""
				}
			}
		}
		project.Sort(next)
		if !slices.Equal(p.Rallies, next) {
			p.ManualTimeline = true
		}
		p.Rallies = next
		p.Rules = rules
		return nil
	})
}
func (a *App) SetExportSettings(settings project.ExportSettings) (*project.Project, error) {
	return a.mutate(func(p *project.Project) error {
		p.ExportSettings = settings.Normalized()
		return project.ValidateExport(settings)
	})
}

func (a *App) SplitRally(id string, at float64) (*project.Project, error) {
	return a.mutateRecorded(func(p *project.Project) error {
		rs, err := timeline.Split(p.Rallies, id, at)
		if err != nil {
			return err
		}
		p.Rallies = rs
		p.ManualTimeline = true
		return nil
	})
}
func (a *App) MergeRallies(ids []string) (*project.Project, error) {
	return a.mutateRecorded(func(p *project.Project) error {
		rs, err := timeline.Merge(p.Rallies, ids)
		if err != nil {
			return err
		}
		p.Rallies = rs
		p.ManualTimeline = true
		return nil
	})
}

// streamEvent stamps worker overlays with the manager's job id, which is the id
// the UI shows; the worker's own request id would never match.
func (a *App) streamEvent(update analysis.Stream) streamUpdate {
	return streamUpdate{
		JobID:            a.manager.CurrentID(),
		Tracks:           update.Tracks,
		TableBounds:      update.TableBounds,
		ProcessedSeconds: update.ProcessedSeconds,
	}
}

// keepPartialRallies stores the rounds recognised before a cancelled run.
func (a *App) keepPartialRallies(rallies []project.Rally) {
	if len(rallies) == 0 {
		return
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.current == nil || (a.current.ManualTimeline && len(a.current.Rallies) > 0) {
		return
	}
	next := project.Clone(a.current)
	next.Rallies = append([]project.Rally(nil), rallies...)
	next.ManualTimeline = false
	next.PartialAnalysis = true
	a.clearHistoryLocked()
	if next.Job != nil {
		next.AnalysisID = next.Job.ID
	}
	next.AnalysisRuntime = vision.Digest()
	if next.Job != nil {
		saved := *next.Job
		saved.Candidates, saved.ProcessedSeconds = nil, 0
		next.Job = &saved
	}
	if err := storage.WriteJSON(a.projectPath, next); err != nil {
		a.log.Error("persist partial analysis", "error", err)
		return
	}
	a.current = next
}

// streamUpdate carries overlay deltas (new tracks + calibrated table box) to
// the UI while an analysis job is running. Tracks are never persisted.
type streamUpdate struct {
	JobID            string              `json:"job_id"`
	Tracks           []project.BallTrack `json:"tracks,omitempty"`
	TableBounds      []float64           `json:"table_bounds"`
	ProcessedSeconds float64             `json:"processed_seconds,omitempty"`
}

func (a *App) notify(j project.Job) {
	a.mu.Lock()
	if a.current != nil {
		saved := j
		saved.Candidates, saved.ProcessedSeconds = nil, 0
		a.current.Job = &saved
		if err := a.persistLocked(); err != nil {
			a.log.Error("persist job", "error", err)
			j.Message += " · 项目保存失败: " + err.Error()
			a.current.Job = &j
		} else if j.Status == "running" {
			// Keep provisional candidates readable in memory, but never on disk.
			// Once the job ends they are dropped so later saves stay small.
			a.current.Job = &j
		}
	}
	a.mu.Unlock()
	wruntime.EventsEmit(a.ctx, "job:update", j)
	a.log.Info("job update", "job_id", j.ID, "status", j.Status, "message", j.Message)
}

func (a *App) StartAnalysis() (project.Job, error) {
	return a.startAnalysis(true)
}

// StartFreshAnalysis reruns inference without reading the cached result. A
// successful run still replaces the cache entry for future runs.
func (a *App) StartFreshAnalysis() (project.Job, error) {
	return a.startAnalysis(false)
}

func (a *App) startAnalysis(useCache bool) (project.Job, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if err := a.ready(); err != nil {
		return project.Job{}, err
	}
	a.mu.RLock()
	p := project.Clone(a.current)
	a.mu.RUnlock()
	if p == nil {
		return project.Job{}, fmt.Errorf("请先导入视频")
	}
	return a.manager.Start(a.ctx, "analysis", a.notify, func(ctx context.Context, progress func(float64, string)) (string, error) {
		ctx, cancel := context.WithTimeout(ctx, 30*time.Minute)
		defer cancel()
		progress(.01, "校验原视频与分析缓存")
		hash, err := media.Fingerprint(ctx, p.Video.Path)
		if err != nil {
			return "", err
		}
		if hash != p.Video.Fingerprint {
			return "", fmt.Errorf("原视频已变化，请重新导入")
		}
		cache := filepath.Join(a.dataDir, "cache", analysis.CacheKey(hash)+".json")
		var cached analysis.Result
		var result *analysis.Result
		if useCache && storage.ReadJSON(cache, &cached) == nil && analysis.Validate(&cached, p.Video.Duration) == nil && cached.Model == analysis.Model {
			result = &cached
			progress(.9, "已读取视觉分析缓存")
		} else {
			var streamed []project.Rally
			partial := func(update analysis.Stream) {
				if len(update.Rallies) > 0 {
					streamed = append([]project.Rally(nil), update.Rallies...)
				}
				a.manager.UpdateCandidates(update.Rallies, update.ProcessedSeconds)
				if len(update.Tracks) == 0 && update.TableBounds == nil {
					return
				}
				wruntime.EventsEmit(a.ctx, "analysis:stream", a.streamEvent(update))
			}
			result, err = analysis.RunStreaming(ctx, a.python, a.worker, p.Video, progress, a.manager.UpdatePerformance, partial)
			if err != nil {
				// Cancelling mid-run keeps what was already recognised so the
				// user can review and export those rounds.
				if ctx.Err() != nil {
					a.keepPartialRallies(streamed)
				}
				return "", err
			}
			if err = storage.WriteJSON(cache, result); err != nil {
				return "", fmt.Errorf("缓存保存失败: %w", err)
			}
		}
		if err = ctx.Err(); err != nil {
			return "", err
		}
		a.mu.Lock()
		defer a.mu.Unlock()
		next := project.Clone(a.current)
		// Machine rallies are replaced; manually added/corrected rallies survive.
		merge := next.ApplyAnalysis(result.Rallies, result.Model)
		a.log.Info("analysis applied", "kept_human", merge.KeptHuman, "machine", merge.Machine,
			"overlap_human", merge.OverlapHuman, "kept_deselected", merge.KeptDeselected)
		next.Tracks = project.CloneTracks(result.Tracks)
		next.Analysis = result.Summary
		if next.Job != nil {
			next.AnalysisID = next.Job.ID
		}
		next.AnalysisRuntime = vision.Digest()
		if err = storage.WriteJSON(a.projectPath, next); err != nil {
			return "", err
		}
		a.current = next
		a.clearHistoryLocked()
		return "", nil
	})
}

// UseAnalysisCandidates explicitly replaces a non-empty manual timeline. Empty
// timelines are adopted automatically by analysis, mutation, and project loading.
func (a *App) UseAnalysisCandidates() (*project.Project, error) {
	return a.mutateRecorded(func(p *project.Project) error {
		if p.Model != analysis.Model || p.Analysis == nil {
			return fmt.Errorf("请先完成真实视频分析")
		}
		p.Rallies = append([]project.Rally{}, p.RawRallies...)
		p.ManualTimeline = false
		return nil
	})
}

func (a *App) CancelJob() { a.manager.Cancel() }

func (a *App) ExportHighlights() (project.Job, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if err := a.ready(); err != nil {
		return project.Job{}, err
	}
	a.mu.RLock()
	p := project.Clone(a.current)
	a.mu.RUnlock()
	if p == nil {
		return project.Job{}, fmt.Errorf("请先导入视频")
	}
	p.SyncActive()
	for _, source := range p.Sources {
		if _, err := timeline.ExportSegments(source.Rallies, p.Rules, p.ExportSettings, source.Video.Duration); err != nil {
			return project.Job{}, err
		}
	}
	path, err := wruntime.SaveFileDialog(a.ctx, wruntime.SaveDialogOptions{Title: "导出 MP4 集锦（使用新文件名）", DefaultFilename: "RallyCut-highlights.mp4", Filters: []wruntime.FileFilter{{DisplayName: "MP4 视频", Pattern: "*.mp4"}}})
	if err != nil {
		return project.Job{}, err
	}
	if path == "" {
		return project.Job{}, nil
	}
	if filepath.Ext(path) == "" {
		path += ".mp4"
	}
	return a.manager.Start(a.ctx, "export", a.notify, func(ctx context.Context, progress func(float64, string)) (string, error) {
		ctx, cancel := context.WithTimeout(ctx, 4*time.Hour)
		defer cancel()
		err := exporter.Run(ctx, p, path, progress)
		if err != nil {
			return "", err
		}
		return path, nil
	})
}

// exportOutput returns the current project's completed export file. The UI
// never supplies a path, so this binding cannot open arbitrary locations.
func (a *App) exportOutput() (string, error) {
	a.mu.RLock()
	defer a.mu.RUnlock()
	if a.current == nil || a.current.Job == nil {
		return "", fmt.Errorf("没有已完成的导出")
	}
	j := a.current.Job
	if j.Kind != "export" || j.Status != "completed" || j.Output == "" {
		return "", fmt.Errorf("没有已完成的导出")
	}
	return j.Output, nil
}

// RevealExport selects the finished highlight file in Finder / Explorer.
func (a *App) RevealExport() error {
	path, err := a.exportOutput()
	if err != nil {
		return err
	}
	return media.Reveal(a.ctx, path)
}

// Only the active project's source is exposed. http.ServeContent supports range
// requests for native seeking; no arbitrary filesystem path is accepted.
func (a *App) serveHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/media/source" {
		http.NotFound(w, r)
		return
	}
	if r.Method != "GET" && r.Method != "HEAD" {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	a.mu.RLock()
	p := project.Clone(a.current)
	a.mu.RUnlock()
	if p == nil || r.URL.Query().Get("project") != p.ID {
		http.NotFound(w, r)
		return
	}
	f, err := os.Open(p.Video.Path)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		http.Error(w, "video unavailable", 500)
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	http.ServeContent(w, r, info.Name(), info.ModTime(), f)
}

// SetupStatus reports first-run provisioning progress for the setup screen.
func (a *App) SetupStatus() setupenv.State {
	if a.setup == nil {
		return setupenv.State{State: "ready", Progress: 1}
	}
	return a.setup.Status()
}

// StartSetup retries provisioning after a failure.
func (a *App) StartSetup() setupenv.State {
	if a.setup == nil {
		return setupenv.State{State: "ready", Progress: 1}
	}
	a.setup.Start(a.ctx)
	return a.setup.Status()
}
