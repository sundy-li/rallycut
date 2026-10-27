//go:build !windows

package childproc

import "os/exec"

func configure(cmd *exec.Cmd)       {}
func configureDialog(cmd *exec.Cmd) {}

// Init is a no-op outside Windows: there is no job object to create.
func Init() error { return nil }
