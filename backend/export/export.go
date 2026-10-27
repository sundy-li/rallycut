package export

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"rallycut/backend/childproc"
	"rallycut/backend/media"
	"rallycut/backend/project"
	"rallycut/backend/timeline"
	"runtime"
	"strings"
)

type inputSpan struct {
	Path     string
	HasAudio bool
	Span     timeline.Segment
	// Overlay data; Overlay is nil when no burn-in option is enabled.
	Overlay *overlaySpec
}

// collect flattens every source's selected spans in project order. normalize is
// true when more than one source contributes, so all segments share 1080p/30.
func collect(p *project.Project) (jobs []inputSpan, normalize bool, audio bool, fingerprints map[string]string, err error) {
	p.SyncActive()
	sources := p.Sources
	if len(sources) == 0 {
		sources = []project.Source{{Video: p.Video, Rallies: p.Rallies}}
	}
	used := 0
	fingerprints = map[string]string{}
	settings := p.ExportSettings.Normalized()
	for _, source := range sources {
		spans, labels, err := timeline.ExportPlan(source.Rallies, p.Rules, settings, source.Video.Duration)
		if err != nil {
			return nil, false, false, nil, err
		}
		if len(p.Sources) == 0 {
			source.Tracks = p.Tracks
		}
		if len(spans) == 0 {
			continue
		}
		used++
		fingerprints[source.Video.Path] = source.Video.Fingerprint
		if source.Video.HasAudio {
			audio = true
		}
		for k, span := range spans {
			job := inputSpan{Path: source.Video.Path, HasAudio: source.Video.HasAudio, Span: span}
			if settings.ShowTrajectory || settings.ShowRallyLabels {
				spec, err := spanOverlay(source, span, labels[k], settings)
				if err != nil {
					return nil, false, false, nil, err
				}
				job.Overlay = spec
			}
			jobs = append(jobs, job)
		}
	}
	return jobs, used > 1, audio, fingerprints, nil
}

// spanOverlay builds the burn-in layer for one span in the decoded frame
// geometry (90/270° rotation swaps the coded width and height).
func spanOverlay(source project.Source, span timeline.Segment, labels []timeline.Label, settings project.ExportSettings) (*overlaySpec, error) {
	v := source.Video
	w, h := v.Width, v.Height
	if r := ((v.Rotation % 360) + 360) % 360; r == 90 || r == 270 {
		w, h = h, w
	}
	if w <= 0 || h <= 0 {
		return nil, fmt.Errorf("缺少视频尺寸，无法叠加：%s", filepath.Base(v.Path))
	}
	fps := v.FPS
	if !(fps > 0) || fps > 240 {
		fps = 30
	}
	spec := &overlaySpec{Width: w, Height: h, FPS: fps, Start: span.Start, Length: span.End - span.Start}
	if settings.ShowTrajectory {
		for _, track := range source.Tracks {
			if !track.OffPlay && len(track.Points) > 0 && track.Points[0].T <= span.End+trackAfter && track.Points[len(track.Points)-1].T >= span.Start-trackBefore {
				spec.Tracks = append(spec.Tracks, track)
			}
		}
	}
	if settings.ShowRallyLabels {
		face, err := labelFace(h)
		if err != nil {
			return nil, err
		}
		spec.Labels, spec.Face = labels, face
	}
	return spec, nil
}

func Run(ctx context.Context, p *project.Project, output string, progress func(float64, string)) error {
	jobs, normalize, audio, fingerprints, err := collect(p)
	if err != nil {
		return err
	}
	if len(jobs) == 0 {
		return fmt.Errorf("没有选中的回合")
	}
	output, err = filepath.Abs(output)
	if err != nil {
		return err
	}
	if strings.ToLower(filepath.Ext(output)) != ".mp4" {
		return fmt.Errorf("导出文件必须以 .mp4 结尾")
	}
	if _, err := os.Lstat(output); err == nil {
		return fmt.Errorf("目标文件已存在，请使用新文件名（不会覆盖原文件）")
	} else if !os.IsNotExist(err) {
		return err
	}
	// Compare content identity again before rendering possibly replaced sources.
	for path, want := range fingerprints {
		hash, err := media.Fingerprint(ctx, path)
		if err != nil {
			return err
		}
		if hash != want {
			return fmt.Errorf("素材已变化，请重新导入: %s", filepath.Base(path))
		}
	}
	dir, err := os.MkdirTemp(filepath.Dir(output), ".rallycut-export-*")
	if err != nil {
		return err
	}
	defer os.RemoveAll(dir)
	bitrate := p.Video.BitRate
	for _, source := range p.Sources {
		if source.Video.BitRate > bitrate {
			bitrate = source.Video.BitRate
		}
	}
	plans, err := encodingPlans(runtime.GOOS, p.ExportSettings, bitrate)
	if err != nil {
		return err
	}
	var chosen encodingPlan
	for attempt, plan := range plans {
		chosen = plan
		err = encodeSegments(ctx, jobs, dir, plan, normalize, progress)
		if err == nil {
			break
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if attempt == len(plans)-1 {
			return err
		}
		detail := err.Error()
		if len(detail) > 300 {
			detail = detail[:300]
		}
		progress(0, "VideoToolbox 不可用，全部片段重新使用软件编码，避免混合编码拼接："+detail)
	}
	var list strings.Builder
	var expected float64
	for i, job := range jobs {
		fmt.Fprintf(&list, "file 'clip-%06d.mp4'\n", i)
		expected += job.Span.End - job.Span.Start
	}
	if err := os.WriteFile(filepath.Join(dir, "concat.txt"), []byte(list.String()), 0600); err != nil {
		return err
	}
	progress(.9, "合并片段并校验媒体轨道")
	result := filepath.Join(dir, "highlights.mp4")
	// Concat resolves entries as URLs; an absolute Windows path containing '#'
	// can be mistaken for a fragment. Keep its list/input/output names relative
	// to a real Unicode working directory instead of escaping user paths as URLs.
	if err := runWithInputDir(ctx, dir, nil, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "concat", "-safe", "1", "-i", "concat.txt", "-c", "copy", "-movflags", "+faststart", "highlights.mp4"); err != nil {
		return err
	}
	v, err := media.Probe(ctx, result)
	if err != nil {
		return fmt.Errorf("导出校验失败: %w", err)
	}
	tolerance := math.Max(.35, float64(len(jobs))*.10)
	if math.Abs(v.Duration-expected) > tolerance {
		return fmt.Errorf("导出时长校验失败：期望 %.2fs，实际 %.2fs", expected, v.Duration)
	}
	if v.Codec != chosen.Codec {
		return fmt.Errorf("导出编码校验失败：期望 %s，实际 %s", chosen.Codec, v.Codec)
	}
	if audio && !v.HasAudio {
		return fmt.Errorf("导出音轨缺失")
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := publishCompleted(result, output); err != nil {
		return fmt.Errorf("保存导出文件失败（目标可能已存在）: %w", err)
	}
	progress(1, "MP4 已导出；请回放确认音画同步")
	return nil
}

func encodeSegments(ctx context.Context, jobs []inputSpan, dir string, plan encodingPlan, normalize bool, progress func(float64, string)) error {
	for i, job := range jobs {
		if err := ctx.Err(); err != nil {
			return err
		}
		name := fmt.Sprintf("clip-%06d.mp4", i)
		progress(float64(i)/float64(len(jobs)+1), fmt.Sprintf("%s · 编码片段 %d / %d", plan.Name, i+1, len(jobs)))
		args := []string{"-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", fmt.Sprintf("%.6f", job.Span.Start), "-i", job.Path}
		next := 1
		if job.Overlay != nil {
			// Transparent burn-in frames streamed on stdin at the source rate.
			o := job.Overlay
			args = append(args, "-f", "rawvideo", "-pix_fmt", "rgba", "-s", fmt.Sprintf("%dx%d", o.Width, o.Height), "-framerate", fmt.Sprintf("%.6f", o.FPS), "-i", "pipe:0")
			next++
		}
		silent := normalize && !job.HasAudio
		if silent {
			args = append(args, "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000")
		}
		args = append(args, "-t", fmt.Sprintf("%.6f", job.Span.End-job.Span.Start))
		filter := "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,setpts=PTS-STARTPTS"
		if normalize {
			filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,setpts=PTS-STARTPTS"
		}
		if job.Overlay != nil {
			// Composite at source resolution before any scaling, so the layer
			// lines up with the frame the tracks were measured on.
			args = append(args, "-filter_complex", "[0:v:0]setpts=PTS-STARTPTS[base];[1:v]setpts=PTS-STARTPTS,format=rgba[layer];[base][layer]overlay=0:0:eof_action=pass:format=auto,"+filter+"[v]", "-map", "[v]")
		} else {
			args = append(args, "-map", "0:v:0", "-vf", filter)
		}
		if job.HasAudio {
			args = append(args, "-map", "0:a:0?")
		} else if silent {
			args = append(args, "-map", fmt.Sprintf("%d:a:0", next))
		}
		args = append(args, "-sn", "-dn")
		args = append(args, plan.Args...)
		if normalize {
			// Uniform AAC params are required for stream-copy concatenation.
			args = append(args, "-ar", "48000", "-ac", "2")
		}
		args = append(args, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-af", "aresample=async=1:first_pts=0", "-metadata:s:v:0", "rotate=0", "-movflags", "+faststart", filepath.Join(dir, name))
		var feed func(io.Writer) error
		if job.Overlay != nil {
			spec := *job.Overlay
			feed = func(w io.Writer) error { return writeOverlay(ctx, w, spec) }
		}
		if err := runWithInput(ctx, feed, args...); err != nil {
			return fmt.Errorf("片段 %d 导出失败: %w", i+1, err)
		}
	}
	return nil
}

// writeOverlay streams every overlay frame of a span.
func writeOverlay(ctx context.Context, w io.Writer, spec overlaySpec) error {
	r := newOverlayRenderer(spec)
	buffered := bufio.NewWriterSize(w, 1<<20)
	for n := 0; n < spec.frameCount(); n++ {
		if err := ctx.Err(); err != nil {
			return err
		}
		if _, err := buffered.Write(r.frame(n)); err != nil {
			return err
		}
	}
	return buffered.Flush()
}

func run(ctx context.Context, args ...string) error {
	return runWithInput(ctx, nil, args...)
}

// runWithInput runs FFmpeg, optionally feeding stdin from feed. FFmpeg may stop
// reading early once -t is reached; that broken pipe is not an error when
// FFmpeg itself succeeds.
func runWithInput(ctx context.Context, feed func(io.Writer) error, args ...string) error {
	return runWithInputDir(ctx, "", feed, args...)
}
func runWithInputDir(ctx context.Context, dir string, feed func(io.Writer) error, args ...string) error {
	cmd := childproc.CommandContext(ctx, media.Binary("ffmpeg"), args...)
	cmd.Dir = dir
	// FFmpeg errors are normally short at loglevel=error; spool to a file to bound RAM.
	log, err := os.CreateTemp("", "rallycut-ffmpeg-*.log")
	if err != nil {
		return err
	}
	defer os.Remove(log.Name())
	defer log.Close()
	cmd.Stderr = log
	var stdin io.WriteCloser
	if feed != nil {
		if stdin, err = cmd.StdinPipe(); err != nil {
			return err
		}
	}
	if err := cmd.Start(); err != nil {
		return err
	}
	fed := make(chan error, 1)
	if feed != nil {
		go func() {
			err := feed(stdin)
			_ = stdin.Close()
			fed <- err
		}()
	} else {
		fed <- nil
	}
	waitErr := cmd.Wait()
	<-fed
	if waitErr != nil {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		_, _ = log.Seek(0, 0)
		buf := make([]byte, 8192)
		n, _ := log.Read(buf)
		return fmt.Errorf("FFmpeg: %w: %s", waitErr, string(buf[:n]))
	}
	return ctx.Err()
}
