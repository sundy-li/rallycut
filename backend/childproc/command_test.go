package childproc

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"testing"
	"time"
)

func TestCommandHelper(t *testing.T) {
	switch os.Getenv("RALLYCUT_COMMAND_TEST") {
	case "output":
		fmt.Print("captured stdout")
		fmt.Fprint(os.Stderr, "captured stderr")
		os.Exit(7)
	case "wait":
		time.Sleep(30 * time.Second)
		os.Exit(0)
	}
}
func TestSilentCommandPreservesOutputAndExitError(t *testing.T) {
	cmd := Command(os.Args[0], "-test.run=^TestCommandHelper$")
	cmd.Env = append(os.Environ(), "RALLYCUT_COMMAND_TEST=output")
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	var exit *exec.ExitError
	if !errors.As(err, &exit) || exit.ExitCode() != 7 || stdout.String() != "captured stdout" || stderr.String() != "captured stderr" {
		t.Fatalf("lost diagnostics: %v %q %q", err, stdout.String(), stderr.String())
	}
}
func TestSilentCommandIsCancelled(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 150*time.Millisecond)
	defer cancel()
	cmd := CommandContext(ctx, os.Args[0], "-test.run=^TestCommandHelper$")
	cmd.Env = append(os.Environ(), "RALLYCUT_COMMAND_TEST=wait")
	start := time.Now()
	err := cmd.Run()
	if err == nil || ctx.Err() != context.DeadlineExceeded || time.Since(start) > 5*time.Second {
		t.Fatalf("cancellation not propagated: %v", err)
	}
	if strings.Contains(err.Error(), "not found") {
		t.Fatal(err)
	}
}
