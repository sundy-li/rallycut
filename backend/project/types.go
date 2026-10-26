package project

import (
	"fmt"
	"math"
	"sort"
	"strings"
	"time"
)

const SchemaVersion = 1

type Video struct {
	Path        string  `json:"path"`
	Name        string  `json:"name"`
	Fingerprint string  `json:"fingerprint"`
	Duration    float64 `json:"duration"`
	Width       int     `json:"width"`
	Height      int     `json:"height"`
	FPS         float64 `json:"fps"`
	HasAudio    bool    `json:"has_audio"`
	Codec       string  `json:"codec"`
	BitRate     int64   `json:"bit_rate"`
	Rotation    int     `json:"rotation"`
}

type Rally struct {
	ID         string  `json:"id"`
	Start      float64 `json:"start"`
	End        float64 `json:"end"`
	Confidence float64 `json:"confidence"`
	Score      float64 `json:"score"`
	Selected   bool    `json:"selected"`
	Edited     bool    `json:"edited"`
	// Invalid marks a rally that should remain visible for review but must not
	// be included in the real editing/export timeline (e.g. a net serve replay).
	Invalid bool `json:"invalid,omitempty"`
	// Favorite is a user-marked highlight, independent of the model score.
	Favorite       bool    `json:"favorite,omitempty"`
	Evidence       string  `json:"evidence,omitempty"`
	BoundaryBefore bool    `json:"boundary_before,omitempty"`
	StartReason    string  `json:"start_reason,omitempty"`
	EndReason      string  `json:"end_reason,omitempty"`
	EndEventTime   float64 `json:"end_event_time,omitempty"`
	EndConfidence  float64 `json:"end_confidence,omitempty"`
}

type TrackPoint struct {
	T          float64 `json:"t"`
	X          float64 `json:"x"`
	Y          float64 `json:"y"`
	Confidence float64 `json:"confidence"`
}

type BallTrack struct {
	ID     string       `json:"id"`
	Points []TrackPoint `json:"points"`
	// OffPlay: far from this video's play area (display hint; never dropped).
	OffPlay bool `json:"off_play,omitempty"`
}

type RallyEvent struct {
	Type        string   `json:"type"`
	Time        float64  `json:"time"`
	ConfirmedAt float64  `json:"confirmed_at"`
	Reason      string   `json:"reason"`
	Confidence  float64  `json:"confidence"`
	X           float64  `json:"x"`
	Y           float64  `json:"y"`
	Signals     []string `json:"signals"`
}

type AnalysisSummary struct {
	Method                         string             `json:"method"`
	DecodedFrames                  int                `json:"decoded_frames"`
	SampledFrames                  int                `json:"sampled_frames"`
	TrackCount                     int                `json:"track_count"`
	ElapsedSeconds                 float64            `json:"elapsed_seconds"`
	ProcessingFPS                  float64            `json:"processing_fps,omitempty"`
	AnalysisFPS                    float64            `json:"analysis_fps,omitempty"`
	TableBounds                    []float64          `json:"table_bounds"`
	TableMode                      string             `json:"table_mode,omitempty"`
	GeometryAvailable              *bool              `json:"geometry_available,omitempty"`
	UnscoredFrames                 int                `json:"unscored_frames,omitempty"`
	TableSegments                  []TableSegment     `json:"table_segments,omitempty"`
	CameraCuts                     int                `json:"camera_cuts,omitempty"`
	NetRegion                      []float64          `json:"net_region,omitempty"`
	NetRegionSource                string             `json:"net_region_source,omitempty"`
	RallyStateVersion              string             `json:"rally_state_version,omitempty"`
	ActivityRuleVersion            string             `json:"activity_rule_version,omitempty"`
	PlayAreaVersion                string             `json:"play_area_version,omitempty"`
	RallyEvents                    []RallyEvent       `json:"rally_events,omitempty"`
	CalibrationMethod              string             `json:"calibration_method,omitempty"`
	CalibrationSamples             int                `json:"calibration_samples,omitempty"`
	CalibrationFirstTimestamp      float64            `json:"calibration_first_timestamp,omitempty"`
	CalibrationLastTimestamp       float64            `json:"calibration_last_timestamp,omitempty"`
	CalibrationSearchSeconds       float64            `json:"calibration_search_seconds,omitempty"`
	CalibrationSampledFrames       int                `json:"calibration_sampled_frames,omitempty"`
	CalibrationElapsedSeconds      float64            `json:"calibration_elapsed_seconds,omitempty"`
	CalibrationStrategy            string             `json:"calibration_strategy,omitempty"`
	CalibrationJumpSamples         int                `json:"calibration_jump_samples,omitempty"`
	CalibrationJumpWindows         int                `json:"calibration_jump_windows,omitempty"`
	CalibrationJumpBudget          int                `json:"calibration_jump_budget,omitempty"`
	CalibrationSearchExtentSeconds float64            `json:"calibration_search_extent_seconds,omitempty"`
	SceneChanges                   int                `json:"scene_changes"`
	AudioImpacts                   int                `json:"audio_impacts"`
	Warnings                       []string           `json:"warnings"`
	WeightsSHA256                  string             `json:"weights_sha256,omitempty"`
	Device                         string             `json:"device,omitempty"`
	Decoder                        string             `json:"decoder,omitempty"`
	HardwareDecode                 bool               `json:"hardware_decode"`
	DecodeFormat                   string             `json:"decode_format,omitempty"`
	Precision                      string             `json:"precision,omitempty"`
	BatchSize                      int                `json:"batch_size,omitempty"`
	Pipeline                       *bool              `json:"pipeline,omitempty"`
	PipelineTimings                map[string]float64 `json:"pipeline_timings,omitempty"`
	Implementation                 string             `json:"implementation,omitempty"`
	DetectionFrames                int                `json:"detection_frames,omitempty"`
	DuplicateFrames                int                `json:"duplicate_frames,omitempty"`
}

type Rules struct {
	PreRoll     float64 `json:"pre_roll"`
	PostRoll    float64 `json:"post_roll"`
	MinDuration float64 `json:"min_duration"`
}

type ExportSettings struct {
	Codec   string `json:"codec"`    // h264 (default) or hevc
	Encoder string `json:"encoder"`  // auto (VideoToolbox on macOS) or software
	BitRate int64  `json:"bit_rate"` // 0 inherits the source video stream bitrate
	// Overlap decides which rally wins when a human rally and a machine rally
	// overlap at export time: merge (default), sequential (the one starting
	// first wins), human or machine. Losers are skipped entirely. Same-kind
	// overlaps are always merged.
	Overlap string `json:"overlap,omitempty"`
	// Burn-in overlays: the player's ball trajectory style and a top-left
	// rally number ("回合 03"). Both default off.
	ShowTrajectory  bool `json:"show_trajectory,omitempty"`
	ShowRallyLabels bool `json:"show_rally_labels,omitempty"`
}

const (
	OverlapMerge      = "merge"
	OverlapSequential = "sequential"
	OverlapHuman      = "human"
	OverlapMachine    = "machine"
)

func (s ExportSettings) Normalized() ExportSettings {
	if s.Codec == "" {
		s.Codec = "h264"
	}
	if s.Encoder == "" {
		s.Encoder = "auto"
	}
	if s.Overlap == "" {
		s.Overlap = OverlapMerge
	}
	return s
}

func ValidateExport(s ExportSettings) error {
	s = s.Normalized()
	if s.Codec != "h264" && s.Codec != "hevc" {
		return fmt.Errorf("不支持的导出编码 %q", s.Codec)
	}
	if s.Encoder != "auto" && s.Encoder != "software" {
		return fmt.Errorf("不支持的编码模式 %q", s.Encoder)
	}
	switch s.Overlap {
	case OverlapMerge, OverlapSequential, OverlapHuman, OverlapMachine:
	default:
		return fmt.Errorf("不支持的重叠处理方式 %q", s.Overlap)
	}
	if s.BitRate != 0 && (s.BitRate < 500000 || s.BitRate > 200000000) {
		return fmt.Errorf("目标码率应为 0（跟随原片）或 0.5–200 Mbps")
	}
	return nil
}

// Performance counts completed frames. It is not the source's nominal FPS.
type Performance struct {
	Stage           string  `json:"stage"`
	ProcessedFrames int     `json:"processed_frames"`
	ElapsedSeconds  float64 `json:"elapsed_seconds"`
	RecentFPS       float64 `json:"recent_fps"`
	AverageFPS      float64 `json:"average_fps"`
}

func (p *Performance) Validate() error {
	if p == nil {
		return nil
	}
	if p.Stage != "inference" && p.Stage != "finalizing" {
		return fmt.Errorf("未知性能阶段")
	}
	if p.ProcessedFrames < 0 {
		return fmt.Errorf("无效处理帧数")
	}
	for _, value := range []float64{p.ElapsedSeconds, p.RecentFPS, p.AverageFPS} {
		if !Finite(value) || value < 0 {
			return fmt.Errorf("无效性能计时")
		}
	}
	return nil
}

type Job struct {
	ID             string       `json:"id"`
	Kind           string       `json:"kind"`
	Status         string       `json:"status"`
	Progress       float64      `json:"progress"`
	Message        string       `json:"message"`
	Output         string       `json:"output,omitempty"`
	Performance    *Performance `json:"performance,omitempty"`
	ElapsedSeconds float64      `json:"elapsed_seconds,omitempty"`
	// Provisional rallies streamed while frames are still being analysed.
	// They are never written to the project file.
	Candidates       []Rally `json:"candidates,omitempty"`
	ProcessedSeconds float64 `json:"processed_seconds,omitempty"`
}

// Source is one imported clip with its own timeline and analysis. Project keeps
// the active source mirrored in the legacy top-level fields so the existing
// single-video code paths keep working unchanged.
type Source struct {
	ID              string           `json:"id"`
	Video           Video            `json:"video"`
	RawRallies      []Rally          `json:"raw_rallies"`
	Rallies         []Rally          `json:"rallies"`
	Tracks          []BallTrack      `json:"tracks"`
	Analysis        *AnalysisSummary `json:"analysis,omitempty"`
	ManualTimeline  bool             `json:"manual_timeline,omitempty"`
	PartialAnalysis bool             `json:"partial_analysis,omitempty"`
}

type Project struct {
	SchemaVersion  int      `json:"schema_version"`
	ID             string   `json:"id"`
	Name           string   `json:"name"`
	Video          Video    `json:"video"`
	Sources        []Source `json:"sources,omitempty"`
	ActiveSourceID string   `json:"active_source_id,omitempty"`
	// Raw detections are immutable; manual changes live in Rallies.
	RawRallies     []Rally        `json:"raw_rallies"`
	Rallies        []Rally        `json:"rallies"`
	Rules          Rules          `json:"rules"`
	ExportSettings ExportSettings `json:"export_settings"`
	Model          string         `json:"model"`
	ManualTimeline bool           `json:"manual_timeline"`
	// PartialAnalysis marks rallies kept from a cancelled run: usable, but not
	// validated against a complete pass.
	PartialAnalysis bool             `json:"partial_analysis,omitempty"`
	Tracks          []BallTrack      `json:"tracks"`
	Analysis        *AnalysisSummary `json:"analysis,omitempty"`
	AnalysisID      string           `json:"analysis_id,omitempty"`
	AnalysisRuntime string           `json:"analysis_runtime,omitempty"`
	UpdatedAt       string           `json:"updated_at"`
	Job             *Job             `json:"job,omitempty"`
}

// SyncActive copies the legacy fields into the active source entry.
func (p *Project) SyncActive() {
	if p == nil {
		return
	}
	if len(p.Sources) == 0 {
		id := p.ID
		if id == "" {
			id = NewID()
		}
		p.Sources = []Source{{ID: id, Video: p.Video, RawRallies: p.RawRallies, Rallies: p.Rallies,
			Tracks: p.Tracks, Analysis: p.Analysis, ManualTimeline: p.ManualTimeline, PartialAnalysis: p.PartialAnalysis}}
		p.ActiveSourceID = id
		return
	}
	for i := range p.Sources {
		if p.Sources[i].ID != p.ActiveSourceID {
			continue
		}
		p.Sources[i].Video = p.Video
		p.Sources[i].RawRallies = p.RawRallies
		p.Sources[i].Rallies = p.Rallies
		p.Sources[i].Tracks = p.Tracks
		p.Sources[i].Analysis = p.Analysis
		p.Sources[i].ManualTimeline = p.ManualTimeline
		p.Sources[i].PartialAnalysis = p.PartialAnalysis
		return
	}
	p.ActiveSourceID = p.Sources[0].ID
	p.SyncActive()
}

// loadSource copies one source into the legacy fields without syncing first.
func (p *Project) loadSource(id string) bool {
	for i := range p.Sources {
		if p.Sources[i].ID != id {
			continue
		}
		s := p.Sources[i]
		p.ActiveSourceID = id
		p.Video, p.RawRallies, p.Rallies, p.Tracks = s.Video, s.RawRallies, s.Rallies, s.Tracks
		p.Analysis, p.ManualTimeline, p.PartialAnalysis = s.Analysis, s.ManualTimeline, s.PartialAnalysis
		return true
	}
	return false
}

// ActivateSource loads a source into the legacy fields.
func (p *Project) ActivateSource(id string) bool {
	p.SyncActive()
	return p.loadSource(id)
}

// AddSource appends a clip and returns its id.
func (p *Project) AddSource(v Video) string {
	id := NewID()
	p.Sources = append(p.Sources, Source{ID: id, Video: v, RawRallies: []Rally{}, Rallies: []Rally{}, Tracks: []BallTrack{}})
	return id
}

// ReorderSources applies a new order; ids must be a permutation of the sources.
func (p *Project) ReorderSources(ids []string) error {
	if len(ids) != len(p.Sources) {
		return fmt.Errorf("素材顺序不完整")
	}
	byID := make(map[string]Source, len(p.Sources))
	for _, s := range p.Sources {
		byID[s.ID] = s
	}
	next := make([]Source, 0, len(ids))
	for _, id := range ids {
		s, ok := byID[id]
		if !ok {
			return fmt.Errorf("素材不存在")
		}
		delete(byID, id)
		next = append(next, s)
	}
	if len(byID) != 0 {
		return fmt.Errorf("素材顺序重复")
	}
	p.Sources = next
	return nil
}

// RemoveSource drops a clip; at least one source must remain.
func (p *Project) RemoveSource(id string) error {
	if len(p.Sources) <= 1 {
		return fmt.Errorf("至少保留一个素材")
	}
	for i, s := range p.Sources {
		if s.ID != id {
			continue
		}
		p.Sources = append(p.Sources[:i], p.Sources[i+1:]...)
		if p.ActiveSourceID == id {
			// The legacy fields belong to the removed clip; drop them instead
			// of syncing them into whichever source becomes active next.
			next := p.Sources[0].ID
			if i < len(p.Sources) {
				next = p.Sources[i].ID
			}
			p.ActiveSourceID = ""
			p.loadSource(next)
		}
		return nil
	}
	return fmt.Errorf("素材不存在")
}

func NewID() string { return fmt.Sprintf("%x", time.Now().UnixNano()) }

const DefaultNameLayout = "20060102-150405"

func DefaultName(at time.Time) string {
	if at.IsZero() {
		at = time.Now()
	}
	return at.Format(DefaultNameLayout)
}

func New(v Video) *Project { return NewAt(v, time.Now()) }

// NewAt creates a project whose name is independent from the video filename.
func NewAt(v Video, at time.Time) *Project {
	id := NewID()
	return &Project{SchemaVersion: SchemaVersion, ID: id, Name: DefaultName(at),
		Video: v, Sources: []Source{{ID: id, Video: v, RawRallies: []Rally{}, Rallies: []Rally{}, Tracks: []BallTrack{}}},
		ActiveSourceID: id,
		RawRallies:     []Rally{}, Rallies: []Rally{},
		Rules:          Rules{PreRoll: .5, PostRoll: .8, MinDuration: 6},
		ExportSettings: ExportSettings{}.Normalized(),
		UpdatedAt:      time.Now().UTC().Format(time.RFC3339),
	}
}

func Finite(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) }

// TableSegment is one camera shot and the table box calibrated for it.
type TableSegment struct {
	Start     float64   `json:"start"`
	End       float64   `json:"end"`
	Bounds    []float64 `json:"bounds"`
	NetRegion []float64 `json:"net_region,omitempty"`
	Method    string    `json:"method,omitempty"`
}

// ValidateTableBounds accepts missing geometry, but not malformed boxes.
func ValidateTableBounds(bounds []float64) error {
	if len(bounds) == 0 {
		return nil
	}
	if len(bounds) != 4 {
		return fmt.Errorf("无效球桌范围")
	}
	for _, v := range bounds {
		if !Finite(v) || v < 0 || v > 1 {
			return fmt.Errorf("球桌范围越界")
		}
	}
	if bounds[0] >= bounds[2] || bounds[1] >= bounds[3] {
		return fmt.Errorf("球桌范围无效")
	}
	return nil
}

// ValidateTableSegments keeps per-shot calibration ordered and inside the video.
func ValidateTableSegments(segments []TableSegment, duration float64) error {
	previous := -1.0
	for _, segment := range segments {
		if !Finite(segment.Start) || !Finite(segment.End) || segment.Start < 0 ||
			segment.End <= segment.Start || segment.End > duration+.25 || segment.Start < previous {
			return fmt.Errorf("无效镜头分段")
		}
		if err := ValidateTableBounds(segment.Bounds); err != nil {
			return err
		}
		if err := ValidateRallyEvents(&AnalysisSummary{NetRegion: segment.NetRegion}, duration); err != nil {
			return err
		}
		previous = segment.End
	}
	return nil
}

func ValidateRallies(rs []Rally, duration float64) error {
	if len(rs) > 100000 {
		return fmt.Errorf("回合数量超出上限")
	}
	ids := map[string]bool{}
	for _, r := range rs {
		if r.ID == "" || ids[r.ID] {
			return fmt.Errorf("回合 ID 为空或重复")
		}
		ids[r.ID] = true
		if !Finite(r.Start) || !Finite(r.End) || r.Start < 0 || r.End > duration || r.End-r.Start < .04 {
			return fmt.Errorf("回合 %s 时间越界或短于 0.04 秒", r.ID)
		}
		if !Finite(r.EndEventTime) || r.EndEventTime < 0 || r.EndEventTime > duration || !Finite(r.EndConfidence) || r.EndConfidence < 0 || r.EndConfidence > 1 {
			return fmt.Errorf("回合 %s 终止证据无效", r.ID)
		}
		if !Finite(r.Confidence) || r.Confidence < 0 || r.Confidence > 1 || !Finite(r.Score) || r.Score < 0 || r.Score > 100 {
			return fmt.Errorf("回合 %s 评分无效", r.ID)
		}
	}
	return nil
}

func ValidateRules(r Rules) error {
	for _, v := range []float64{r.PreRoll, r.PostRoll, r.MinDuration} {
		if !Finite(v) || v < 0 || v > 60 {
			return fmt.Errorf("剪辑规则必须在 0–60 秒之间")
		}
	}
	return nil
}

func (p *Project) Validate() error {
	if p.SchemaVersion != SchemaVersion {
		return fmt.Errorf("不支持的项目版本 %d", p.SchemaVersion)
	}
	if p.ID == "" || p.Video.Path == "" || !Finite(p.Video.Duration) || p.Video.Duration <= 0 {
		return fmt.Errorf("项目视频信息无效")
	}
	if err := ValidateRules(p.Rules); err != nil {
		return err
	}
	if err := ValidateExport(p.ExportSettings); err != nil {
		return err
	}
	if err := ValidateRallies(p.RawRallies, p.Video.Duration); err != nil {
		return err
	}
	if err := ValidateTracks(p.Tracks, p.Video.Duration); err != nil {
		return err
	}
	if err := ValidateRallyEvents(p.Analysis, p.Video.Duration); err != nil {
		return err
	}
	if p.Analysis != nil {
		if err := ValidateTableBounds(p.Analysis.TableBounds); err != nil {
			return err
		}
		if err := ValidateTableSegments(p.Analysis.TableSegments, p.Video.Duration); err != nil {
			return err
		}
	}
	return ValidateRallies(p.Rallies, p.Video.Duration)
}

func Clone(p *Project) *Project {
	if p == nil {
		return nil
	}
	q := *p
	q.Sources = make([]Source, len(p.Sources))
	for i, source := range p.Sources {
		q.Sources[i] = source
		q.Sources[i].RawRallies = append([]Rally{}, source.RawRallies...)
		q.Sources[i].Rallies = append([]Rally{}, source.Rallies...)
		q.Sources[i].Tracks = CloneTracks(source.Tracks)
		if source.Analysis != nil {
			summary := *source.Analysis
			q.Sources[i].Analysis = &summary
		}
	}
	q.RawRallies = append([]Rally{}, p.RawRallies...)
	q.Rallies = append([]Rally{}, p.Rallies...)
	q.Tracks = CloneTracks(p.Tracks)
	if p.Analysis != nil {
		summary := *p.Analysis
		summary.TableBounds = append([]float64{}, p.Analysis.TableBounds...)
		if p.Analysis.GeometryAvailable != nil {
			available := *p.Analysis.GeometryAvailable
			summary.GeometryAvailable = &available
		}
		summary.TableSegments = append([]TableSegment{}, p.Analysis.TableSegments...)
		for i := range summary.TableSegments {
			summary.TableSegments[i].Bounds = append([]float64{}, p.Analysis.TableSegments[i].Bounds...)
			summary.TableSegments[i].NetRegion = append([]float64{}, p.Analysis.TableSegments[i].NetRegion...)
		}
		summary.NetRegion = append([]float64{}, p.Analysis.NetRegion...)
		summary.RallyEvents = append([]RallyEvent{}, p.Analysis.RallyEvents...)
		for i := range summary.RallyEvents {
			summary.RallyEvents[i].Signals = append([]string{}, p.Analysis.RallyEvents[i].Signals...)
		}
		summary.Warnings = append([]string{}, p.Analysis.Warnings...)
		if p.Analysis.Pipeline != nil {
			pipeline := *p.Analysis.Pipeline
			summary.Pipeline = &pipeline
		}
		if p.Analysis.PipelineTimings != nil {
			summary.PipelineTimings = make(map[string]float64, len(p.Analysis.PipelineTimings))
			for key, value := range p.Analysis.PipelineTimings {
				summary.PipelineTimings[key] = value
			}
		}
		q.Analysis = &summary
	}
	if p.Job != nil {
		j := *p.Job
		if p.Job.Performance != nil {
			performance := *p.Job.Performance
			j.Performance = &performance
		}
		q.Job = &j
	}
	return &q
}

// AdoptAnalysisCandidatesIfEmpty fills an empty timeline from the latest
// machine candidates. A non-empty manual timeline is left untouched.
func (p *Project) AdoptAnalysisCandidatesIfEmpty() bool {
	if p == nil || len(p.Rallies) != 0 || len(p.RawRallies) == 0 {
		return false
	}
	p.Rallies = append([]Rally{}, p.RawRallies...)
	p.ManualTimeline = false
	return true
}

// IsHuman reports whether a rally was created or corrected by the user.
// Such rallies survive re-analysis; untouched model candidates do not.
func (r Rally) IsHuman() bool { return r.Edited || strings.HasPrefix(r.ID, "manual-") }

func rallyOverlap(a, b Rally) float64 {
	return math.Min(a.End, b.End) - math.Max(a.Start, b.Start)
}

// AnalysisMerge reports what ApplyAnalysis did with a non-empty timeline.
type AnalysisMerge struct {
	KeptHuman      int
	Machine        int
	OverlapHuman   int // new candidates overlapping a kept human rally (both kept)
	KeptDeselected int
}

// ApplyAnalysis installs a new machine result. Human rallies (manually added
// or corrected) are kept; untouched machine rallies are replaced by all new
// candidates. Human and machine rallies are separate sources and both stay in
// the timeline even where they overlap; export_settings.overlap decides at
// export which one is used. A candidate matching a machine rally the user had
// deselected (IoU >= 0.5) stays deselected.
func (p *Project) ApplyAnalysis(rs []Rally, model string) AnalysisMerge {
	p.RawRallies = append([]Rally{}, rs...)
	p.Model = model
	p.PartialAnalysis = false
	if !p.ManualTimeline || len(p.Rallies) == 0 {
		p.Rallies = append([]Rally{}, rs...)
		p.ManualTimeline = false
		return AnalysisMerge{Machine: len(rs)}
	}
	var stats AnalysisMerge
	kept := make([]Rally, 0, len(p.Rallies)+len(rs))
	ids := map[string]bool{}
	var deselected []Rally
	for _, r := range p.Rallies {
		if r.IsHuman() {
			kept = append(kept, r)
			ids[r.ID] = true
		} else if !r.Selected {
			deselected = append(deselected, r)
		}
	}
	stats.KeptHuman = len(kept)
	human := append([]Rally(nil), kept...)
	for _, candidate := range rs {
		for _, h := range human {
			if rallyOverlap(candidate, h) > 0.05 {
				stats.OverlapHuman++
				break
			}
		}
		for _, old := range deselected {
			inter := rallyOverlap(candidate, old)
			union := math.Max(candidate.End, old.End) - math.Min(candidate.Start, old.Start)
			if inter > 0 && union > 0 && inter/union >= 0.5 {
				candidate.Selected = false
				stats.KeptDeselected++
				break
			}
		}
		base, id := candidate.ID, candidate.ID
		for n := 2; ids[id]; n++ {
			id = fmt.Sprintf("%s-r%d", base, n)
		}
		candidate.ID = id
		ids[id] = true
		kept = append(kept, candidate)
		stats.Machine++
	}
	Sort(kept)
	p.Rallies = kept
	p.ManualTimeline = stats.KeptHuman > 0 || stats.KeptDeselected > 0
	return stats
}

func ValidateRallyEvents(summary *AnalysisSummary, duration float64) error {
	if summary == nil {
		return nil
	}
	net := summary.NetRegion
	if len(net) != 0 {
		if len(net) != 6 {
			return fmt.Errorf("球网标定需要 6 个坐标")
		}
		for _, v := range net {
			if !Finite(v) || v < 0 || v > 1 {
				return fmt.Errorf("球网坐标越界")
			}
		}
		if net[0] >= net[3] || net[1] >= net[2] || net[4] >= net[5] {
			return fmt.Errorf("球网几何无效")
		}
	}
	if len(summary.RallyEvents) > 100000 {
		return fmt.Errorf("回合事件数量过多")
	}
	for _, e := range summary.RallyEvents {
		if e.Type != "dead_ball" && e.Type != "restart" {
			return fmt.Errorf("未知回合事件")
		}
		if e.Reason == "" || len(e.Signals) == 0 || !Finite(e.Time) || e.Time < 0 || e.Time > duration || !Finite(e.ConfirmedAt) || e.ConfirmedAt < e.Time || e.ConfirmedAt > duration+.001 {
			return fmt.Errorf("回合事件时间/依据无效")
		}
		for _, v := range []float64{e.Confidence, e.X, e.Y} {
			if !Finite(v) || v < 0 || v > 1 {
				return fmt.Errorf("回合事件坐标/分数无效")
			}
		}
	}
	return nil
}

func CloneTracks(tracks []BallTrack) []BallTrack {
	out := make([]BallTrack, len(tracks))
	for i, t := range tracks {
		out[i] = t
		out[i].Points = append([]TrackPoint{}, t.Points...)
	}
	return out
}

func ValidateTracks(tracks []BallTrack, duration float64) error {
	total := 0
	ids := map[string]bool{}
	for _, track := range tracks {
		if track.ID == "" || ids[track.ID] {
			return fmt.Errorf("球轨迹 ID 为空或重复")
		}
		ids[track.ID] = true
		if len(track.Points) < 3 || len(track.Points) > 60 {
			return fmt.Errorf("球轨迹点数无效")
		}
		previous := -1.0
		for _, p := range track.Points {
			if !Finite(p.T) || p.T < 0 || p.T > duration || p.T <= previous || !Finite(p.X) || p.X < 0 || p.X > 1 || !Finite(p.Y) || p.Y < 0 || p.Y > 1 || !Finite(p.Confidence) || p.Confidence < 0 || p.Confidence > 1 {
				return fmt.Errorf("球轨迹包含无效坐标或时间戳")
			}
			previous = p.T
			total++
		}
	}
	if total > 2000000 {
		return fmt.Errorf("球轨迹超过容量上限")
	}
	return nil
}

func Sort(rs []Rally) { sort.SliceStable(rs, func(i, j int) bool { return rs[i].Start < rs[j].Start }) }
