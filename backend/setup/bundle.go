package setup

import (
	"archive/zip"
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"rallycut/backend/analysis"
	"rallycut/backend/runtimeenv"
	"rallycut/backend/storage"
)

// The release builder replaces this catalog with hashes of its own verified
// portable runtime. The source checkout intentionally has no executable pin.
//
//go:embed runtime-bundle.json
var embeddedBundle []byte

type BundleSpec struct {
	ID             string `json:"id"`
	Filename       string `json:"filename"`
	URL            string `json:"url,omitempty"`
	SHA256         string `json:"sha256"`
	ManifestSHA256 string `json:"manifest_sha256"`
	Bytes          int64  `json:"bytes"`
	InstalledBytes int64  `json:"installed_bytes"`
}
type bundleFile struct {
	SHA256 string `json:"sha256"`
	Bytes  int64  `json:"bytes"`
}
type bundleManifest struct {
	ID       string                `json:"id"`
	Platform string                `json:"platform"`
	Files    map[string]bundleFile `json:"files"`
}

func (p *Provisioner) bundleSpec() *BundleSpec {
	if p.options.Bundle != nil {
		return p.options.Bundle
	}
	var c struct {
		Platforms map[string]BundleSpec `json:"platforms"`
	}
	if json.Unmarshal(embeddedBundle, &c) != nil {
		return nil
	}
	if s, ok := c.Platforms[runtime.GOOS+"/"+runtime.GOARCH]; ok {
		return &s
	}
	return nil
}
func (s BundleSpec) validate() error {
	if !runtimeenv.SafeName(s.ID) || !runtimeenv.SafeName(s.Filename) || len(s.SHA256) != 64 || len(s.ManifestSHA256) != 64 || s.Bytes <= 0 || s.InstalledBytes <= 0 {
		return fmt.Errorf("预制环境清单无效")
	}
	return nil
}
func safeBundlePath(name string) bool {
	return name != "" && !strings.Contains(name, "\\") && !strings.Contains(name, ":") && !strings.HasPrefix(name, "/") && filepath.ToSlash(filepath.Clean(name)) == name && name != ".." && !strings.HasPrefix(name, "../")
}
func verifyBundleFiles(ctx context.Context, root string, s BundleSpec) error {
	manifestPath := filepath.Join(root, "bundle-manifest.json")
	if info, err := os.Stat(manifestPath); err != nil || info.Size() > 16<<20 {
		return fmt.Errorf("预制环境缺少有效的文件清单")
	}
	got, err := fileSHA256(manifestPath)
	if err != nil || got != s.ManifestSHA256 {
		return fmt.Errorf("预制环境文件清单校验失败")
	}
	data, err := os.ReadFile(manifestPath)
	if err != nil {
		return err
	}
	var m bundleManifest
	if json.Unmarshal(data, &m) != nil || m.ID != s.ID || m.Platform != "windows/amd64" || len(m.Files) == 0 {
		return fmt.Errorf("预制环境版本或平台不符")
	}
	for _, name := range []string{"python/python.exe", "bin/ffmpeg.exe", "bin/ffprobe.exe"} {
		if _, ok := m.Files[name]; !ok {
			return fmt.Errorf("环境清单缺少 %s", name)
		}
	}
	for name, expected := range m.Files {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if !safeBundlePath(name) {
			return fmt.Errorf("环境清单含非法路径")
		}
		path := filepath.Join(root, filepath.FromSlash(name))
		info, err := os.Lstat(path)
		if err != nil || !info.Mode().IsRegular() || info.Size() != expected.Bytes {
			return fmt.Errorf("环境文件大小不符：%s", name)
		}
		got, err := fileSHA256(path)
		if err != nil || got != expected.SHA256 {
			return fmt.Errorf("环境文件校验失败：%s", name)
		}
	}
	return nil
}
func extractBundle(ctx context.Context, archive, root string, s BundleSpec) error {
	z, err := zip.OpenReader(archive)
	if err != nil {
		return err
	}
	defer z.Close()
	seen := map[string]bool{}
	var written int64
	for _, entry := range z.File {
		if err := ctx.Err(); err != nil {
			return err
		}
		name := entry.Name
		if entry.FileInfo().IsDir() {
			continue
		}
		// Case-insensitive duplicate detection is required on Windows.
		lower := strings.ToLower(name)
		if !safeBundlePath(name) || seen[lower] || !entry.Mode().IsRegular() || strings.Contains(name, "\x00") {
			return fmt.Errorf("预制环境压缩包包含非法文件：%s", name)
		}
		seen[lower] = true
		if entry.UncompressedSize64 > uint64(s.InstalledBytes) || written > s.InstalledBytes-int64(entry.UncompressedSize64) {
			return fmt.Errorf("环境解压大小超出清单")
		}
		dest := filepath.Join(root, filepath.FromSlash(name))
		if err := os.MkdirAll(filepath.Dir(dest), 0700); err != nil {
			return err
		}
		src, err := entry.Open()
		if err != nil {
			return err
		}
		dst, err := os.OpenFile(dest, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err != nil {
			src.Close()
			return err
		}
		n, e := io.Copy(dst, io.LimitReader(src, int64(entry.UncompressedSize64)+1))
		closeErr := dst.Close()
		src.Close()
		if e != nil {
			return e
		}
		if closeErr != nil {
			return closeErr
		}
		if n != int64(entry.UncompressedSize64) {
			return fmt.Errorf("环境解压大小不符")
		}
		written += n
	}
	return verifyBundleFiles(ctx, root, s)
}
func bundleLocalPath(s BundleSpec) string {
	exe, err := os.Executable()
	if err != nil {
		return ""
	}
	for _, name := range []string{"runtime-payload.zip", s.Filename} {
		p := filepath.Join(filepath.Dir(exe), name)
		if info, err := os.Stat(p); err == nil && !info.IsDir() {
			return p
		}
	}
	return ""
}
func (p *Provisioner) expandedRoot() string {
	if p.options.InstalledRoot != "" {
		return p.options.InstalledRoot
	}
	return runtimeenv.Installed()
}
func checkReady(checks []CheckItem, id string) bool {
	for _, c := range checks {
		if c.ID == id {
			return c.Ready
		}
	}
	return false
}
func runtimeChecksReady(checks []CheckItem) bool {
	return checkReady(checks, "python") && checkReady(checks, "media") && checkReady(checks, "packages")
}
func (p *Provisioner) verifyRuntime(ctx context.Context, root string, s BundleSpec) error {
	p.update(.10, "python", "检查已安装的运行环境…", "无需下载或重新安装 Python 包")
	if err := verifyBundleFiles(ctx, root, s); err != nil {
		return err
	}
	python := filepath.Join(root, "python", "python.exe")
	if ok, detail := analysis.PythonDetail(python); !ok {
		return fmt.Errorf("已安装依赖自检失败：%s", detail)
	}
	for _, tool := range []string{"ffmpeg", "ffprobe"} {
		if !commandWorks(ctx, filepath.Join(root, "bin", tool+".exe"), "-version") {
			return fmt.Errorf("已安装视频工具自检失败：%s", tool)
		}
	}
	if err := p.ensureWeights(ctx); err != nil {
		return err
	}
	p.mu.Lock()
	p.state.Checks = []CheckItem{{ID: "python", Ready: true}, {ID: "media", Ready: true}, {ID: "packages", Ready: true}, {ID: "model", Ready: true}, {ID: "verify", Ready: false}}
	p.mu.Unlock()
	p.update(.96, "verify", "执行模型运行自检…", "首次 ARM 模拟加载可能较慢，请等待")
	p.setIndeterminate(true)
	defer p.setIndeterminate(false)
	if ok, detail := analysis.ModelDetailContext(ctx, python, p.options.Worker, p.options.DataDir); !ok {
		return fmt.Errorf("环境已安装，但模型运行自检未通过\n%s", detail)
	}
	return nil
}
func (p *Provisioner) provisionBundle(ctx context.Context, s BundleSpec) (string, error) {
	if err := s.validate(); err != nil {
		return "", err
	}
	if root := p.expandedRoot(); root != "" {
		if err := p.verifyRuntime(ctx, root, s); err != nil {
			return "", err
		}
		return filepath.Join(root, "python", "python.exe"), nil
	}
	if err := os.MkdirAll(p.runtimeDir(), 0700); err != nil {
		return "", err
	}
	need := s.InstalledBytes + s.Bytes + (512 << 20)
	if err := checkFreeSpace(p.runtimeDir(), need); err != nil {
		return "", err
	}
	p.update(.04, "python", "准备预制环境包…", "不在你的电脑上运行 pip 安装")
	archive := p.options.BundlePath
	if archive == "" {
		archive = bundleLocalPath(s)
	}
	if archive == "" {
		if !strings.HasPrefix(s.URL, "https://") {
			return "", fmt.Errorf("未找到预制环境包。请使用完整安装器，或把 %s 与免安装 EXE 放在同一目录。私有 GitHub 不支持匿名下载。", s.Filename)
		}
		archive = filepath.Join(p.runtimeDir(), "downloads", s.SHA256+".zip")
		err := downloadResumable(ctx, &http.Client{Timeout: 30 * time.Minute}, s.URL, archive, s.Bytes, s.SHA256, func(done, total int64) {
			p.update(.04+.60*float64(done)/float64(total), "python", "下载预制环境包（支持续传）…", fmt.Sprintf("%.1f / %.1f MB", mb(done), mb(total)))
		})
		if err != nil {
			return "", err
		}
	}
	p.update(.65, "media", "校验并解压环境包…", "")
	got, err := fileSHA256(archive)
	if err != nil || got != s.SHA256 {
		return "", fmt.Errorf("预制环境包 SHA-256 不符，未修改现有环境")
	}
	info, err := os.Stat(archive)
	if err != nil || info.Size() != s.Bytes {
		return "", fmt.Errorf("预制环境包大小不符")
	}
	return p.installBundle(ctx, archive, s, func(root string) error {
		p.update(.82, "packages", "检查预制分析依赖…", "")
		python := filepath.Join(root, "python", "python.exe")
		if ok, detail := analysis.PythonDetail(python); !ok {
			return fmt.Errorf("预制依赖自检失败：%s", detail)
		}
		for _, tool := range []string{"ffmpeg", "ffprobe"} {
			if !commandWorks(ctx, filepath.Join(root, "bin", tool+".exe"), "-version") {
				return fmt.Errorf("预制视频工具自检失败：%s", tool)
			}
		}
		if err := p.ensureWeights(ctx); err != nil {
			return err
		}
		p.update(.96, "verify", "加载模型并执行一次 CPU 推理…", "首次加载和 ARM 模拟可能较慢，请等待")
		p.setIndeterminate(true)
		defer p.setIndeterminate(false)
		if ok, detail := analysis.ModelDetailContext(ctx, python, p.options.Worker, p.options.DataDir); !ok {
			return fmt.Errorf("环境自检未通过：视觉模型\n%s", detail)
		}
		return nil
	})
}

// The old active pointer remains untouched throughout extraction, hash checking
// and real self-test. Only a fully verified version is atomically activated.
func (p *Provisioner) installBundle(ctx context.Context, archive string, s BundleSpec, verify func(string) error) (string, error) {
	versions := filepath.Join(p.runtimeDir(), "versions")
	if err := os.MkdirAll(versions, 0700); err != nil {
		return "", err
	}
	candidate, err := os.MkdirTemp(versions, s.ID+"-")
	if err != nil {
		return "", err
	}
	committed := false
	defer func() {
		if !committed {
			_ = os.RemoveAll(candidate)
		}
	}()
	if err := extractBundle(ctx, archive, candidate, s); err != nil {
		return "", err
	}
	if err := verify(candidate); err != nil {
		return "", fmt.Errorf("新环境未通过验证，原环境未改动：%w", err)
	}
	if err := ctx.Err(); err != nil {
		return "", err
	}
	active := filepath.Join(p.runtimeDir(), "active.json")
	previous, readErr := os.ReadFile(active)
	if readErr != nil && !os.IsNotExist(readErr) {
		return "", readErr
	}
	if len(previous) > 0 {
		var old runtimeenv.ActiveState
		if json.Unmarshal(previous, &old) == nil {
			if err := storage.WriteJSON(filepath.Join(p.runtimeDir(), "active.previous.json"), old); err != nil {
				return "", err
			}
		}
	}
	state := runtimeenv.ActiveState{ID: s.ID, Directory: filepath.Base(candidate)}
	if err := storage.WriteJSON(active, state); err != nil {
		return "", fmt.Errorf("切换环境失败，旧环境保留：%w", err)
	}
	committed = true
	return filepath.Join(candidate, "python", "python.exe"), nil
}
