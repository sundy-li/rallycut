// Package childproc starts internal helpers without console windows on Windows.
// Captured stdout/stderr and context cancellation remain unchanged.
package childproc

import (
	"context"
	"os/exec"
)

func Command(name string, args ...string) *exec.Cmd {
	cmd := exec.Command(name, args...)
	configure(cmd)
	return cmd
}
func CommandContext(ctx context.Context, name string, args ...string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, name, args...)
	configure(cmd)
	return cmd
}

// DialogContext keeps user-requested native dialogs visible while preventing
// their console host (e.g. PowerShell) from opening an extra DOS window.
func DialogContext(ctx context.Context, name string, args ...string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, name, args...)
	configureDialog(cmd)
	return cmd
}
