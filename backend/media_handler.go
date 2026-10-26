package backend

import (
	"net/http"
	"strings"
)

// Keep HTTP types out of Wails' exported method bindings.
func MediaHandler(app *App) http.Handler { return http.HandlerFunc(app.serveHTTP) }

// Wails normally tries the external Vite server first and invokes Handler only
// for 404/405. Vite's SPA fallback returns 200 HTML for /media/source instead.
// Intercept media before that proxy in BOTH development and production modes.
func MediaMiddleware(app *App) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if strings.HasPrefix(r.URL.Path, "/media/") {
				app.serveHTTP(w, r)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
