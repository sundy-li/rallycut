//go:build windows

package backend

import (
	"context"
	"fmt"
	"os"
	"syscall"
	"unsafe"

	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
	"golang.org/x/sys/windows"
)

type winRect struct{ Left, Top, Right, Bottom int32 }
type monitorInfo struct {
	Size          uint32
	Monitor, Work winRect
	Flags         uint32
}

var windowUser32 = windows.NewLazySystemDLL("user32.dll")
var (
	getWindowClass    = windowUser32.NewProc("GetClassNameW")
	getWindowBounds   = windowUser32.NewProc("GetWindowRect")
	monitorFromWindow = windowUser32.NewProc("MonitorFromWindow")
	getMonitorInfo    = windowUser32.NewProc("GetMonitorInfoW")
	getWindowDPI      = windowUser32.NewProc("GetDpiForWindow")
	setWindowPosition = windowUser32.NewProc("SetWindowPos")
)

func mainWindowHandle() windows.Handle {
	var result windows.Handle
	_ = windows.EnumWindows(syscall.NewCallback(func(hwnd uintptr, _ uintptr) uintptr {
		var pid uint32
		_, err := windows.GetWindowThreadProcessId(windows.HWND(hwnd), &pid)
		if err != nil || pid != uint32(os.Getpid()) {
			return 1
		}
		var name [256]uint16
		n, _, _ := getWindowClass.Call(hwnd, uintptr(unsafe.Pointer(&name[0])), uintptr(len(name)))
		if n > 0 && windows.UTF16ToString(name[:]) == MainWindowClassName {
			result = windows.Handle(hwnd)
			return 0
		}
		return 1
	}), nil)
	return result
}
func nativeWindowMetrics(hwnd windows.Handle) (desktopRect, desktopRect, int, error) {
	var rect winRect
	if ok, _, err := getWindowBounds.Call(uintptr(hwnd), uintptr(unsafe.Pointer(&rect))); ok == 0 {
		return desktopRect{}, desktopRect{}, 0, fmt.Errorf("GetWindowRect: %v", err)
	}
	monitor, _, _ := monitorFromWindow.Call(uintptr(hwnd), 2) // MONITOR_DEFAULTTONEAREST
	if monitor == 0 {
		return desktopRect{}, desktopRect{}, 0, fmt.Errorf("no current monitor")
	}
	info := monitorInfo{Size: uint32(unsafe.Sizeof(monitorInfo{}))}
	if ok, _, err := getMonitorInfo.Call(monitor, uintptr(unsafe.Pointer(&info))); ok == 0 {
		return desktopRect{}, desktopRect{}, 0, fmt.Errorf("GetMonitorInfoW: %v", err)
	}
	dpi := 96
	if getWindowDPI.Find() == nil {
		if value, _, _ := getWindowDPI.Call(uintptr(hwnd)); value > 0 {
			dpi = int(value)
		}
	}
	convert := func(r winRect) desktopRect { return desktopRect{int(r.Left), int(r.Top), int(r.Right), int(r.Bottom)} }
	return convert(rect), convert(info.Work), dpi, nil
}
func positionWindow(hwnd windows.Handle, rect desktopRect) error {
	// HWND coordinates and RcWork share physical desktop pixels, including
	// negative origins and taskbars on any edge. Do not steal foreground focus.
	ok, _, err := setWindowPosition.Call(uintptr(hwnd), 0, uintptr(rect.Left), uintptr(rect.Top), uintptr(rect.Right-rect.Left), uintptr(rect.Bottom-rect.Top), 0x0014) // NOZORDER | NOACTIVATE
	if ok == 0 {
		return fmt.Errorf("SetWindowPos: %v", err)
	}
	return nil
}
func fitWindowToScreen(ctx context.Context) {
	hwnd := mainWindowHandle()
	if hwnd == 0 {
		return
	}
	rect, work, dpi, err := nativeWindowMetrics(hwnd)
	if err != nil {
		return
	}
	plan, ok := fitWindowRect(rect, work, dpi)
	if !ok {
		return
	}
	// Lower the minimum before resizing: Wails clamps sizes to this minimum.
	wruntime.WindowSetMinSize(ctx, plan.MinWidth, plan.MinHeight)
	_ = positionWindow(hwnd, plan.Rect)
}
