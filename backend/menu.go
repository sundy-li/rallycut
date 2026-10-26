package backend

import (
	"runtime"

	"github.com/wailsapp/wails/v2/pkg/menu"
	"github.com/wailsapp/wails/v2/pkg/menu/keys"
	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

// Menu events the frontend listens for (frontend/src/api/client.ts subscribeMenu).
const (
	MenuEventSettings  = "menu:settings"
	MenuEventShortcuts = "menu:shortcuts"
	MenuEventHelp      = "menu:help"
)

// ApplicationMenu builds the native macOS menu bar; other platforms get nil
// (no window menu bar). The first submenu becomes the macOS app menu, which
// holds "设置… ⌘," per platform convention.
//
// There is deliberately no Edit menu: its Undo / Redo items would claim ⌘Z /
// ⇧⌘Z for the WebView's text undo, while the app's project undo is handled in
// the frontend keydown handler. Without a menu Wails installs no Edit menu
// either, so this keeps the previous keyboard behaviour.
func ApplicationMenu(a *App) *menu.Menu {
	if runtime.GOOS != "darwin" {
		return nil
	}
	return buildApplicationMenu(a)
}

func buildApplicationMenu(a *App) *menu.Menu {
	emit := func(name string) menu.Callback {
		return func(*menu.CallbackData) {
			if a.ctx != nil {
				wruntime.EventsEmit(a.ctx, name)
			}
		}
	}
	withCtx := func(f func()) menu.Callback {
		return func(*menu.CallbackData) {
			if a.ctx != nil {
				f()
			}
		}
	}
	root := menu.NewMenu()

	app := root.AddSubmenu("RallyCut")
	app.AddText("设置…", keys.CmdOrCtrl(","), emit(MenuEventSettings))
	app.AddSeparator()
	app.AddText("隐藏 RallyCut", keys.CmdOrCtrl("h"), withCtx(func() { wruntime.Hide(a.ctx) }))
	app.AddText("退出 RallyCut", keys.CmdOrCtrl("q"), withCtx(func() { wruntime.Quit(a.ctx) }))

	window := root.AddSubmenu("窗口")
	window.AddText("最小化", keys.CmdOrCtrl("m"), withCtx(func() { wruntime.WindowMinimise(a.ctx) }))
	window.AddText("缩放", nil, withCtx(func() { wruntime.WindowToggleMaximise(a.ctx) }))
	window.AddText("切换全屏", &keys.Accelerator{Key: "f", Modifiers: []keys.Modifier{keys.CmdOrCtrlKey, keys.ControlKey}}, withCtx(func() {
		if wruntime.WindowIsFullscreen(a.ctx) {
			wruntime.WindowUnfullscreen(a.ctx)
		} else {
			wruntime.WindowFullscreen(a.ctx)
		}
	}))

	help := root.AddSubmenu("帮助")
	help.AddText("快捷键", keys.CmdOrCtrl("/"), emit(MenuEventShortcuts))
	help.AddText("使用说明", nil, emit(MenuEventHelp))
	return root
}
