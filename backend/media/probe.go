package media

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"rallycut/backend/project"
	"rallycut/backend/runtimeenv"
	"runtime"
	"strconv"
	"strings"
	"time"
)

func Binary(name string) string { return BinaryFor(os.Getenv("RALLYCUT_DATA_DIR"), name) }

// BinaryFor finds app-managed tools even when Finder / Explorer supplies no PATH.
func BinaryFor(dataDir, name string) string {
	if p := os.Getenv("RALLYCUT_" + strings.ToUpper(name)); p != "" {
		return p
	}
	if dataDir != "" && (name == "ffmpeg" || name == "ffprobe") {
		if active := runtimeenv.Root(dataDir); active != "" {
			return filepath.Join(active, "bin", name+".exe")
		}
		file := name
		if runtime.GOOS == "windows" {
			file += ".exe"
		}
		p := filepath.Join(dataDir, "runtime", "bin", file)
		if info, err := os.Stat(p); err == nil && !info.IsDir() {
			return p
		}
	}
	if p, err := exec.LookPath(name); err == nil {
		return p
	}
	for _, dir := range []string{"/opt/homebrew/bin", "/usr/local/bin"} {
		p := filepath.Join(dir, name)
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return name
}

// Hash the entire source once: cache identity must not rely on a file name or FPS.
func Fingerprint(ctx context.Context, path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	buf := make([]byte, 1<<20)
	for {
		if err := ctx.Err(); err != nil {
			return "", err
		}
		n, e := f.Read(buf)
		if n > 0 {
			_, _ = h.Write(buf[:n])
		}
		if e == io.EOF {
			break
		}
		if e != nil {
			return "", e
		}
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func Probe(ctx context.Context, path string) (project.Video, error) {
	var v project.Video
	abs, err := filepath.Abs(path)
	if err != nil {
		return v, err
	}
	info, err := os.Stat(abs)
	if err != nil {
		return v, err
	}
	if !info.Mode().IsRegular() {
		return v, fmt.Errorf("请选择普通视频文件")
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, Binary("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", abs).Output()
	if err != nil {
		return v, fmt.Errorf("ffprobe 读取失败（请检查 FFmpeg 安装或文件格式）: %w", err)
	}
	var data struct {
		Streams []struct {
			CodecType string            `json:"codec_type"`
			CodecName string            `json:"codec_name"`
			Width     int               `json:"width"`
			Height    int               `json:"height"`
			FPS       string            `json:"avg_frame_rate"`
			Duration  string            `json:"duration"`
			BitRate   string            `json:"bit_rate"`
			Tags      map[string]string `json:"tags"`
			SideData  []struct {
				Rotation int `json:"rotation"`
			} `json:"side_data_list"`
		} `json:"streams"`
		Format struct {
			Duration string `json:"duration"`
		} `json:"format"`
	}
	if err := json.Unmarshal(out, &data); err != nil {
		return v, err
	}
	v.Path = abs
	v.Name = filepath.Base(abs)
	v.Duration, _ = strconv.ParseFloat(data.Format.Duration, 64)
	for _, s := range data.Streams {
		if s.CodecType == "audio" {
			v.HasAudio = true
		}
		if s.CodecType == "video" && v.Width == 0 {
			v.Width, v.Height, v.Codec = s.Width, s.Height, s.CodecName
			v.BitRate, _ = strconv.ParseInt(s.BitRate, 10, 64)
			bits := strings.Split(s.FPS, "/")
			if len(bits) == 2 {
				a, _ := strconv.ParseFloat(bits[0], 64)
				b, _ := strconv.ParseFloat(bits[1], 64)
				if b > 0 {
					v.FPS = a / b
				}
			}
			if v.Duration <= 0 {
				v.Duration, _ = strconv.ParseFloat(s.Duration, 64)
			}
			v.Rotation, _ = strconv.Atoi(s.Tags["rotate"])
			for _, side := range s.SideData {
				v.Rotation = side.Rotation
			}
		}
	}
	if v.Width <= 0 || v.Height <= 0 || !project.Finite(v.Duration) || v.Duration <= 0 {
		return v, fmt.Errorf("未找到有效视频轨道或时长")
	}
	// Hashing is deliberately outside the probe deadline.
	return v, nil
}

func Inspect(ctx context.Context, path string) (project.Video, error) {
	v, err := Probe(ctx, path)
	if err != nil {
		return v, err
	}
	v.Fingerprint, err = Fingerprint(ctx, v.Path)
	return v, err
}
