package jobs

import (
	"context"
	"fmt"
	"rallycut/backend/project"
	"sync"
	"time"
)

type Notify func(project.Job)
type Work func(context.Context, func(float64, string)) (string, error)
type Manager struct {
	mu      sync.Mutex
	cancel  context.CancelFunc
	current *project.Job
	done    chan struct{}
}

func (m *Manager) Start(parent context.Context, kind string, notify Notify, work Work) (project.Job, error) {
	m.mu.Lock()
	if m.cancel != nil {
		m.mu.Unlock()
		return project.Job{}, fmt.Errorf("请等待当前任务结束")
	}
	ctx, cancel := context.WithCancel(parent)
	started := time.Now()
	j := project.Job{ID: project.NewID(), Kind: kind, Status: "running", Message: "准备中"}
	m.current = &j
	m.cancel = cancel
	m.done = make(chan struct{})
	done := m.done
	m.mu.Unlock()
	notify(j)
	go func() {
		defer close(done)
		defer cancel()
		progress := func(p float64, msg string) {
			m.mu.Lock()
			next := *m.current
			if next.Status == "cancelling" {
				m.mu.Unlock()
				return
			}
			if p < 0 {
				p = 0
			}
			if p > 1 {
				p = 1
			}
			if p < next.Progress {
				p = next.Progress
			}
			next.ElapsedSeconds = time.Since(started).Seconds()
			next.Progress = p
			next.Message = msg
			m.current = &next
			m.mu.Unlock()
			notify(next)
		}
		output, err := work(ctx, progress)
		m.mu.Lock()
		next := *m.current
		next.ElapsedSeconds = time.Since(started).Seconds()
		if ctx.Err() != nil && err != nil {
			next.Status = "cancelled"
			next.Message = "任务已取消"
		} else if err != nil {
			next.Status = "failed"
			next.Message = err.Error()
		} else {
			next.Status = "completed"
			next.Progress = 1
			next.Message = "任务完成"
			next.Output = output
		}
		m.current = &next
		// Keep the slot occupied until the final state is persisted and emitted.
		m.mu.Unlock()
		notify(next)
		m.mu.Lock()
		m.cancel = nil
		m.mu.Unlock()
	}()
	return j, nil
}

// UpdatePerformance does not emit an extra event or fsync. The following
// existing progress callback carries this immutable snapshot to the frontend.
func (m *Manager) UpdatePerformance(performance *project.Performance) {
	if performance == nil || performance.Validate() != nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.current == nil || m.current.Status != "running" {
		return
	}
	copy := *performance
	next := *m.current
	next.Performance = &copy
	m.current = &next
}

// UpdateCandidates stores provisional rallies on the running job so the next
// progress notification can carry them to the UI.
func (m *Manager) UpdateCandidates(rallies []project.Rally, processed float64) {
	if len(rallies) == 0 {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.current == nil || m.current.Status != "running" {
		return
	}
	next := *m.current
	next.Candidates = append([]project.Rally(nil), rallies...)
	next.ProcessedSeconds = processed
	m.current = &next
}

// CurrentID returns the running job's ID, or "" when no job is running.
func (m *Manager) CurrentID() string {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.current == nil || m.current.Status != "running" {
		return ""
	}
	return m.current.ID
}

func (m *Manager) Cancel() {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.cancel != nil {
		next := *m.current
		next.Status = "cancelling"
		m.current = &next
		m.cancel()
	}
}
func (m *Manager) Busy() bool { m.mu.Lock(); defer m.mu.Unlock(); return m.cancel != nil }
func (m *Manager) Wait() {
	m.mu.Lock()
	done := m.done
	m.mu.Unlock()
	if done != nil {
		<-done
	}
}
