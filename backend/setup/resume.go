package setup

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// downloadResumable retains only an untrusted .part file on interruption; no
// executable is published until the final size and pinned hash both match.
func downloadResumable(ctx context.Context, client *http.Client, url, dest string, size int64, digest string, progress func(int64, int64)) error {
	if size <= 0 || len(digest) != 64 {
		return fmt.Errorf("无效的下载清单")
	}
	if got, _ := fileSHA256(dest); got == digest {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(dest), 0700); err != nil {
		return err
	}
	part := dest + ".part"
	var last error
	for attempt := 0; attempt < 4; attempt++ {
		if attempt > 0 {
			timer := time.NewTimer(time.Duration(1<<(attempt-1)) * time.Second)
			select {
			case <-ctx.Done():
				timer.Stop()
				return ctx.Err()
			case <-timer.C:
			}
		}
		if err := ctx.Err(); err != nil {
			return err
		}
		offset := int64(0)
		if info, err := os.Stat(part); err == nil {
			offset = info.Size()
		}
		if offset > size {
			_ = os.Remove(part)
			offset = 0
		}
		if offset == size {
			return finishDownload(part, dest, size, digest)
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			return err
		}
		req.Header.Set("Accept-Encoding", "identity")
		if offset > 0 {
			req.Header.Set("Range", fmt.Sprintf("bytes=%d-", offset))
		}
		resp, err := client.Do(req)
		if err != nil {
			last = err
			continue
		}
		if resp.StatusCode == http.StatusRequestedRangeNotSatisfiable {
			resp.Body.Close()
			_ = os.Remove(part)
			last = fmt.Errorf("下载源拒绝续传，正在从头重试")
			continue
		}
		if resp.StatusCode != 200 && resp.StatusCode != 206 {
			resp.Body.Close()
			last = fmt.Errorf("下载 HTTP %d", resp.StatusCode)
			if resp.StatusCode == 408 || resp.StatusCode == 429 || resp.StatusCode >= 500 {
				continue
			}
			return last
		}
		if resp.StatusCode == 206 {
			var start, end, total int64
			_, err = fmt.Sscanf(resp.Header.Get("Content-Range"), "bytes %d-%d/%d", &start, &end, &total)
			if err != nil || start != offset || end != size-1 || total != size {
				resp.Body.Close()
				return fmt.Errorf("下载源返回无效的 Content-Range")
			}
		} else {
			offset = 0
		} // A server ignoring Range must never be appended.
		if resp.Uncompressed || (resp.Header.Get("Content-Encoding") != "" && resp.Header.Get("Content-Encoding") != "identity") {
			resp.Body.Close()
			return fmt.Errorf("下载源改变了压缩编码，无法安全续传")
		}
		flags := os.O_CREATE | os.O_WRONLY
		if offset == 0 {
			flags |= os.O_TRUNC
		} else {
			flags |= os.O_APPEND
		}
		f, err := os.OpenFile(part, flags, 0600)
		if err != nil {
			resp.Body.Close()
			return err
		}
		reader := &progressReader{reader: io.LimitReader(resp.Body, size-offset+1), total: size, written: offset, onProgress: progress}
		n, copyErr := io.Copy(f, reader)
		closeErr := f.Close()
		resp.Body.Close()
		if copyErr == nil {
			copyErr = closeErr
		}
		if offset+n > size {
			_ = os.Remove(part)
			return fmt.Errorf("下载超出固定大小")
		}
		if copyErr == nil && offset+n == size {
			return finishDownload(part, dest, size, digest)
		}
		last = copyErr
		if last == nil {
			last = io.ErrUnexpectedEOF
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
	}
	return fmt.Errorf("下载中断，已保留进度，可重试：%w", last)
}
func finishDownload(part, dest string, size int64, digest string) error {
	got, err := fileSHA256(part)
	if err != nil {
		return err
	}
	info, err := os.Stat(part)
	if err != nil {
		return err
	}
	if info.Size() != size || !strings.EqualFold(got, digest) {
		_ = os.Remove(part)
		return fmt.Errorf("下载 SHA-256 校验失败，未安装任何文件")
	}
	if err := os.Remove(dest); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	return os.Rename(part, dest)
}
