//go:build windows

package childproc

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"testing"
	"time"

	"golang.org/x/sys/windows"
)

type helperPID struct {
	Kind string `json:"kind"`
	PID  uint32 `json:"pid"`
}

func TestJobLifetimeHelper(t *testing.T) {
	role := os.Getenv("RALLYCUT_JOB_HELPER")
	if role == "" {
		return
	}
	if role == "supervisor" {
		if err := Init(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		startLifetimeChild("child")
	} else if role == "child" {
		reportLifetimePID(role)
		startLifetimeChild("grandchild")
	} else {
		reportLifetimePID(role)
	}
	for {
		time.Sleep(time.Hour)
	}
}
func startLifetimeChild(role string) {
	cmd := Command(os.Args[0], "-test.run=^TestJobLifetimeHelper$")
	// Replace instead of appending duplicate environment keys on Windows.
	env := os.Environ()
	for i, entry := range env {
		if len(entry) >= len("RALLYCUT_JOB_HELPER=") && entry[:len("RALLYCUT_JOB_HELPER=")] == "RALLYCUT_JOB_HELPER=" {
			env[i] = "RALLYCUT_JOB_HELPER=" + role
			cmd.Env = env
			break
		}
	}
	if cmd.Env == nil {
		cmd.Env = append(env, "RALLYCUT_JOB_HELPER="+role)
	}
	cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
	if err := cmd.Start(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(3)
	}
}
func reportLifetimePID(role string) {
	data, _ := json.Marshal(helperPID{Kind: role, PID: uint32(os.Getpid())})
	fmt.Println(string(data))
}
func TestForceClosedAppReapsChildAndGrandchild(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	cmd := CommandContext(ctx, os.Args[0], "-test.run=^TestJobLifetimeHelper$")
	cmd.Env = append(os.Environ(), "RALLYCUT_JOB_HELPER=supervisor")
	pipe, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { _ = cmd.Process.Kill(); _ = cmd.Wait() }()
	pids := make(chan helperPID, 2)
	go func() {
		scanner := bufio.NewScanner(pipe)
		for scanner.Scan() {
			var pid helperPID
			if json.Unmarshal(scanner.Bytes(), &pid) == nil {
				pids <- pid
			}
		}
		close(pids)
	}()
	handles := map[string]windows.Handle{}
	for len(handles) < 2 {
		select {
		case pid, ok := <-pids:
			if !ok {
				t.Fatal("supervisor exited before children were ready")
			}
			if pid.PID == 0 || (pid.Kind != "child" && pid.Kind != "grandchild") {
				t.Fatalf("invalid helper PID: %+v", pid)
			}
			h, err := windows.OpenProcess(windows.SYNCHRONIZE|windows.PROCESS_TERMINATE, false, pid.PID)
			if err != nil {
				t.Fatal(err)
			}
			handles[pid.Kind] = h
			defer func() { _ = windows.TerminateProcess(h, 1); _ = windows.CloseHandle(h) }() // Cleanup even if the regression fails.
		case <-ctx.Done():
			t.Fatal("helper startup timed out")
		}
	}
	// Kill only the supervisor, as Task Manager would. No explicit child cancel.
	if err := cmd.Process.Kill(); err != nil {
		t.Fatal(err)
	}
	for role, h := range handles {
		state, err := windows.WaitForSingleObject(h, 5000)
		if err != nil || state != windows.WAIT_OBJECT_0 {
			t.Fatalf("orphan survived parent termination: %s wait=%d error=%v", role, state, err)
		}
	}
	t.Log("PASS: force-killing only the supervisor terminates both child and grandchild through its Job Object")
}
