package media

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

// RevealCommand returns the argv that selects path in the OS file manager.
// Arguments are passed as an array; nothing goes through a shell.
func RevealCommand(path string) (string, []string) {
	switch runtime.GOOS {
	case "darwin":
		return "open", []string{"-R", path}
	case "windows":
		return "explorer", []string{"/select," + path}
	default:
		// xdg-open cannot select a file; open its folder instead.
		return "xdg-open", []string{filepath.Dir(path)}
	}
}

// Reveal shows an existing regular file in Finder / Explorer.
func Reveal(ctx context.Context, path string) error {
	if !filepath.IsAbs(path) {
		return fmt.Errorf("导出路径无效")
	}
	info, err := os.Stat(path)
	if err != nil || !info.Mode().IsRegular() {
		return fmt.Errorf("导出文件不存在，可能已被移动或删除：%s", path)
	}
	name, args := RevealCommand(path)
	cmd := exec.CommandContext(ctx, name, args...)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("无法打开文件夹: %w", err)
	}
	// explorer.exe returns non-zero even on success; only reap the process.
	go func() { _ = cmd.Wait() }()
	return nil
}
