package setup

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

// ImportWeights installs a user-selected local copy of the pinned model
// weights, for when the official download source is unreachable. The file
// name is never trusted: only the pinned size and SHA-256 decide. The source
// file is only read, never moved or modified.
func (p *Provisioner) ImportWeights(src string) error {
	p.mu.Lock()
	if p.running {
		p.mu.Unlock()
		return errors.New("正在准备或检测环境，请等待完成后再导入模型")
	}
	p.running = true
	p.mu.Unlock()
	defer func() {
		p.mu.Lock()
		p.running = false
		p.mu.Unlock()
	}()
	spec, err := defaultWeights()
	if err != nil {
		return err
	}
	return importWeightsFile(src, p.weightsPath(), spec)
}

func importWeightsFile(src, dest string, spec weightsSpec) error {
	if spec.Bytes <= 0 || len(spec.SHA256) != 64 {
		return errors.New("无效的模型清单")
	}
	info, err := os.Stat(src)
	if err != nil {
		return fmt.Errorf("无法读取所选文件：%w", err)
	}
	if !info.Mode().IsRegular() {
		return errors.New("所选路径不是普通文件")
	}
	if info.Size() != spec.Bytes {
		return fmt.Errorf("所选文件不是 BlurBall 官方权重：大小 %d 字节，应为 %d 字节", info.Size(), spec.Bytes)
	}
	if existing, err := os.Stat(dest); err == nil && os.SameFile(info, existing) {
		if digest, hashErr := fileSHA256(dest); hashErr == nil && strings.EqualFold(digest, spec.SHA256) {
			return nil
		}
	}
	in, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("无法读取所选文件：%w", err)
	}
	defer in.Close()
	if err := os.MkdirAll(filepath.Dir(dest), 0700); err != nil {
		return err
	}
	out, err := os.CreateTemp(filepath.Dir(dest), ".import-*")
	if err != nil {
		return err
	}
	temp := out.Name()
	defer func() { _ = os.Remove(temp) }()
	// Hash the exact bytes written, so a file changing after the size check
	// cannot slip an unverified copy into place.
	hasher := sha256.New()
	n, copyErr := io.Copy(io.MultiWriter(out, hasher), io.LimitReader(in, spec.Bytes+1))
	if copyErr == nil {
		copyErr = out.Sync()
	}
	if closeErr := out.Close(); copyErr == nil {
		copyErr = closeErr
	}
	if copyErr != nil {
		return copyErr
	}
	if n != spec.Bytes {
		return fmt.Errorf("所选文件在读取时发生变化：%d / %d 字节", n, spec.Bytes)
	}
	if got := hex.EncodeToString(hasher.Sum(nil)); !strings.EqualFold(got, spec.SHA256) {
		return fmt.Errorf("所选文件 SHA-256 不匹配（期望 %s…，实际 %s…），未安装", spec.SHA256[:12], got[:12])
	}
	if err := os.Remove(dest); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	return os.Rename(temp, dest)
}
