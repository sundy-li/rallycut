//go:build windows

package childproc

import (
	"context"
	"fmt"
	"os"
	"syscall"
	"testing"
)

func TestWindowsConsoleHelper(t *testing.T) {
	if os.Getenv("RALLYCUT_COMMAND_TEST") != "console" {
		return
	}
	window, _, _ := syscall.NewLazyDLL("kernel32.dll").NewProc("GetConsoleWindow").Call()
	fmt.Printf("console=%d", window)
	os.Exit(0)
}
func TestRealChildHasNoConsole(t *testing.T) {
	cmd := Command(os.Args[0], "-test.run=^TestWindowsConsoleHelper$")
	cmd.Env = append(os.Environ(), "RALLYCUT_COMMAND_TEST=console")
	out, err := cmd.Output()
	if err != nil || string(out) != "console=0" {
		t.Fatalf("child attached or created a console: %q %v", out, err)
	}
	dialog := DialogContext(context.Background(), "powershell.exe", "-NoProfile")
	if dialog.SysProcAttr == nil || dialog.SysProcAttr.HideWindow || dialog.SysProcAttr.CreationFlags&0x08000000 == 0 {
		t.Fatal("native dialogs must stay visible without a console")
	}
}
func TestInternalCommandsCannotCreateConsoleWindows(t *testing.T) {
	for _, cmd := range []*struct{ context bool }{{false}, {true}} {
		c := Command("python.exe", "-V")
		if cmd.context {
			c = CommandContext(context.Background(), "ffmpeg.exe", "-version")
		}
		if c.SysProcAttr == nil || !c.SysProcAttr.HideWindow || c.SysProcAttr.CreationFlags&0x08000000 == 0 {
			t.Fatal("internal helper may create a console")
		}
	}
}
