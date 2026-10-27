package backend

import (
	"context"
	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

// MainWindowClassName identifies our own window even before it becomes visible.
const MainWindowClassName = "RallyCutMainWindow"

// Geometry is in physical desktop pixels. Convert only Wails' minimum size to
// DIP; never mix physical positioning with the logical Screen.Size dimensions.
type desktopRect struct{ Left, Top, Right, Bottom int }
type windowPlan struct {
	Rect                desktopRect
	MinWidth, MinHeight int
}

func fitWindowRect(current, work desktopRect, dpi int) (windowPlan, bool) {
	if dpi <= 0 {
		dpi = 96
	}
	if current.Right <= current.Left || current.Bottom <= current.Top || work.Right <= work.Left || work.Bottom <= work.Top {
		return windowPlan{}, false
	}
	margin := (8*dpi + 95) / 96
	mx := min(margin, (work.Right-work.Left-1)/2)
	my := min(margin, (work.Bottom-work.Top-1)/2)
	available := desktopRect{work.Left + mx, work.Top + my, work.Right - mx, work.Bottom - my}
	maxW, maxH := available.Right-available.Left, available.Bottom-available.Top
	plan := windowPlan{MinWidth: max(1, min(960, maxW*96/dpi)), MinHeight: max(1, min(600, maxH*96/dpi))}
	width := min(maxW, max((plan.MinWidth*dpi+48)/96, current.Right-current.Left))
	height := min(maxH, max((plan.MinHeight*dpi+48)/96, current.Bottom-current.Top))
	plan.Rect = current
	if width != current.Right-current.Left || height != current.Bottom-current.Top || current.Left < available.Left || current.Top < available.Top || current.Right > available.Right || current.Bottom > available.Bottom {
		x, y := available.Left+(maxW-width)/2, available.Top+(maxH-height)/2
		plan.Rect = desktopRect{x, y, x + width, y + height}
	}
	return plan, true
}

func focusWindow(ctx context.Context) {
	focusExistingWindow(func() bool { return wruntime.WindowIsMinimised(ctx) }, func() { wruntime.WindowUnminimise(ctx) }, func() { wruntime.WindowShow(ctx) })
}
func focusExistingWindow(minimized func() bool, restore, show func()) {
	if minimized() {
		restore()
	}
	show()
}
