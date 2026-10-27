package media

import (
	"context"
	"path/filepath"
	"rallycut/backend/childproc"
	"runtime"
	"strings"
)

// PickVideos asks the OS for one or more video files. Wails 2.16 only exposes a
// single-selection dialog, but the native panels already support multi-select.
func PickVideos(ctx context.Context) []string {
	var out []byte
	var err error
	switch runtime.GOOS {
	case "darwin":
		script := `set theFiles to choose file with prompt "选择比赛视频" of type {"public.movie"} with multiple selections allowed
set out to ""
repeat with f in theFiles
	set out to out & POSIX path of f & linefeed
end repeat
return out`
		out, err = childproc.CommandContext(ctx, "osascript", "-e", script).Output()
	case "windows":
		script := `Add-Type -AssemblyName System.Windows.Forms
$d=New-Object System.Windows.Forms.OpenFileDialog
$d.Multiselect=$true
$d.Filter='Video|*.mp4;*.mov;*.mkv;*.m4v;*.avi;*.webm'
if($d.ShowDialog() -eq 'OK'){$d.FileNames -join "` + "`n" + `"}`
		out, err = childproc.DialogContext(ctx, "powershell", "-NoProfile", "-STA", "-Command", script).Output()
	default:
		out, err = childproc.CommandContext(ctx, "zenity", "--file-selection", "--multiple", "--separator=\n",
			"--file-filter=视频 | *.mp4 *.mov *.mkv *.m4v *.avi *.webm").Output()
	}
	if err != nil {
		return nil
	}
	var paths []string
	for _, line := range strings.Split(string(out), "\n") {
		line = strings.TrimSpace(line)
		switch strings.ToLower(filepath.Ext(line)) {
		case ".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm":
			paths = append(paths, line)
		}
	}
	return paths
}
