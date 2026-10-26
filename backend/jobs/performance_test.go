package jobs

import (
	"context"
	"rallycut/backend/project"
	"sync"
	"testing"
)

func TestPerformanceUsesExistingProgressAndOwnsSnapshot(t *testing.T) {
	var manager Manager
	var lock sync.Mutex
	jobs := []project.Job{}
	_, err := manager.Start(context.Background(), "analysis", func(job project.Job) { lock.Lock(); jobs = append(jobs, job); lock.Unlock() },
		func(_ context.Context, progress func(float64, string)) (string, error) {
			p := &project.Performance{Stage: "inference", ProcessedFrames: 120, ElapsedSeconds: 1, AverageFPS: 120, RecentFPS: 120}
			manager.UpdatePerformance(p)
			p.AverageFPS = 999
			progress(.5, "measured")
			return "", nil
		})
	if err != nil {
		t.Fatal(err)
	}
	manager.Wait()
	lock.Lock()
	defer lock.Unlock()
	if len(jobs) != 3 {
		t.Fatal("extra performance event/fsync", len(jobs))
	}
	if jobs[1].Performance == nil || jobs[1].Performance.AverageFPS != 120 || jobs[2].Performance.AverageFPS != 120 {
		t.Fatal(jobs)
	}
	p := project.New(project.Video{Path: "source", Duration: 10})
	p.Job = &jobs[2]
	clone := project.Clone(p)
	clone.Job.Performance.AverageFPS = 7
	if p.Job.Performance.AverageFPS != 120 {
		t.Fatal("project clone aliases live metrics")
	}
}
