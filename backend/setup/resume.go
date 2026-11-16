package setup

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// Download tuning. Variables, not constants, so tests can shrink them.
var (
	// Rounds over every source before giving up; each round tries each
	// still-usable source once.
	downloadRounds = 4
	// Backoff between full rounds: 1s, 2s, 4s … capped.
	downloadBackoffBase = time.Second
	downloadBackoffMax  = 8 * time.Second
	// A connection that delivers no body bytes for this long is dropped and
	// the next source is tried; the .part progress is kept.
	downloadStallTimeout = 30 * time.Second
)

// newDownloadClient returns a client with bounded connect / TLS / header
// waits so a black-holed source fails in seconds instead of hanging. Proxy
// settings from the environment are honored like http.DefaultTransport.
func newDownloadClient() *http.Client {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.DialContext = (&net.Dialer{Timeout: 15 * time.Second, KeepAlive: 30 * time.Second}).DialContext
	transport.TLSHandshakeTimeout = 15 * time.Second
	transport.ResponseHeaderTimeout = 30 * time.Second
	return &http.Client{Transport: transport, Timeout: 30 * time.Minute}
}

// downloadResumable is the single-source form of downloadFromSources.
func downloadResumable(ctx context.Context, client *http.Client, url, dest string, size int64, digest string, progress func(int64, int64)) error {
	return downloadFromSources(ctx, client, []string{url}, dest, size, digest, progress)
}

// sourceFailure marks errors after which the same source is not retried
// (wrong file, unsafe resume semantics, permanent HTTP status).
type sourceFailure struct{ err error }

func (e sourceFailure) Error() string { return e.err.Error() }
func (e sourceFailure) Unwrap() error { return e.err }

// downloadFromSources fetches one pinned file from interchangeable sources.
// Every source must serve byte-identical content: the .part file survives
// switching sources and interruptions, and nothing is published until the
// fixed size and SHA-256 both match. A source that serves wrong bytes or
// unsafe ranges is dropped for the rest of the call.
func downloadFromSources(ctx context.Context, client *http.Client, sources []string, dest string, size int64, digest string, progress func(int64, int64)) error {
	if size <= 0 || len(digest) != 64 || len(sources) == 0 {
		return fmt.Errorf("无效的下载清单")
	}
	if got, _ := fileSHA256(dest); strings.EqualFold(got, digest) {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(dest), 0700); err != nil {
		return err
	}
	part := dest + ".part"
	dead := make([]bool, len(sources))
	lastErr := make([]error, len(sources))
	usable := func() bool {
		for _, d := range dead {
			if !d {
				return true
			}
		}
		return false
	}
	for round := 0; round < downloadRounds && usable(); round++ {
		if round > 0 {
			delay := downloadBackoffBase << (round - 1)
			if delay > downloadBackoffMax {
				delay = downloadBackoffMax
			}
			timer := time.NewTimer(delay)
			select {
			case <-ctx.Done():
				timer.Stop()
				return ctx.Err()
			case <-timer.C:
			}
		}
		for i, source := range sources {
			if dead[i] {
				continue
			}
			if err := ctx.Err(); err != nil {
				return err
			}
			done, err := fetchPart(ctx, client, source, part, size, progress)
			if err == nil && done != partIncomplete {
				err = finishDownload(part, dest, size, digest)
				if err == nil {
					return nil
				}
				// finishDownload removed the bad .part. Only a source that
				// produced the whole file by itself is proven wrong; a mix
				// with older bytes just restarts from zero.
				if done == fullFromSource {
					err = sourceFailure{err}
				}
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
			lastErr[i] = err
			var permanent sourceFailure
			if errors.As(err, &permanent) {
				dead[i] = true
			}
		}
	}
	if !usable() {
		return fmt.Errorf("所有下载源都不可用：%s", describeSourceErrors(sources, lastErr))
	}
	return fmt.Errorf("下载中断，已保留进度，可重试：%s", describeSourceErrors(sources, lastErr))
}

type partResult int

const (
	partIncomplete partResult = iota
	partResumed               // complete, but some bytes predate this request
	fullFromSource            // complete, every byte from this request
)

// fetchPart appends to (or restarts) part from one source. It reports whether
// part now holds exactly size bytes and how they were obtained.
func fetchPart(ctx context.Context, client *http.Client, source, part string, size int64, progress func(int64, int64)) (partResult, error) {
	offset := int64(0)
	if info, err := os.Stat(part); err == nil {
		offset = info.Size()
	}
	if offset > size {
		_ = os.Remove(part)
		offset = 0
	}
	if offset == size {
		return partResumed, nil
	}
	reqCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	req, err := http.NewRequestWithContext(reqCtx, http.MethodGet, source, nil)
	if err != nil {
		return partIncomplete, sourceFailure{err}
	}
	req.Header.Set("User-Agent", "RallyCut/1.0")
	req.Header.Set("Accept-Encoding", "identity")
	if offset > 0 {
		req.Header.Set("Range", fmt.Sprintf("bytes=%d-", offset))
	}
	resp, err := client.Do(req)
	if err != nil {
		// The source host is already named in the summary; drop the URL.
		var ue *url.Error
		if errors.As(err, &ue) {
			err = ue.Err
		}
		return partIncomplete, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusRequestedRangeNotSatisfiable {
		_ = os.Remove(part)
		return partIncomplete, fmt.Errorf("下载源拒绝续传，将从头重试")
	}
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		err := fmt.Errorf("HTTP %d", resp.StatusCode)
		if resp.StatusCode == 408 || resp.StatusCode == 429 || resp.StatusCode >= 500 {
			return partIncomplete, err
		}
		return partIncomplete, sourceFailure{err}
	}
	if resp.StatusCode == http.StatusPartialContent {
		var start, end, total int64
		_, err = fmt.Sscanf(resp.Header.Get("Content-Range"), "bytes %d-%d/%d", &start, &end, &total)
		if err != nil || start != offset || end != size-1 || total != size {
			return partIncomplete, sourceFailure{fmt.Errorf("下载源返回无效的 Content-Range")}
		}
	} else {
		offset = 0 // A server ignoring Range must never be appended.
	}
	if resp.Uncompressed || (resp.Header.Get("Content-Encoding") != "" && resp.Header.Get("Content-Encoding") != "identity") {
		return partIncomplete, sourceFailure{fmt.Errorf("下载源改变了压缩编码，无法安全续传")}
	}
	// Accelerators and proxies may answer 200 with an HTML error page. Reject
	// it before opening part, so it can neither truncate nor pollute progress
	// kept from other sources.
	if resp.ContentLength >= 0 && resp.ContentLength != size-offset {
		return partIncomplete, sourceFailure{fmt.Errorf("下载源返回的大小不符（%d 字节，应为 %d）", resp.ContentLength, size-offset)}
	}
	if strings.HasPrefix(strings.ToLower(resp.Header.Get("Content-Type")), "text/html") {
		return partIncomplete, sourceFailure{fmt.Errorf("下载源返回了网页而不是模型文件")}
	}
	flags := os.O_CREATE | os.O_WRONLY
	if offset == 0 {
		flags |= os.O_TRUNC
	} else {
		flags |= os.O_APPEND
	}
	f, err := os.OpenFile(part, flags, 0600)
	if err != nil {
		return partIncomplete, err
	}
	stall := newStallGuard(downloadStallTimeout, cancel)
	defer stall.stop()
	reader := &progressReader{reader: stall.wrap(io.LimitReader(resp.Body, size-offset+1)), total: size, written: offset, onProgress: progress}
	n, copyErr := io.Copy(f, reader)
	if closeErr := f.Close(); copyErr == nil {
		copyErr = closeErr
	}
	if offset+n > size {
		_ = os.Remove(part)
		return partIncomplete, sourceFailure{fmt.Errorf("下载超出固定大小")}
	}
	if offset+n == size {
		if offset == 0 {
			return fullFromSource, nil
		}
		return partResumed, nil
	}
	if stall.fired() {
		return partIncomplete, fmt.Errorf("%s 内没有收到数据", downloadStallTimeout)
	}
	if copyErr == nil {
		// A clean end of body before the pinned size means this source serves
		// a different (shorter) file; its bytes must not seed a resume.
		if offset == 0 {
			_ = os.Remove(part)
		}
		return partIncomplete, sourceFailure{fmt.Errorf("下载源提供的文件不完整（%d / %d 字节）", offset+n, size)}
	}
	return partIncomplete, copyErr
}

// stallGuard cancels a request whose body stops delivering bytes.
type stallGuard struct {
	timer   *time.Timer
	timeout time.Duration
	mu      sync.Mutex
	hit     bool
}

func newStallGuard(timeout time.Duration, cancel context.CancelFunc) *stallGuard {
	g := &stallGuard{timeout: timeout}
	g.timer = time.AfterFunc(timeout, func() {
		g.mu.Lock()
		g.hit = true
		g.mu.Unlock()
		cancel()
	})
	return g
}

func (g *stallGuard) wrap(r io.Reader) io.Reader { return stallReader{r, g} }
func (g *stallGuard) stop()                      { g.timer.Stop() }
func (g *stallGuard) fired() bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.hit
}

type stallReader struct {
	r io.Reader
	g *stallGuard
}

func (s stallReader) Read(p []byte) (int, error) {
	n, err := s.r.Read(p)
	if n > 0 {
		s.g.timer.Reset(s.g.timeout)
	}
	return n, err
}

// describeSourceErrors names each source by host only (no query / userinfo).
func describeSourceErrors(sources []string, errs []error) string {
	parts := make([]string, 0, len(sources))
	for i, source := range sources {
		host := source
		if u, err := url.Parse(source); err == nil && u.Host != "" {
			host = u.Host
		}
		reason := "未尝试"
		if errs[i] != nil {
			reason = errs[i].Error()
		}
		parts = append(parts, fmt.Sprintf("%s：%s", host, reason))
	}
	return strings.Join(parts, "；")
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
