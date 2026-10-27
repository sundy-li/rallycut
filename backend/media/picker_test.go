package media

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"

	wruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

func TestNativeVideoPickerPreservesUnicodeAndUNCPaths(t *testing.T) {
	// These are the exact strings returned by the native Unicode dialog; this
	// test does not pretend to drive the interactive OS dialog itself.
	want := []string{`C:\Users\种子 用户\Documents\生活\video\hezuocheng.mp4`, `\\Mac\Home\Documents\生活\video\樊振东 比赛.mp4`, `\\服务器\共享目录\比赛 #100% & 对拉.mp4`, `D:\比赛\émoji 🏓.MOV`}
	got, err := pickVideos(context.Background(), func(_ context.Context, options wruntime.OpenDialogOptions) ([]string, error) {
		if options.Title == "" || len(options.Filters) != 1 || !strings.Contains(options.Filters[0].Pattern, "*.mp4") {
			t.Fatal("invalid native dialog options")
		}
		return want, nil
	})
	if err != nil || !reflect.DeepEqual(got, want) {
		t.Fatalf("Unicode/UNC paths were rewritten: %q %v", got, err)
	}
}
func TestNativeVideoPickerCancellationAndErrorsDiffer(t *testing.T) {
	paths, err := pickVideos(context.Background(), func(context.Context, wruntime.OpenDialogOptions) ([]string, error) { return nil, nil })
	if err != nil || len(paths) != 0 {
		t.Fatal("cancel created an error")
	}
	sentinel := errors.New("native dialog failed")
	_, err = pickVideos(context.Background(), func(context.Context, wruntime.OpenDialogOptions) ([]string, error) { return nil, sentinel })
	if !errors.Is(err, sentinel) {
		t.Fatal("dialog failure silently treated as cancellation")
	}
}
func TestNativeVideoPickerRejectsInvalidProtocolPaths(t *testing.T) {
	for _, path := range []string{"", string([]byte{0xff}), "broken\x00path.mp4"} {
		if _, err := pickVideos(context.Background(), func(context.Context, wruntime.OpenDialogOptions) ([]string, error) { return []string{path}, nil }); err == nil {
			t.Fatalf("accepted invalid native result: %q", path)
		}
	}
}
