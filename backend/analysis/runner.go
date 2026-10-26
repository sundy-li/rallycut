package analysis

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"rallycut/backend/media"
	"rallycut/backend/project"
	"rallycut/vision"
)

const ProtocolVersion = 1
const Model = "blurball-pretrained-v1"
const ClassicalModel = "classical-av-v1"
const WeightsSHA256 = "3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f"

type Request struct {
	ProtocolVersion int     `json:"protocol_version"`
	Type            string  `json:"type"`
	JobID           string  `json:"job_id"`
	VideoPath       string  `json:"video_path"`
	AudioPath       string  `json:"audio_path,omitempty"`
	Duration        float64 `json:"duration"`
	Config          struct {
		Detector string `json:"detector"`
	} `json:"config"`
}

type Result struct {
	ProtocolVersion int                      `json:"protocol_version"`
	Model           string                   `json:"model"`
	Rallies         []project.Rally          `json:"rallies"`
	Tracks          []project.BallTrack      `json:"tracks"`
	Summary         *project.AnalysisSummary `json:"summary,omitempty"`
}

type Event struct {
	ProtocolVersion  int                  `json:"protocol_version"`
	JobID            string               `json:"job_id"`
	Type             string               `json:"type"`
	Progress         float64              `json:"progress"`
	Message          string               `json:"message"`
	Result           *Result              `json:"result,omitempty"`
	Performance      *project.Performance `json:"performance,omitempty"`
	Rallies          []project.Rally      `json:"rallies,omitempty"`
	Tracks           []project.BallTrack  `json:"tracks,omitempty"`
	TableBounds      []float64            `json:"table_bounds"`
	ProcessedSeconds float64              `json:"processed_seconds,omitempty"`
}

// Stream is one provisional snapshot emitted while frames are still being
// analysed: rallies found so far, tracks finished since the last snapshot and
// the calibrated table box.
type Stream struct {
	JobID            string
	Rallies          []project.Rally
	Tracks           []project.BallTrack
	TableBounds      []float64
	ProcessedSeconds float64
}

func CacheKey(fingerprint string) string {
	sum := sha256.Sum256([]byte(fmt.Sprintf("%d:%s:%s:%s", ProtocolVersion, Model+":"+WeightsSHA256, vision.Digest(), fingerprint)))
	return hex.EncodeToString(sum[:])
}

// Capped stderr avoids unbounded memory consumption from a broken worker.
type cappedBuffer struct{ bytes.Buffer }

func (b *cappedBuffer) Write(p []byte) (int, error) {
	n := len(p)
	if b.Len() < 8192 {
		limit := 8192 - b.Len()
		if len(p) > limit {
			p = p[:limit]
		}
		_, _ = b.Buffer.Write(p)
	}
	return n, nil
}

func Run(ctx context.Context, python, worker string, v project.Video, progress func(float64, string)) (*Result, error) {
	return RunWithModel(ctx, python, worker, v, Model, progress)
}

// Classical analysis remains explicit for comparisons/tests, never an automatic fallback.
func RunWithModel(ctx context.Context, python, worker string, v project.Video, model string, progress func(float64, string)) (*Result, error) {
	return runObserved(ctx, python, worker, v, model, progress, nil, nil)
}

func RunObserved(ctx context.Context, python, worker string, v project.Video, progress func(float64, string), performance func(*project.Performance)) (*Result, error) {
	return runObserved(ctx, python, worker, v, Model, progress, performance, nil)
}

// RunStreaming reports provisional rallies while frames are still being
// analysed, so the UI can play finished parts before the run completes.
func RunStreaming(ctx context.Context, python, worker string, v project.Video, progress func(float64, string), performance func(*project.Performance), partial func(Stream)) (*Result, error) {
	return runObserved(ctx, python, worker, v, Model, progress, performance, partial)
}

func runObserved(ctx context.Context, python, worker string, v project.Video, model string, progress func(float64, string), performance func(*project.Performance), partial func(Stream)) (*Result, error) {
	if model != Model && model != ClassicalModel {
		return nil, fmt.Errorf("不支持的检测器 %q", model)
	}
	req := Request{ProtocolVersion: ProtocolVersion, Type: "analyze", JobID: project.NewID(), VideoPath: v.Path, Duration: v.Duration}
	req.Config.Detector = model
	if v.HasAudio {
		progress(.01, "提取本地音频，检测击球声瞬态")
		f, err := os.CreateTemp("", "rallycut-analysis-*.wav")
		if err != nil {
			return nil, err
		}
		path := f.Name()
		_ = f.Close()
		defer os.Remove(path)
		audio := exec.CommandContext(ctx, media.Binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", v.Path, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", path)
		var log cappedBuffer
		audio.Stderr = &log
		if err := audio.Run(); err != nil {
			if ctx.Err() != nil {
				return nil, ctx.Err()
			}
			return nil, fmt.Errorf("分析音轨提取失败: %w; %s", err, log.String())
		}
		req.AudioPath = path
	}
	data, _ := json.Marshal(req)
	cmd := exec.CommandContext(ctx, python, "-u", worker)
	cmd.Stdin = bytes.NewReader(append(data, '\n'))
	var stderr cappedBuffer
	cmd.Stderr = &stderr
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("Python 启动失败: %w", err)
	}
	result, parseErr := parseObserved(stdout, req.JobID, v.Duration, progress, performance, partial)
	if parseErr == nil && result.Model != model {
		parseErr = fmt.Errorf("返回的检测器与请求不一致")
	}
	if parseErr != nil && cmd.Process != nil {
		_ = cmd.Process.Kill()
	}
	waitErr := cmd.Wait()
	if ctx.Err() != nil {
		return nil, ctx.Err()
	}
	if parseErr != nil {
		return nil, parseErr
	}
	if waitErr != nil {
		return nil, fmt.Errorf("算法进程退出: %w; %s", waitErr, stderr.String())
	}
	return result, nil
}

func Validate(r *Result, duration float64) error {
	if r == nil || r.ProtocolVersion != ProtocolVersion || (r.Model != Model && r.Model != ClassicalModel) {
		return fmt.Errorf("算法结果版本无效")
	}
	if err := project.ValidateRallyEvents(r.Summary, duration); err != nil {
		return err
	}
	if r.Summary != nil {
		if err := project.ValidateTableSegments(r.Summary.TableSegments, duration); err != nil {
			return err
		}
		if r.Summary.CameraCuts < 0 {
			return fmt.Errorf("无效镜头切换计数")
		}
	}
	if err := project.ValidateRallies(r.Rallies, duration); err != nil {
		return err
	}
	if err := project.ValidateTracks(r.Tracks, duration); err != nil {
		return err
	}
	if r.Summary == nil || r.Summary.Method != r.Model || r.Summary.DecodedFrames < 1 || r.Summary.TrackCount != len(r.Tracks) || !project.Finite(r.Summary.ElapsedSeconds) || r.Summary.ElapsedSeconds < 0 {
		return fmt.Errorf("算法分析摘要无效")
	}
	if r.Summary.CalibrationJumpBudget < 0 || r.Summary.CalibrationJumpBudget > 384 || r.Summary.CalibrationJumpSamples < 0 || r.Summary.CalibrationJumpSamples > r.Summary.CalibrationJumpBudget || r.Summary.CalibrationJumpWindows < 0 || r.Summary.CalibrationJumpWindows > 128 {
		return fmt.Errorf("无效球桌跳搜计数")
	}
	if !project.Finite(r.Summary.CalibrationSearchExtentSeconds) || r.Summary.CalibrationSearchExtentSeconds < 0 || r.Summary.CalibrationSearchExtentSeconds > duration+.25 {
		return fmt.Errorf("无效球桌跳搜范围")
	}
	for _, value := range []float64{r.Summary.ProcessingFPS, r.Summary.AnalysisFPS} {
		if !project.Finite(value) || value < 0 {
			return fmt.Errorf("无效分析 FPS")
		}
	}
	if r.Summary.HardwareDecode && r.Summary.Decoder != "videotoolbox" {
		return fmt.Errorf("硬件解码来源不匹配")
	}
	if r.Model == Model && r.Summary.WeightsSHA256 != WeightsSHA256 {
		return fmt.Errorf("预训练权重来源不匹配")
	}
	if len(r.Rallies) > 0 && len(r.Tracks) == 0 {
		return fmt.Errorf("回合结果缺少轨迹证据")
	}
	if r.Summary.TableMode != "" && r.Summary.TableMode != "optional" && r.Summary.TableMode != "off" && r.Summary.TableMode != "precalibrate" {
		return fmt.Errorf("未知球桌辅助模式")
	}
	return project.ValidateTableBounds(r.Summary.TableBounds)
}

func Parse(reader io.Reader, jobID string, duration float64, progress func(float64, string)) (*Result, error) {
	return parseObserved(reader, jobID, duration, progress, nil, nil)
}

func parseObserved(reader io.Reader, jobID string, duration float64, progress func(float64, string), performance func(*project.Performance), partial func(Stream)) (*Result, error) {
	scan := bufio.NewScanner(reader)
	scan.Buffer(make([]byte, 4096), 32<<20)
	var result *Result
	for scan.Scan() {
		var e Event
		if err := json.Unmarshal(scan.Bytes(), &e); err != nil {
			return nil, fmt.Errorf("算法协议 JSON 无效: %w", err)
		}
		if e.ProtocolVersion != ProtocolVersion || e.JobID != jobID {
			return nil, fmt.Errorf("算法协议版本或 job_id 不匹配")
		}
		if result != nil {
			return nil, fmt.Errorf("result 必须是最后一个事件")
		}
		switch e.Type {
		case "progress":
			if !project.Finite(e.Progress) || e.Progress < 0 || e.Progress > 1 {
				return nil, fmt.Errorf("算法进度无效")
			}
			if err := e.Performance.Validate(); err != nil {
				return nil, err
			}
			if performance != nil && e.Performance != nil {
				performance(e.Performance)
			}
			progress(e.Progress, e.Message)
		case "candidates":
			if partial == nil {
				continue
			}
			if len(e.Rallies) == 0 && len(e.Tracks) == 0 && e.TableBounds == nil {
				continue
			}
			if err := project.ValidateTableBounds(e.TableBounds); err != nil {
				return nil, err
			}
			if err := project.ValidateTracks(e.Tracks, duration); err != nil {
				return nil, err
			}
			// A provisional segment clipped at the analysis frontier is not
			// fatal: forward the overlay data but drop the incoherent rallies.
			if len(e.Rallies) > 0 && project.ValidateRallies(e.Rallies, duration) != nil {
				e.Rallies = nil
			}
			partial(Stream{JobID: e.JobID, Rallies: e.Rallies, Tracks: e.Tracks,
				TableBounds: e.TableBounds, ProcessedSeconds: e.ProcessedSeconds})
		case "result":
			if e.Result == nil || e.Result.ProtocolVersion != ProtocolVersion || (e.Result.Model != Model && e.Result.Model != ClassicalModel) {
				return nil, fmt.Errorf("算法结果版本无效")
			}
			if err := Validate(e.Result, duration); err != nil {
				return nil, err
			}
			result = e.Result
		case "error":
			return nil, fmt.Errorf("算法错误: %s", e.Message)
		default:
			return nil, fmt.Errorf("未知算法事件 %q", e.Type)
		}
	}
	if err := scan.Err(); err != nil {
		return nil, err
	}
	if result == nil {
		return nil, fmt.Errorf("算法进程未输出 result")
	}
	return result, nil
}
