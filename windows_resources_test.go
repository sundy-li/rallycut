//go:build windows

package main

import (
	"bytes"
	"os"
	"testing"

	"golang.org/x/sys/windows"
)

func TestWindowsExecutableHasNativeResources(t *testing.T) {
	path := os.Getenv("RALLYCUT_TEST_EXE")
	if path == "" {
		t.Skip("requires standard Windows build output")
	}
	module, err := windows.LoadLibraryEx(path, 0, windows.LOAD_LIBRARY_AS_DATAFILE|windows.LOAD_LIBRARY_AS_IMAGE_RESOURCE)
	if err != nil {
		t.Fatal(err)
	}
	defer windows.FreeLibrary(module)
	load := func(kind windows.ResourceID, ids ...windows.ResourceID) []byte {
		for _, id := range ids {
			if resource, err := windows.FindResource(module, id, kind); err == nil {
				if data, err := windows.LoadResourceData(module, resource); err == nil {
					return data
				}
			}
		}
		return nil
	}
	manifest := load(windows.RT_MANIFEST, 1)
	hasManifest := bytes.Contains(manifest, []byte("dpiAwareness")) && bytes.Contains(manifest, []byte("permonitorv2"))
	// Wails' standard build names the icon group RT_ICON (3).
	hasIcon := len(load(windows.RT_GROUP_ICON, 3, 1)) > 0
	hasVersion := len(load(windows.RT_VERSION, 1)) > 0
	if !hasManifest || !hasIcon || !hasVersion {
		t.Fatalf("incomplete Windows resources: DPI manifest=%v icon=%v version=%v", hasManifest, hasIcon, hasVersion)
	}
}
