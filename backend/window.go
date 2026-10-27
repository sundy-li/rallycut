package backend

import (
	"context"

	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

// fitWindowToScreen shrinks and re-centres the initial window when the desktop
// is smaller than the configured size.
//
// Wails does not clamp the window to the work area. On a 1396x760 desktop the
// 1440x940 window was placed at y=-32, so the whole native title bar (and its
// close button) sat above the top edge and the app could only be closed from
// the taskbar. Keep the frame reachable instead of trusting the screen size.
func fitWindowToScreen(ctx context.Context) {
	screens, err := wruntime.ScreenGetAll(ctx)
	if err != nil || len(screens) == 0 {
		return
	}
	screen := screens[0]
	for _, candidate := range screens {
		if candidate.IsCurrent {
			screen = candidate
			break
		}
	}
	// Reserve room for the native title bar and the taskbar. Reserving the whole
	// frame twice (as before) shrank the window more than necessary.
	maxWidth := screen.Size.Width - 64
	maxHeight := screen.Size.Height - 88
	if maxWidth <= 0 || maxHeight <= 0 {
		return
	}
	width, height := wruntime.WindowGetSize(ctx)
	if width <= maxWidth && height <= maxHeight {
		return
	}
	if width > maxWidth {
		width = maxWidth
	}
	if height > maxHeight {
		height = maxHeight
	}
	wruntime.WindowSetSize(ctx, width, height)
	// Centre explicitly: WindowCenter alone left the frame 4px above the top
	// edge on this desktop, because the outer frame is larger than the size
	// reported for the client area.
	x := (screen.Size.Width - width) / 2
	y := (screen.Size.Height - height) / 2
	if x < 8 {
		x = 8
	}
	if y < 8 {
		y = 8
	}
	wruntime.WindowSetPosition(ctx, x, y)
}
