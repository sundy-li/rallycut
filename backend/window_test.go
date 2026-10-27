package backend

import "testing"

func TestWindowFitKeepsFrameInsideRealWorkArea(t *testing.T) {
	cases := []struct {
		name          string
		work, current desktopRect
		dpi           int
	}{
		{"1366x768 at 125%", desktopRect{0, 0, 1366, 718}, desktopRect{0, -32, 1800, 1143}, 120},
		{"150% negative left monitor", desktopRect{-1920, 0, 0, 1032}, desktopRect{-2000, -30, 240, 1380}, 144},
		{"top taskbar", desktopRect{0, 48, 1366, 768}, desktopRect{0, -32, 1440, 908}, 96},
		{"left taskbar and right monitor", desktopRect{2016, 0, 3840, 1080}, desktopRect{1900, -20, 4060, 1390}, 144},
		{"tiny remote desktop 200%", desktopRect{0, 0, 800, 560}, desktopRect{0, 0, 2880, 1880}, 192},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			plan, ok := fitWindowRect(c.current, c.work, c.dpi)
			if !ok {
				t.Fatal("missing fit plan")
			}
			r := plan.Rect
			if r.Left < c.work.Left || r.Top < c.work.Top || r.Right > c.work.Right || r.Bottom > c.work.Bottom {
				t.Fatalf("window clipped by work area: %+v in %+v", r, c.work)
			}
			if plan.MinWidth*c.dpi/96 > r.Right-r.Left || plan.MinHeight*c.dpi/96 > r.Bottom-r.Top {
				t.Fatalf("minimum cancels resizing: %+v", plan)
			}
			if c.dpi == 120 && plan.MinHeight >= 600 {
				t.Fatal("125% small display still requests 600 DIP")
			}
		})
	}
}
func TestWindowFitPreservesAlreadyVisiblePosition(t *testing.T) {
	current := desktopRect{200, 100, 1200, 800}
	plan, ok := fitWindowRect(current, desktopRect{0, 0, 1920, 1040}, 96)
	if !ok || plan.Rect != current {
		t.Fatalf("visible window was needlessly moved: %+v", plan)
	}
	if _, ok := fitWindowRect(current, desktopRect{}, 96); ok {
		t.Fatal("accepted invalid work area")
	}
}
func TestSecondLaunchOnlyRestoresMinimizedWindow(t *testing.T) {
	for _, minimized := range []bool{false, true} {
		restored, shown := 0, 0
		focusExistingWindow(func() bool { return minimized }, func() { restored++ }, func() { shown++ })
		if shown != 1 || (minimized && restored != 1) || (!minimized && restored != 0) {
			t.Fatalf("unexpected restore: minimized=%v restored=%d shown=%d", minimized, restored, shown)
		}
	}
}
