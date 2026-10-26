package main

import (
	"embed"
	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
	"log"
	"rallycut/backend"
)

//go:embed all:frontend/dist
var assets embed.FS

func main() {
	app := backend.NewApp()
	if err := wails.Run(&options.App{
		Title: "RallyCut · 本地乒乓球剪辑", Width: 1440, Height: 940,
		MinWidth: 1060, MinHeight: 720, BackgroundColour: options.NewRGB(17, 20, 23),
		AssetServer: &assetserver.Options{Assets: assets, Handler: backend.MediaHandler(app), Middleware: backend.MediaMiddleware(app)},
		OnStartup:   app.Startup, OnShutdown: app.Shutdown, Bind: []interface{}{app},
		Menu: backend.ApplicationMenu(app),
	}); err != nil {
		log.Fatal(err)
	}
}
