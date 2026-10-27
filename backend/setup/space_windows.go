//go:build windows

package setup

import (
	"fmt"
	"golang.org/x/sys/windows"
)

func checkFreeSpace(path string, need int64) error {
	p, err := windows.UTF16PtrFromString(path)
	if err != nil {
		return err
	}
	var free, total, available uint64
	if err := windows.GetDiskFreeSpaceEx(p, &available, &total, &free); err != nil {
		return err
	}
	if available < uint64(need) {
		return fmt.Errorf("磁盘空间不足：需要约 %.1f GB，可用 %.1f GB", float64(need)/(1<<30), float64(available)/(1<<30))
	}
	return nil
}
