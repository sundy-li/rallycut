package main

import (
	"embed"
	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
	"github.com/wailsapp/wails/v2/pkg/options/windows"
	"log"
	"rallycut/backend"
	"rallycut/backend/childproc"
)

//go:embed all:frontend/dist
var assets embed.FS

func main() {
	// Helper processes must not outlive the app: a force-closed RallyCut used to
	// leave the Python analysis worker running for the rest of the video.
	if err := childproc.Init(); err != nil {
		log.Printf("无法创建子进程作业对象，强制结束后可能残留分析进程：%v", err)
	}
	app := backend.NewApp()
	messages := windows.DefaultMessages()
	messages.InstallationRequired = "RallyCut 的窗口需要 Microsoft WebView2。点击确定后下载安装，取消则退出。安装完成后才会打开应用内的环境准备页。"
	messages.UpdateRequired = "Microsoft WebView2 需要更新。点击确定后下载并更新，取消则退出。"
	messages.MissingRequirements = "需要准备窗口运行环境"
	messages.Webview2NotInstalled = "尚未安装 Microsoft WebView2，无法打开 RallyCut。"
	messages.Error = "运行环境错误"
	messages.FailedToInstall = "Microsoft WebView2 安装未完成，请检查网络后重试。"
	messages.DownloadPage = "需要安装 Microsoft WebView2，点击确定打开微软下载页。最低版本："
	messages.PressOKToInstall = "点击确定开始安装。"
	messages.ContactAdmin = "运行 RallyCut 需要 Microsoft WebView2，请联系系统管理员协助安装。"
	messages.InvalidFixedWebview2 = "配置的 WebView2 目录不可用，请检查路径与版本。"
	messages.WebView2ProcessCrash = "窗口运行环境意外退出，请重新启动 RallyCut。"
	if err := wails.Run(&options.App{
		Title: "RallyCut · 本地乒乓球剪辑", Width: 1440, Height: 940,
		// 960x600 keeps the desktop usable on 1366x768 laptops (especially at
		// 125% scaling, where the work area is only ~1093x574 DIP); the layout
		// has compact rules down to 660px height.
		MinWidth: 960, MinHeight: 600, BackgroundColour: options.NewRGB(17, 20, 23),
		// Two windows used to share one data directory, so both could write the
		// same project JSON and analysis cache. The second launch now just
		// focuses the running window.
		SingleInstanceLock: &options.SingleInstanceLock{
			UniqueId: "rallycut-desktop-f4b2c1",
			OnSecondInstanceLaunch: func(options.SecondInstanceData) {
				app.FocusWindow()
			},
		},
		AssetServer: &assetserver.Options{Assets: assets, Handler: backend.MediaHandler(app), Middleware: backend.MediaMiddleware(app)},
		OnStartup:   app.Startup, OnShutdown: app.Shutdown, Bind: []interface{}{app},
		Menu:    backend.ApplicationMenu(app),
		Windows: &windows.Options{Messages: messages, Theme: windows.Dark},
	}); err != nil {
		log.Fatal(err)
	}
}
