package media

import (
	"context"
	"fmt"
	"strings"
	"unicode/utf8"

	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

// Wails 2.16 supports native multi-select on all desktop platforms. On Windows
// it obtains UTF-16 SIGDN_FILESYSPATH values directly from IFileOpenDialog.
// Never round-trip a filename through PowerShell stdout, an ANSI code page,
// newline-separated shell output or URL decoding. UNC prefixes stay intact.
func PickVideos(ctx context.Context) ([]string, error) {
	return pickVideos(ctx, wruntime.OpenMultipleFilesDialog)
}

type multipleFileDialog func(context.Context, wruntime.OpenDialogOptions) ([]string, error)

func pickVideos(ctx context.Context, open multipleFileDialog) ([]string, error) {
	paths, err := open(ctx, wruntime.OpenDialogOptions{
		Title:   "选择比赛视频（可多选）",
		Filters: []wruntime.FileFilter{{DisplayName: "视频文件", Pattern: "*.mp4;*.mov;*.mkv;*.m4v;*.avi;*.webm"}},
	})
	if err != nil {
		return nil, fmt.Errorf("打开视频选择窗口失败：%w", err)
	}
	// Cancellation is not an error. Real dialog failures must not masquerade as
	// cancellation, and filenames must not be trimmed or otherwise rewritten.
	for _, path := range paths {
		if path == "" || !utf8.ValidString(path) || strings.ContainsRune(path, 0) {
			return nil, fmt.Errorf("文件选择器返回了无效路径，请重新选择视频")
		}
	}
	return paths, nil
}
