package backend

import (
	"fmt"
	"slices"
	"time"

	"rallycut/backend/project"
	"rallycut/backend/storage"
)

const maxTimelineHistory = 100

// timelineSnapshot is the editable part of a project. Export settings, names
// and sources are deliberately excluded: undo only covers cutting work.
type timelineSnapshot struct {
	Rallies []project.Rally
	Rules   project.Rules
	Manual  bool
	Partial bool
}

type timelineHistory struct {
	undo []timelineSnapshot
	redo []timelineSnapshot
}

func snapshotTimeline(p *project.Project) timelineSnapshot {
	return timelineSnapshot{
		Rallies: append([]project.Rally(nil), p.Rallies...),
		Rules:   p.Rules,
		Manual:  p.ManualTimeline,
		Partial: p.PartialAnalysis,
	}
}

func (s timelineSnapshot) equal(other timelineSnapshot) bool {
	return slices.Equal(s.Rallies, other.Rallies) && s.Rules == other.Rules &&
		s.Manual == other.Manual && s.Partial == other.Partial
}

func (s timelineSnapshot) apply(p *project.Project) {
	p.Rallies = append([]project.Rally(nil), s.Rallies...)
	p.Rules = s.Rules
	p.ManualTimeline = s.Manual
	p.PartialAnalysis = s.Partial
}

func pushSnapshot(stack []timelineSnapshot, s timelineSnapshot) []timelineSnapshot {
	stack = append(stack, s)
	if len(stack) > maxTimelineHistory {
		stack = append([]timelineSnapshot(nil), stack[len(stack)-maxTimelineHistory:]...)
	}
	return stack
}

// recordLocked stores before as an undo step after a successful user edit.
// Requires a.mu. Automatic fills of an empty timeline are not user edits.
func (a *App) recordLocked(before timelineSnapshot, after *project.Project) {
	if len(before.Rallies) == 0 || before.equal(snapshotTimeline(after)) {
		return
	}
	a.history.undo = pushSnapshot(a.history.undo, before)
	a.history.redo = nil
}

// clearHistoryLocked drops history when the timeline it refers to is replaced
// (project switch, source switch, analysis result). Requires a.mu.
func (a *App) clearHistoryLocked() {
	a.history = timelineHistory{}
}

// Undo restores the previous editing state and saves it immediately.
func (a *App) Undo() (*project.Project, error) { return a.stepHistory(true) }

// Redo re-applies the last undone editing state and saves it immediately.
func (a *App) Redo() (*project.Project, error) { return a.stepHistory(false) }

func (a *App) stepHistory(undo bool) (*project.Project, error) {
	a.opMu.Lock()
	defer a.opMu.Unlock()
	if err := a.ready(); err != nil {
		return nil, err
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.current == nil {
		return nil, fmt.Errorf("请先打开项目")
	}
	from, to := &a.history.undo, &a.history.redo
	if !undo {
		from, to = to, from
	}
	if len(*from) == 0 {
		if undo {
			return nil, fmt.Errorf("没有可撤销的操作")
		}
		return nil, fmt.Errorf("没有可重做的操作")
	}
	target := (*from)[len(*from)-1]
	current := snapshotTimeline(a.current)
	next := project.Clone(a.current)
	target.apply(next)
	next.AdoptAnalysisCandidatesIfEmpty()
	next.SyncActive()
	if err := next.Validate(); err != nil {
		return nil, err
	}
	next.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	if err := storage.WriteJSON(a.projectPath, next); err != nil {
		return nil, err
	}
	*from = (*from)[:len(*from)-1]
	*to = pushSnapshot(*to, current)
	a.current = next
	a.rememberProject(a.projectPath, next, false)
	return project.Clone(next), nil
}
