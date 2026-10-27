//go:build windows

package export

import "golang.org/x/sys/windows"

// Jobs are rendered under the output's own directory. MoveFileW publishes the
// completed file on that same volume without replacing an existing name. Do
// not require NTFS hard-link support: Mac/SMB shared folders may not have it.
func publishCompleted(source, dest string) error {
	from, err := windows.UTF16PtrFromString(source)
	if err != nil {
		return err
	}
	to, err := windows.UTF16PtrFromString(dest)
	if err != nil {
		return err
	}
	return windows.MoveFile(from, to)
}
