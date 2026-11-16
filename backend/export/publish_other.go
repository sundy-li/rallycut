//go:build !windows

package export

import "os"

func publishCompleted(source, dest string) error { return os.Link(source, dest) }

// replaceCompleted atomically swaps in the finished file: readers see either
// the old export or the new one, never a partial file.
func replaceCompleted(source, dest string) error { return os.Rename(source, dest) }
