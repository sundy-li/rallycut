//go:build !windows

package setup

import (
	"fmt"
	"syscall"
)

func checkFreeSpace(path string, need int64) error {
	var s syscall.Statfs_t
	if err := syscall.Statfs(path, &s); err != nil {
		return err
	}
	available := uint64(s.Bavail) * uint64(s.Bsize)
	if available < uint64(need) {
		return fmt.Errorf("磁盘空间不足：需要约 %.1f GB，可用 %.1f GB", float64(need)/(1<<30), float64(available)/(1<<30))
	}
	return nil
}
