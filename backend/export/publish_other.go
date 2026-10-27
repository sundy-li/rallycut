//go:build !windows

package export

import "os"

func publishCompleted(source, dest string) error { return os.Link(source, dest) }
