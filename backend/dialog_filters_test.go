package backend

import (
	"strings"
	"testing"
)

func TestProjectDialogsUseNativeSingleExtension(t *testing.T) {
	filters := projectFileFilters()
	if len(filters) != 1 || filters[0].Pattern != "*.json" {
		t.Fatalf("unsafe macOS project filters: %+v", filters)
	}
	for _, filter := range filters {
		for _, pattern := range strings.Split(filter.Pattern, ";") {
			extension := strings.TrimPrefix(pattern, "*.")
			if strings.Contains(extension, ".") {
				t.Fatalf("compound suffix would crash UTType: %s", pattern)
			}
		}
	}
}
