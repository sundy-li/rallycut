//go:build windows

package media

import (
	"path/filepath"
	"testing"
)

func TestWindowsUNCPathsStayAbsoluteWithoutDrivePrefix(t *testing.T) {
	for _, path := range []string{`\\Mac\Home\Documents\生活\video\hezuocheng.mp4`, `\\服务器\共享目录\比赛 #100% & 对拉.mp4`} {
		if !filepath.IsAbs(path) {
			t.Fatalf("UNC path not absolute: %q", path)
		}
		got, err := filepath.Abs(path)
		if err != nil || got != path {
			t.Fatalf("UNC rewritten to local drive: %q → %q (%v)", path, got, err)
		}
	}
}
