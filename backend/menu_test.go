package backend

import (
	"testing"

	"github.com/wailsapp/wails/v2/pkg/menu"
	"github.com/wailsapp/wails/v2/pkg/menu/keys"
)

func findItem(m *menu.Menu, label string) *menu.MenuItem {
	for _, item := range m.Items {
		if item.Label == label {
			return item
		}
		if item.SubMenu != nil {
			if found := findItem(item.SubMenu, label); found != nil {
				return found
			}
		}
	}
	return nil
}

func TestApplicationMenuShortcuts(t *testing.T) {
	m := buildApplicationMenu(NewApp())
	if first := m.Items[0]; first.SubMenu == nil || first.SubMenu.Items[0].Label != "设置…" {
		t.Fatalf("app menu must open with 设置…: %+v", first)
	}
	for label, key := range map[string]string{"设置…": ",", "快捷键": "/", "退出 RallyCut": "q"} {
		item := findItem(m, label)
		if item == nil || item.Accelerator == nil || item.Accelerator.Key != key ||
			len(item.Accelerator.Modifiers) != 1 || item.Accelerator.Modifiers[0] != keys.CmdOrCtrlKey {
			t.Fatalf("%s should be ⌘%s, got %+v", label, key, item)
		}
		if item.Click == nil {
			t.Fatalf("%s has no action", label)
		}
	}
	// Callbacks before startup (nil ctx) must not panic.
	findItem(m, "设置…").Click(nil)
	findItem(m, "退出 RallyCut").Click(nil)
	// No Edit menu: ⌘Z / ⇧⌘Z stay with the frontend's project undo.
	for _, label := range []string{"Undo", "撤销", "Edit", "编辑"} {
		if findItem(m, label) != nil {
			t.Fatalf("menu must not claim %s", label)
		}
	}
}
