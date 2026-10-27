//go:build !windows

package backend

import (
	"context"
	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

// Preserve the previous conservative logical-size fitting on macOS/Linux.
// Re-centering stays native; do not apply Win32 physical desktop coordinates.
func fitWindowToScreen(ctx context.Context) {
	screens, err := wruntime.ScreenGetAll(ctx)
	if err != nil || len(screens) == 0 {
		return
	}
	screen := screens[0]
	for _, s := range screens {
		if s.IsCurrent {
			screen = s
			break
		}
	}
	maxW, maxH := screen.Size.Width-64, screen.Size.Height-88
	if maxW <= 0 || maxH <= 0 {
		return
	}
	width, height := wruntime.WindowGetSize(ctx)
	if width <= maxW && height <= maxH {
		return
	}
	wruntime.WindowSetMinSize(ctx, min(960, maxW), min(600, maxH))
	wruntime.WindowSetSize(ctx, min(width, maxW), min(height, maxH))
	wruntime.WindowCenter(ctx)
}
