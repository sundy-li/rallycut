package jobs

import (
	"context"
	"errors"
	"rallycut/backend/project"
	"sync"
	"testing"
)

func TestSingleFlightCancellationAndRetry(t *testing.T) {
	var m Manager
	var mu sync.Mutex
	var terminal project.Job
	notify := func(j project.Job) { mu.Lock(); terminal = j; mu.Unlock() }
	_, err := m.Start(context.Background(), "analysis", notify, func(ctx context.Context, p func(float64, string)) (string, error) {
		p(.5, "half")
		<-ctx.Done()
		return "", ctx.Err()
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := m.Start(context.Background(), "export", notify, nil); err == nil {
		t.Fatal("concurrent work accepted")
	}
	m.Cancel()
	m.Wait()
	mu.Lock()
	status := terminal.Status
	mu.Unlock()
	if status != "cancelled" || m.Busy() {
		t.Fatalf("bad cancellation: %s", status)
	}
	_, err = m.Start(context.Background(), "analysis", notify, func(context.Context, func(float64, string)) (string, error) {
		return "", errors.New("expected failure")
	})
	if err != nil {
		t.Fatal(err)
	}
	m.Wait()
	mu.Lock()
	status = terminal.Status
	mu.Unlock()
	if status != "failed" {
		t.Fatal(status)
	}
	_, err = m.Start(context.Background(), "export", notify, func(context.Context, func(float64, string)) (string, error) { return "out.mp4", nil })
	if err != nil {
		t.Fatal(err)
	}
	m.Wait()
	mu.Lock()
	defer mu.Unlock()
	if terminal.Status != "completed" || terminal.Output != "out.mp4" {
		t.Fatal(terminal)
	}
}

func TestCurrentIDFollowsRunningJob(t *testing.T) {
	var m Manager
	block := make(chan struct{})
	job, err := m.Start(context.Background(), "analysis", func(project.Job) {},
		func(ctx context.Context, p func(float64, string)) (string, error) {
			<-block
			return "", nil
		})
	if err != nil {
		t.Fatal(err)
	}
	if job.ID == "" || m.CurrentID() != job.ID {
		t.Fatalf("current id %q does not match job %q", m.CurrentID(), job.ID)
	}
	close(block)
	m.Wait()
	if m.CurrentID() != "" {
		t.Fatalf("id kept after finish: %q", m.CurrentID())
	}
}
