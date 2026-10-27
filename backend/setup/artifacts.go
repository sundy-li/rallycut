package setup

import (
	"archive/tar"
	"archive/zip"
	"compress/gzip"
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"rallycut/backend/media"
)

// Versions, sizes and SHA-256 values are pinned from the upstream release API.
// No shell installers, mutable latest URLs, global PATH or registry changes.
//
//go:embed artifacts.json
var artifactManifest []byte

type artifact struct {
	URL    string `json:"url"`
	SHA256 string `json:"sha256"`
	Bytes  int64  `json:"bytes"`
	Format string `json:"format"`
	Entry  string `json:"entry,omitempty"`
}
type platformArtifacts struct {
	Label   string              `json:"label"`
	UV      artifact            `json:"uv"`
	FFmpeg  artifact            `json:"ffmpeg"`
	FFprobe artifact            `json:"ffprobe"`
	Notices map[string]artifact `json:"notices"`
}
type artifactCatalog struct {
	PythonVersion string                       `json:"python_version"`
	Platforms     map[string]platformArtifacts `json:"platforms"`
}

func catalog() artifactCatalog {
	var result artifactCatalog
	if err := json.Unmarshal(artifactManifest, &result); err != nil {
		panic(err)
	}
	return result
}
func platformName() string {
	if target, ok := catalog().Platforms[runtime.GOOS+"/"+runtime.GOARCH]; ok {
		return target.Label
	}
	return runtime.GOOS + " / " + runtime.GOARCH
}
func (p *Provisioner) target() (platformArtifacts, error) {
	target, ok := catalog().Platforms[runtime.GOOS+"/"+runtime.GOARCH]
	if !ok {
		return target, fmt.Errorf("暂不支持自动准备 %s / %s，请联系维护者", runtime.GOOS, runtime.GOARCH)
	}
	return target, nil
}
func executableName(name string) string {
	if runtime.GOOS == "windows" {
		return name + ".exe"
	}
	return name
}
func (p *Provisioner) ensureArtifact(ctx context.Context, spec artifact, dest string, from, to float64, step, label string) error {
	if spec.Bytes <= 0 || len(spec.SHA256) != 64 || !strings.HasPrefix(spec.URL, "https://github.com/") {
		return fmt.Errorf("无效的固定依赖清单")
	}
	if marker, err := os.ReadFile(dest + ".sha256"); err == nil {
		if digest, err := fileSHA256(dest); err == nil && strings.TrimSpace(string(marker)) == spec.SHA256+":"+digest {
			p.update(to, step, label, "已就绪")
			return nil
		}
	}
	cache := filepath.Join(p.runtimeDir(), "downloads", spec.SHA256)
	if err := os.MkdirAll(filepath.Dir(cache), 0700); err != nil {
		return err
	}
	digest, _ := fileSHA256(cache)
	if digest != spec.SHA256 {
		p.update(from, step, label, "连接下载源…")
		var last time.Time
		if err := download(ctx, spec.URL, cache, spec.Bytes, func(written, total int64) {
			if time.Since(last) < 150*time.Millisecond {
				return
			}
			last = time.Now()
			p.update(from+(to-from)*.9*float64(written)/float64(spec.Bytes), step, label, fmt.Sprintf("%.1f / %.1f MB", mb(written), mb(total)))
		}); err != nil {
			return err
		}
		digest, _ = fileSHA256(cache)
		if digest != spec.SHA256 {
			_ = os.Remove(cache)
			return fmt.Errorf("下载校验失败，未执行文件；请重试")
		}
	}
	if err := os.MkdirAll(filepath.Dir(dest), 0700); err != nil {
		return err
	}
	if err := unpackArtifact(ctx, cache, spec, dest); err != nil {
		return err
	}
	digest, err := fileSHA256(dest)
	if err != nil {
		return err
	}
	if err := os.WriteFile(dest+".sha256", []byte(spec.SHA256+":"+digest), 0600); err != nil {
		return err
	}
	p.update(to, step, label, "下载与校验完成")
	return nil
}

// Only the requested regular file is extracted. Paths, links and decompressed
// sizes are checked even though the compressed archive is also hash-verified.
func unpackArtifact(ctx context.Context, archive string, spec artifact, dest string) error {
	const maxBinary = 256 << 20
	if err := ctx.Err(); err != nil {
		return err
	}
	out, err := os.CreateTemp(filepath.Dir(dest), ".install-*")
	if err != nil {
		return err
	}
	defer func() { out.Close(); _ = os.Remove(out.Name()) }()
	copyFile := func(reader io.Reader) error {
		n, err := io.Copy(out, io.LimitReader(reader, maxBinary+1))
		if err != nil {
			return err
		}
		if n == 0 || n > maxBinary {
			return fmt.Errorf("依赖文件为空或超出大小限制")
		}
		return ctx.Err()
	}
	validEntry := func(name string) bool {
		clean := path.Clean(name)
		return !strings.Contains(name, "\\") && !path.IsAbs(name) && clean != ".." && !strings.HasPrefix(clean, "../") && path.Base(clean) == spec.Entry
	}
	switch spec.Format {
	case "zip":
		z, err := zip.OpenReader(archive)
		if err != nil {
			return err
		}
		defer z.Close()
		found := false
		for _, f := range z.File {
			if !validEntry(f.Name) {
				continue
			}
			if found || !f.Mode().IsRegular() {
				return fmt.Errorf("依赖压缩包含无效的可执行文件")
			}
			found = true
			r, err := f.Open()
			if err != nil {
				return err
			}
			err = copyFile(r)
			r.Close()
			if err != nil {
				return err
			}
		}
		if !found {
			return fmt.Errorf("依赖压缩包缺少 %s", spec.Entry)
		}
	case "tar.gz", "gz":
		f, err := os.Open(archive)
		if err != nil {
			return err
		}
		defer f.Close()
		g, err := gzip.NewReader(f)
		if err != nil {
			return err
		}
		defer g.Close()
		if spec.Format == "gz" {
			if err := copyFile(g); err != nil {
				return err
			}
		} else {
			t := tar.NewReader(g)
			found := false
			for {
				h, err := t.Next()
				if err == io.EOF {
					break
				}
				if err != nil {
					return err
				}
				if !validEntry(h.Name) {
					continue
				}
				if found || (h.Typeflag != tar.TypeReg && h.Typeflag != tar.TypeRegA) {
					return fmt.Errorf("依赖压缩包含无效的可执行文件")
				}
				found = true
				if err := copyFile(t); err != nil {
					return err
				}
			}
			if !found {
				return fmt.Errorf("依赖压缩包缺少 %s", spec.Entry)
			}
		}
	case "file":
		f, err := os.Open(archive)
		if err != nil {
			return err
		}
		defer f.Close()
		if err := copyFile(f); err != nil {
			return err
		}
	default:
		return fmt.Errorf("不支持的依赖格式")
	}
	mode := os.FileMode(0755)
	if spec.Format == "file" {
		mode = 0600
	}
	if err := out.Chmod(mode); err != nil {
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}
	// Windows Rename cannot replace an existing file. This directory belongs to
	// the application, and no runtime task starts before provisioning succeeds.
	if err := os.Remove(dest); err != nil && !os.IsNotExist(err) {
		return err
	}
	return os.Rename(out.Name(), dest)
}

func (p *Provisioner) ensurePython(ctx context.Context, target platformArtifacts) (string, error) {
	if base := p.managedPython(); base != "" && supportsVenv(base) {
		return base, nil
	}
	if !p.options.ForceManagedPython {
		if base, err := FindPython(); err == nil {
			p.update(.15, "python", "复用兼容的 Python", base)
			return base, nil
		}
	}
	uv := filepath.Join(p.runtimeDir(), "tools", executableName("uv"))
	if err := p.ensureArtifact(ctx, target.UV, uv, .03, .10, "python", "下载环境准备工具…"); err != nil {
		return "", err
	}
	p.update(.10, "python", "下载独立 Python 运行时…", "仅安装到 RallyCut 的私有目录，不修改系统")
	p.setIndeterminate(true)
	defer p.setIndeterminate(false)
	cmd := exec.CommandContext(ctx, uv, "python", "install", catalog().PythonVersion, "--install-dir", filepath.Join(p.runtimeDir(), "python"), "--no-bin", "--no-registry", "--no-config", "--no-progress", "--color", "never")
	cmd.Env = append(os.Environ(), "UV_CACHE_DIR="+filepath.Join(p.runtimeDir(), "cache", "uv"), "UV_NATIVE_TLS=true", "UV_PYTHON_INSTALL_REGISTRY=0")
	writer := &lineWriter{onLine: func(line string) { p.update(.10, "python", "下载独立 Python 运行时…", truncate(line, 180)) }}
	cmd.Stdout, cmd.Stderr = writer, writer
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("Python 准备失败：%s", tail(writer.text(), 500))
	}
	base := p.managedPython()
	if base == "" || !supportsVenv(base) {
		return "", fmt.Errorf("独立 Python 安装后自检失败")
	}
	p.update(.15, "python", "Python 运行时已就绪", "")
	return base, nil
}
func (p *Provisioner) managedPython() string {
	pattern := filepath.Join(p.runtimeDir(), "python", "cpython-"+catalog().PythonVersion+"-*", "bin", "python3.12")
	if runtime.GOOS == "windows" {
		pattern = filepath.Join(p.runtimeDir(), "python", "cpython-"+catalog().PythonVersion+"-*", "python.exe")
	}
	paths, _ := filepath.Glob(pattern)
	if len(paths) > 0 {
		return paths[0]
	}
	return ""
}
func (p *Provisioner) ensureMedia(ctx context.Context, target platformArtifacts) error {
	for i, item := range []struct {
		name string
		spec artifact
	}{{"ffmpeg", target.FFmpeg}, {"ffprobe", target.FFprobe}} {
		from := .23 + float64(i)*.10
		// Prefer a working explicit/system installation when available. Once a
		// managed binary exists, media.Binary chooses that consistently.
		if !p.options.ForceManagedMedia && commandWorks(ctx, p.mediaBinary(item.name), "-version") {
			p.update(from+.10, "media", item.name+" 已就绪", "")
			continue
		}
		dest := filepath.Join(p.runtimeDir(), "bin", executableName(item.name))
		if err := p.ensureArtifact(ctx, item.spec, dest, from, from+.10, "media", "下载视频工具 "+item.name+"…"); err != nil {
			return err
		}
		if !commandWorks(ctx, dest, "-version") {
			return fmt.Errorf("%s 下载后无法运行，请检查系统拦截提示", item.name)
		}
	}
	for name, spec := range target.Notices {
		if filepath.Base(name) != name {
			return fmt.Errorf("无效的许可文件名")
		}
		if err := p.ensureArtifact(ctx, spec, filepath.Join(p.runtimeDir(), "notices", name), .43, .44, "media", "保存视频工具来源与许可证…"); err != nil {
			return err
		}
	}
	return nil
}
func (p *Provisioner) mediaBinary(name string) string {
	return media.BinaryFor(p.options.DataDir, name)
}

func commandWorks(ctx context.Context, binary string, args ...string) bool {
	check, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	return exec.CommandContext(check, binary, args...).Run() == nil
}
