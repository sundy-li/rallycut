//go:build !windows

package childproc

import "os/exec"

func configure(cmd *exec.Cmd)       {}
func configureDialog(cmd *exec.Cmd) {}
