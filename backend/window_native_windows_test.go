//go:build windows

package backend

import (
	"runtime"
	"testing"
	"unsafe"

	"golang.org/x/sys/windows"
)

func TestNativeWindowFitsCurrentWindowsWorkArea(t *testing.T) {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	// The Go test executable has no per-monitor manifest; opt this test thread
	// into the same coordinate space as the production Wails executable.
	awareness := windowUser32.NewProc("SetThreadDpiAwarenessContext")
	if awareness.Find() != nil {
		t.Skip("requires Windows 10 per-monitor DPI")
	}
	previous, _, _ := awareness.Call(^uintptr(3)) // DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
	if previous == 0 {
		t.Fatal("could not enable per-monitor DPI for native test")
	}
	defer awareness.Call(previous)
	class, _ := windows.UTF16PtrFromString("STATIC")
	title, _ := windows.UTF16PtrFromString("RallyCut geometry regression")
	hwnd, _, err := windowUser32.NewProc("CreateWindowExW").Call(0, uintptr(unsafe.Pointer(class)), uintptr(unsafe.Pointer(title)), 0x00cf0000, 0, 0, 1800, 1200, 0, 0, 0, 0)
	if hwnd == 0 {
		t.Fatalf("create hidden test window: %v", err)
	}
	defer windowUser32.NewProc("DestroyWindow").Call(hwnd)
	before, work, dpi, err := nativeWindowMetrics(windows.Handle(hwnd))
	if err != nil {
		t.Fatal(err)
	}
	plan, ok := fitWindowRect(before, work, dpi)
	if !ok {
		t.Fatal("could not fit test window")
	}
	if err := positionWindow(windows.Handle(hwnd), plan.Rect); err != nil {
		t.Fatal(err)
	}
	after, _, _, err := nativeWindowMetrics(windows.Handle(hwnd))
	if err != nil {
		t.Fatal(err)
	}
	if after.Left < work.Left || after.Top < work.Top || after.Right > work.Right || after.Bottom > work.Bottom {
		t.Fatalf("native window outside real work area: %+v %+v", after, work)
	}
	t.Logf("native DPI=%d work=%+v fitted=%+v", dpi, work, after)
}
