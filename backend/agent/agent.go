// Package agent turns a RallyCut project into a brief an AI agent can read
// and edit, and turns edited briefs (or skill segment JSON, or a project
// file) back into a project for planning and export. The desktop "copy for
// agent" button and the skill's rallycut-cli share this code, so both see
// the same rally numbering, selection rules and export plan.
package agent

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"rallycut/backend/project"
	"rallycut/backend/timeline"
)

const (
	BriefKind    = "rallycut.project_brief"
	SegmentsKind = "rallycut.segments"
	PlanKind     = "rallycut.export_plan"
	maxDocument  = 32 << 20
)

// Rally is a project rally plus the fields an agent needs to refer to it.
type Rally struct {
	// Key is "<source id>/<rally id>", unique across the project.
	Key    string `json:"key"`
	Number int    `json:"n"` // 1-based position in its source, as on the rally cards
	project.Rally
	Duration float64 `json:"duration"`
	Human    bool    `json:"human"` // added or edited by the user
}

type Source struct {
	ID              string        `json:"id"`
	Video           project.Video `json:"video"`
	Analyzed        bool          `json:"analyzed"`
	PartialAnalysis bool          `json:"partial_analysis,omitempty"`
	Rallies         []Rally       `json:"rallies,omitempty"`
}

// Brief is a project without ball tracks or analysis internals.
type Brief struct {
	SchemaVersion  int                    `json:"schema_version"`
	Kind           string                 `json:"kind"`
	Note           string                 `json:"note,omitempty"`
	ProjectName    string                 `json:"project_name"`
	ProjectPath    string                 `json:"project_path,omitempty"`
	Rules          project.Rules          `json:"rules"`
	ExportSettings project.ExportSettings `json:"export_settings"`
	Sources        []Source               `json:"sources"`
}

const briefNote = "Times are seconds on each source video's own timeline. Rallies are machine candidates unless human=true; review before claiming accuracy. To change the cut, edit selected / start / end here (or pass --rallies) and run the rallycut skill: plan first, then export to a new .mp4. Never overwrite source videos."

// NewBrief summarizes p. path is the project file, if saved.
func NewBrief(p *project.Project, path string) Brief {
	c := project.Clone(p)
	c.SyncActive()
	b := Brief{SchemaVersion: 1, Kind: BriefKind, Note: briefNote, ProjectName: c.Name, ProjectPath: path,
		Rules: c.Rules, ExportSettings: c.ExportSettings.Normalized()}
	for _, s := range c.Sources {
		rallies := append([]project.Rally(nil), s.Rallies...)
		project.Sort(rallies)
		out := Source{ID: s.ID, Video: s.Video, Analyzed: s.Analysis != nil, PartialAnalysis: s.PartialAnalysis, Rallies: []Rally{}}
		for i, r := range rallies {
			// Millisecond times keep the clipboard short; never past the end.
			r.Start, r.End = round(r.Start), math.Min(round(r.End), s.Video.Duration)
			if r.EndEventTime > 0 {
				r.EndEventTime = math.Min(round(r.EndEventTime), s.Video.Duration)
			}
			out.Rallies = append(out.Rallies, Rally{Key: s.ID + "/" + r.ID, Number: i + 1, Rally: r,
				Duration: round(r.End - r.Start), Human: r.IsHuman()})
		}
		b.Sources = append(b.Sources, out)
	}
	return b
}

func round(v float64) float64 { return math.Round(v*1000) / 1000 }

// Markdown is the clipboard text: a short human/agent readable header, the
// skill commands, and the brief JSON. It contains local paths, not video.
func Markdown(b Brief) (string, error) {
	data, err := CompactJSON(b)
	if err != nil {
		return "", err
	}
	total, selected, human := 0, 0, 0
	for _, s := range b.Sources {
		for _, r := range s.Rallies {
			total++
			if r.Selected && !r.Invalid {
				selected++
			}
			if r.Human {
				human++
			}
		}
	}
	var w strings.Builder
	fmt.Fprintf(&w, "# RallyCut 项目：%s\n\n", b.ProjectName)
	if b.ProjectPath != "" {
		fmt.Fprintf(&w, "- 项目文件：%s\n", b.ProjectPath)
	}
	fmt.Fprintf(&w, "- 素材 %d 个，回合 %d 个（导出选中 %d，人工添加 / 修改 %d）\n", len(b.Sources), total, selected, human)
	fmt.Fprintf(&w, "- 剪辑参数：发球前保留 %.1f 秒，回合结束后保留 %.1f 秒；编码 %s，重叠处理 %s\n",
		b.Rules.PreRoll, b.Rules.PostRoll, b.ExportSettings.Codec, b.ExportSettings.Overlap)
	for i, s := range b.Sources {
		fmt.Fprintf(&w, "- 素材 %d：%s（%s，%.0f 秒）\n", i+1, s.Video.Name, s.Video.Path, s.Video.Duration)
	}
	w.WriteString("\n回合是机器识别的候选，`human: true` 为用户添加或修改；时间单位是秒，都在各自素材的时间轴上。\n\n")
	w.WriteString("## 用 rallycut skill 二次剪辑\n\n")
	w.WriteString("把下面的 JSON 存为文件（如 `brief.json`），按需要改 `selected` / `start` / `end`，然后先看计划、再导出 .mp4（不会覆盖原片；替换已有成片需加 `--overwrite`）：\n\n")
	w.WriteString("```bash\npython3 \"$SKILL_DIR/scripts/rallycut.py\" plan --input brief.json [--max-rallies 10] [--pre-roll 2] [--post-roll 1]\n")
	w.WriteString("python3 \"$SKILL_DIR/scripts/rallycut.py\" export --input brief.json --output /absolute/path/highlights.mp4 [同样的选项]\n```\n\n")
	if b.ProjectPath != "" {
		w.WriteString("也可以直接用项目文件：`--input \"" + b.ProjectPath + "\"`（读取桌面版当前保存的时间轴）。\n\n")
	}
	w.WriteString("```json\n")
	w.Write(data)
	w.WriteString("\n```\n")
	return w.String(), nil
}

// CompactJSON writes the brief with one rally per line: readable, and about
// a third of the size of fully indented JSON in an agent's context.
func CompactJSON(b Brief) ([]byte, error) {
	sources := b.Sources
	b.Sources = nil
	head, err := json.Marshal(b)
	if err != nil {
		return nil, err
	}
	var w strings.Builder
	w.Write(head[:len(head)-1]) // reopen the object
	w.WriteString(`,"sources":[`)
	for i, s := range sources {
		rallies := s.Rallies
		s.Rallies = nil
		meta, err := json.Marshal(s)
		if err != nil {
			return nil, err
		}
		if i > 0 {
			w.WriteString(",")
		}
		w.WriteString("\n {")
		w.Write(meta[1 : len(meta)-1])
		w.WriteString(`,"rallies":[`)
		for j, r := range rallies {
			line, err := json.Marshal(r)
			if err != nil {
				return nil, err
			}
			if j > 0 {
				w.WriteString(",")
			}
			w.WriteString("\n  ")
			w.Write(line)
		}
		w.WriteString("\n ]}")
	}
	w.WriteString("\n]}")
	return []byte(w.String()), nil
}

// Load reads a brief, a skill segments document or a desktop project file.
func Load(path string) (*project.Project, string, error) {
	path, err := filepath.Abs(path)
	if err != nil {
		return nil, "", err
	}
	info, err := os.Stat(path)
	if err != nil {
		return nil, "", err
	}
	if info.Size() > maxDocument {
		return nil, "", fmt.Errorf("输入文件超过 32 MiB 上限")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, "", err
	}
	p, kind, err := Parse(data)
	if err != nil {
		return nil, "", fmt.Errorf("%s: %w", filepath.Base(path), err)
	}
	return p, kind, nil
}

// Parse decodes any of the three accepted documents into a validated project.
func Parse(data []byte) (*project.Project, string, error) {
	var head struct {
		Kind          string          `json:"kind"`
		SchemaVersion int             `json:"schema_version"`
		Sources       json.RawMessage `json:"sources"`
	}
	if err := json.Unmarshal(data, &head); err != nil {
		return nil, "", fmt.Errorf("不是 JSON：%w", err)
	}
	var p *project.Project
	var err error
	switch head.Kind {
	case BriefKind:
		p, err = fromBrief(data)
	case SegmentsKind:
		p, err = fromSegments(data)
	case "":
		p = &project.Project{}
		err = json.Unmarshal(data, p)
		head.Kind = "rallycut.project"
	default:
		return nil, "", fmt.Errorf("不支持的文档类型 %q（接受项目 / project_brief / segments）", head.Kind)
	}
	if err != nil {
		return nil, "", err
	}
	if head.SchemaVersion != 1 {
		return nil, "", fmt.Errorf("不支持的 schema_version %d", head.SchemaVersion)
	}
	if err := check(p); err != nil {
		return nil, "", err
	}
	return p, head.Kind, nil
}

func fromBrief(data []byte) (*project.Project, error) {
	var b Brief
	if err := json.Unmarshal(data, &b); err != nil {
		return nil, err
	}
	if len(b.Sources) == 0 {
		return nil, errors.New("brief 没有素材")
	}
	p := &project.Project{SchemaVersion: project.SchemaVersion, ID: "agent-brief", Name: b.ProjectName,
		Rules: b.Rules, ExportSettings: b.ExportSettings, Model: "blurball-pretrained-v1"}
	for _, s := range b.Sources {
		src := project.Source{ID: s.ID, Video: s.Video, PartialAnalysis: s.PartialAnalysis}
		for _, r := range s.Rallies {
			src.Rallies = append(src.Rallies, r.Rally)
		}
		p.Sources = append(p.Sources, src)
	}
	activate(p)
	return p, nil
}

func fromSegments(data []byte) (*project.Project, error) {
	var doc struct {
		Source   project.Video   `json:"source"`
		Model    string          `json:"model"`
		Segments []project.Rally `json:"segments"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		return nil, err
	}
	// New-project padding (project.DefaultRules); flags override.
	p := &project.Project{SchemaVersion: project.SchemaVersion, ID: "skill-segments", Name: doc.Source.Name,
		Rules: project.DefaultRules(), Model: doc.Model,
		Sources: []project.Source{{ID: "source-1", Video: doc.Source, Rallies: doc.Segments}}}
	activate(p)
	return p, nil
}

// activate fills the legacy single-source fields from the first source.
func activate(p *project.Project) {
	p.ActiveSourceID = p.Sources[0].ID
	p.Video = p.Sources[0].Video
	p.Rallies = p.Sources[0].Rallies
}

func check(p *project.Project) error {
	p.SyncActive()
	if err := project.ValidateRules(p.Rules); err != nil {
		return err
	}
	if err := project.ValidateExport(p.ExportSettings); err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, s := range p.Sources {
		if s.ID == "" || seen[s.ID] {
			return errors.New("素材 ID 为空或重复")
		}
		seen[s.ID] = true
		if s.Video.Path == "" || !project.Finite(s.Video.Duration) || s.Video.Duration <= 0 {
			return fmt.Errorf("素材 %s 缺少视频路径或时长", s.ID)
		}
		if s.Video.Fingerprint == "" {
			return fmt.Errorf("素材 %s 缺少内容指纹，无法确认原片未变", s.ID)
		}
		if err := project.ValidateRallies(s.Rallies, s.Video.Duration); err != nil {
			return fmt.Errorf("素材 %s：%w", s.Video.Name, err)
		}
	}
	return nil
}

// Selection narrows what gets exported. Zero values keep the document's own
// `selected` flags.
type Selection struct {
	// Keys picks exactly these rallies ("<source id>/<rally id>", or a bare
	// rally id when unambiguous); everything else is deselected.
	Keys          []string
	FavoritesOnly bool
	MinDuration   float64
	// MaxRallies keeps at most N rallies across all sources: favorites first,
	// then higher score, then longer; ties keep timeline order.
	MaxRallies int
	PreRoll    *float64
	PostRoll   *float64
}

// Apply changes selection and padding on p in place. Invalid rallies are
// never exported. Returns how many rallies remain selected.
func Apply(p *project.Project, s Selection) (int, error) {
	if s.MaxRallies < 0 || !project.Finite(s.MinDuration) || s.MinDuration < 0 {
		return 0, errors.New("max-rallies / min-duration 不能为负")
	}
	if s.PreRoll != nil {
		p.Rules.PreRoll = *s.PreRoll
	}
	if s.PostRoll != nil {
		p.Rules.PostRoll = *s.PostRoll
	}
	if err := project.ValidateRules(p.Rules); err != nil {
		return 0, err
	}
	p.SyncActive()
	if len(s.Keys) > 0 {
		want := map[[2]string]bool{}
		for _, key := range s.Keys {
			key = strings.TrimSpace(key)
			if key == "" {
				continue
			}
			ref, err := resolve(p, key)
			if err != nil {
				return 0, err
			}
			want[ref] = true
		}
		for i := range p.Sources {
			for j := range p.Sources[i].Rallies {
				r := &p.Sources[i].Rallies[j]
				r.Selected = want[[2]string{p.Sources[i].ID, r.ID}]
			}
		}
	}
	type ref struct{ source, rally, order int }
	var kept []ref
	order := 0
	for i := range p.Sources {
		project.Sort(p.Sources[i].Rallies)
		for j := range p.Sources[i].Rallies {
			r := &p.Sources[i].Rallies[j]
			if r.Invalid || (s.FavoritesOnly && !r.Favorite) || r.End-r.Start < s.MinDuration {
				r.Selected = false
			}
			if r.Selected {
				kept = append(kept, ref{i, j, order})
			}
			order++
		}
	}
	if s.MaxRallies > 0 && len(kept) > s.MaxRallies {
		rally := func(k ref) project.Rally { return p.Sources[k.source].Rallies[k.rally] }
		ranked := append([]ref(nil), kept...)
		sort.SliceStable(ranked, func(a, b int) bool {
			x, y := rally(ranked[a]), rally(ranked[b])
			if x.Favorite != y.Favorite {
				return x.Favorite
			}
			if x.Score != y.Score {
				return x.Score > y.Score
			}
			return x.End-x.Start > y.End-y.Start
		})
		for _, k := range ranked[s.MaxRallies:] {
			p.Sources[k.source].Rallies[k.rally].Selected = false
		}
		kept = ranked[:s.MaxRallies]
	}
	// Re-load the legacy fields from the (possibly re-sorted) active source.
	for _, src := range p.Sources {
		if src.ID == p.ActiveSourceID {
			p.Video, p.Rallies = src.Video, src.Rallies
		}
	}
	return len(kept), nil
}

func resolve(p *project.Project, key string) ([2]string, error) {
	if source, rally, ok := strings.Cut(key, "/"); ok {
		for _, s := range p.Sources {
			if s.ID != source {
				continue
			}
			for _, r := range s.Rallies {
				if r.ID == rally {
					return [2]string{source, rally}, nil
				}
			}
		}
		return [2]string{}, fmt.Errorf("找不到回合 %q", key)
	}
	var found [][2]string
	for _, s := range p.Sources {
		for _, r := range s.Rallies {
			if r.ID == key {
				found = append(found, [2]string{s.ID, r.ID})
			}
		}
	}
	switch len(found) {
	case 0:
		return [2]string{}, fmt.Errorf("找不到回合 %q", key)
	case 1:
		return found[0], nil
	}
	return [2]string{}, fmt.Errorf("回合 ID %q 在多个素材中出现，请用 <素材 id>/<回合 id>", key)
}

// PlanSpan is one output clip; rallies are 1-based numbers in its source.
type PlanSpan struct {
	Source   string  `json:"source"`
	Video    string  `json:"video"`
	Start    float64 `json:"start"`
	End      float64 `json:"end"`
	Duration float64 `json:"duration"`
	Rallies  []int   `json:"rallies"`
}

type Plan struct {
	SchemaVersion   int                    `json:"schema_version"`
	Kind            string                 `json:"kind"`
	Rules           project.Rules          `json:"rules"`
	ExportSettings  project.ExportSettings `json:"export_settings"`
	SelectedRallies int                    `json:"selected_rallies"`
	Spans           []PlanSpan             `json:"spans"`
	TotalDuration   float64                `json:"total_duration"`
}

// NewPlan is the exact span list export.Run renders (timeline.ExportPlan per
// source, overlap policy included).
func NewPlan(p *project.Project, selected int) (Plan, error) {
	p.SyncActive()
	settings := p.ExportSettings.Normalized()
	plan := Plan{SchemaVersion: 1, Kind: PlanKind, Rules: p.Rules, ExportSettings: settings, SelectedRallies: selected, Spans: []PlanSpan{}}
	for _, s := range p.Sources {
		if !anySelected(s.Rallies) {
			continue
		}
		spans, labels, err := timeline.ExportPlan(s.Rallies, p.Rules, settings, s.Video.Duration)
		if err != nil {
			return Plan{}, fmt.Errorf("%s：%w", s.Video.Name, err)
		}
		for k, span := range spans {
			numbers := []int{}
			for _, label := range labels[k] {
				numbers = append(numbers, label.Number)
			}
			plan.Spans = append(plan.Spans, PlanSpan{Source: s.ID, Video: s.Video.Path, Start: round(span.Start), End: round(span.End),
				Duration: round(span.End - span.Start), Rallies: numbers})
			plan.TotalDuration += span.End - span.Start
		}
	}
	plan.TotalDuration = round(plan.TotalDuration)
	if len(plan.Spans) == 0 {
		return Plan{}, errors.New("没有选中的回合")
	}
	return plan, nil
}

func anySelected(rs []project.Rally) bool {
	for _, r := range rs {
		if r.Selected && !r.Invalid {
			return true
		}
	}
	return false
}
