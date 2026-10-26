package timeline

import (
	"fmt"
	"math"
	"rallycut/backend/project"
	"sort"
)

type Segment struct {
	Start float64 `json:"start"`
	End   float64 `json:"end"`
}

// Segments are chronological, clamped and coalesced so padding/overlap never
// duplicates footage or audio in a highlights export.
func Segments(rs []project.Rally, rules project.Rules, duration float64) ([]Segment, error) {
	if err := project.ValidateRules(rules); err != nil {
		return nil, err
	}
	if err := project.ValidateRallies(rs, duration); err != nil {
		return nil, err
	}
	ordered := append([]project.Rally{}, rs...)
	project.Sort(ordered)
	barriers := map[float64]bool{}
	cuts := map[int]float64{}
	furthest, exported := 0.0, 0.0
	for i, r := range ordered {
		if r.BoundaryBefore {
			// A protected boundary only stops padding from rejoining. If an
			// exported rally's own content already crosses it (e.g. a manual
			// mark overlapping a machine candidate), the user has overridden
			// it: keep all of that footage and merge, never duplicate.
			if exported <= r.Start {
				cut := r.Start
				if i > 0 {
					cut = (math.Min(furthest, r.Start) + r.Start) / 2
				}
				cuts[i] = cut
				barriers[cut] = true
			}
		}
		furthest = math.Max(furthest, r.End)
		if r.Selected && !r.Invalid {
			exported = math.Max(exported, r.End)
		}
	}
	// Context is still retained. If it overlaps the next protected rally, divide
	// the idle gap at its midpoint rather than deleting ALL post/pre-roll.
	upper := make([]float64, len(ordered))
	ceiling := duration
	for i := len(ordered) - 1; i >= 0; i-- {
		upper[i] = ceiling
		if cut, ok := cuts[i]; ok {
			ceiling = cut
		}
	}
	spans := []Segment{}
	floor := 0.0
	for i, r := range ordered {
		if cut, ok := cuts[i]; ok {
			floor = cut
		}
		if !r.Selected || r.Invalid {
			continue
		}
		start := math.Max(floor, math.Max(0, r.Start-rules.PreRoll))
		end := math.Min(upper[i], math.Min(duration, r.End+rules.PostRoll))
		spans = append(spans, Segment{start, end})
	}
	sort.Slice(spans, func(i, j int) bool { return spans[i].Start < spans[j].Start })
	merged := []Segment{}
	for _, s := range spans {
		n := len(merged)
		if n > 0 && s.Start <= merged[n-1].End && !barriers[s.Start] {
			merged[n-1].End = math.Max(merged[n-1].End, s.End)
		} else {
			merged = append(merged, s)
		}
	}
	if len(merged) == 0 {
		return nil, fmt.Errorf("请至少选择一个回合")
	}
	return merged, nil
}

// overlapEpsilon ignores rounding-level touches between adjacent rallies.
const overlapEpsilon = 0.04

func exported(r project.Rally) bool { return r.Selected && !r.Invalid }

func overlaps(a, b project.Rally) bool {
	return math.Min(a.End, b.End)-math.Max(a.Start, b.Start) > overlapEpsilon
}

// ResolveOverlaps applies the export overlap policy between human and machine
// rallies. The losing rally is skipped entirely (returned deselected); the
// project timeline itself is not changed. Same-kind overlaps are left for
// Segments to merge, as is the "merge" policy.
func ResolveOverlaps(rs []project.Rally, mode string) []project.Rally {
	out := append([]project.Rally{}, rs...)
	if mode == "" || mode == project.OverlapMerge {
		return out
	}
	order := make([]int, 0, len(out))
	for i, r := range out {
		if exported(r) {
			order = append(order, i)
		}
	}
	sort.SliceStable(order, func(a, b int) bool { return out[order[a]].Start < out[order[b]].Start })
	hits := func(r project.Rally, wantHuman bool, among []int) bool {
		for _, j := range among {
			if out[j].IsHuman() == wantHuman && overlaps(r, out[j]) {
				return true
			}
		}
		return false
	}
	kept := []int{}
	for _, i := range order {
		r := out[i]
		drop := false
		switch mode {
		case project.OverlapHuman:
			drop = !r.IsHuman() && hits(r, true, order)
		case project.OverlapMachine:
			drop = r.IsHuman() && hits(r, false, order)
		case project.OverlapSequential:
			drop = hits(r, !r.IsHuman(), kept)
		}
		if drop {
			out[i].Selected = false
		} else {
			kept = append(kept, i)
		}
	}
	return out
}

// OverlapConflicts counts exported human/machine rally pairs that overlap.
func OverlapConflicts(rs []project.Rally) int {
	n := 0
	for i, a := range rs {
		for _, b := range rs[i+1:] {
			if exported(a) && exported(b) && a.IsHuman() != b.IsHuman() && overlaps(a, b) {
				n++
			}
		}
	}
	return n
}

// ExportSegments resolves human/machine overlaps with the configured policy
// and then builds the padded, coalesced export spans.
func ExportSegments(rs []project.Rally, rules project.Rules, settings project.ExportSettings, duration float64) ([]Segment, error) {
	segs, _, err := ExportPlan(rs, rules, settings, duration)
	return segs, err
}

// Label is the rally number burned into an exported span, shown from source
// time From until the next label (the first one covers the span start).
// Number is the rally's 1-based position in the source timeline, matching the
// "01, 02…" numbering on the rally cards.
type Label struct {
	Number int
	From   float64
}

// ExportPlan is ExportSegments plus, for each span, the exported rallies it
// contains in time order. A span can hold several rallies when padding or
// overlaps merged them.
func ExportPlan(rs []project.Rally, rules project.Rules, settings project.ExportSettings, duration float64) ([]Segment, [][]Label, error) {
	resolved := ResolveOverlaps(rs, settings.Normalized().Overlap)
	segs, err := Segments(resolved, rules, duration)
	if err != nil {
		return nil, nil, err
	}
	return segs, SegmentLabels(resolved, segs), nil
}

// SegmentLabels lists, per span, the exported rallies whose content overlaps
// it. rs must be in timeline order (indices become rally numbers).
func SegmentLabels(rs []project.Rally, segs []Segment) [][]Label {
	out := make([][]Label, len(segs))
	for k, seg := range segs {
		var labels []Label
		for i, r := range rs {
			if exported(r) && r.Start < seg.End && r.End > seg.Start {
				labels = append(labels, Label{Number: i + 1, From: math.Max(seg.Start, r.Start)})
			}
		}
		sort.SliceStable(labels, func(a, b int) bool { return labels[a].From < labels[b].From })
		if len(labels) > 0 {
			labels[0].From = seg.Start
		}
		out[k] = labels
	}
	return out
}

func Split(rs []project.Rally, id string, at float64) ([]project.Rally, error) {
	out := append([]project.Rally{}, rs...)
	for i, r := range out {
		if r.ID != id {
			continue
		}
		if !project.Finite(at) || at-r.Start < .04 || r.End-at < .04 {
			return nil, fmt.Errorf("拆分点必须位于回合内，且两侧至少 0.04 秒")
		}
		left, right := r, r
		left.End = at
		left.EndReason = ""
		left.EndEventTime = 0
		left.EndConfidence = 0
		right.Start = at
		right.BoundaryBefore = false
		right.StartReason = ""
		right.ID = project.NewID()
		left.Edited = true
		right.Edited = true
		out[i] = left
		out = append(out, right)
		project.Sort(out)
		return out, nil
	}
	return nil, fmt.Errorf("回合不存在")
}

func Merge(rs []project.Rally, ids []string) ([]project.Rally, error) {
	want := map[string]bool{}
	for _, id := range ids {
		want[id] = true
	}
	if len(want) < 2 {
		return nil, fmt.Errorf("请勾选至少两个回合")
	}
	ordered := append([]project.Rally{}, rs...)
	project.Sort(ordered)
	out := []project.Rally{}
	var merged *project.Rally
	found := 0
	first, last := -1, -1
	for i, r := range ordered {
		if !want[r.ID] {
			out = append(out, r)
			continue
		}
		if first < 0 {
			first = i
		}
		last = i
		found++
		if merged == nil {
			copy := r
			merged = &copy
		} else {
			merged.End = math.Max(merged.End, r.End)
			merged.Confidence = math.Min(merged.Confidence, r.Confidence)
			merged.Score = math.Max(merged.Score, r.Score)
		}
	}
	if found != len(want) || last-first+1 != found {
		return nil, fmt.Errorf("只能合并时间顺序上相邻的回合")
	}
	// Explicit manual merge overrides internal model boundaries, but retains
	// the outer boundaries of the first and last merged rallies.
	for _, r := range ordered {
		if want[r.ID] && r.End == merged.End {
			merged.EndReason = r.EndReason
			merged.EndEventTime = r.EndEventTime
			merged.EndConfidence = r.EndConfidence
		}
	}
	merged.Edited = true
	merged.Selected = true
	out = append(out, *merged)
	project.Sort(out)
	return out, nil
}
