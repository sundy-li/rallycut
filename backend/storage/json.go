package storage

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"rallycut/backend/project"
)

// WriteJSON replaces a file atomically on the same filesystem.
func WriteJSON(path string, v any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	// Do not publish a project (including annotations) that ReadJSON cannot reopen.
	if len(data) > 32<<20 {
		return fmt.Errorf("JSON 文件超过 32 MiB 上限，未覆盖已有文件")
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".rallycut-*")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if err = f.Chmod(0600); err == nil {
		_, err = f.Write(data)
	}
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(f.Name(), path)
}

func ReadJSON(path string, v any) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	if info, err := f.Stat(); err != nil {
		return err
	} else if info.Size() > 32<<20 {
		return fmt.Errorf("JSON 文件超过 32 MiB 上限")
	}
	dec := json.NewDecoder(io.LimitReader(f, 32<<20))
	if err := dec.Decode(v); err != nil {
		return err
	}
	var extra any
	if err := dec.Decode(&extra); err != io.EOF {
		return fmt.Errorf("JSON 文件尾部存在额外内容")
	}
	return nil
}

func Load(path string) (*project.Project, error) {
	var p project.Project
	if err := ReadJSON(path, &p); err != nil {
		return nil, err
	}
	p.ExportSettings = p.ExportSettings.Normalized()
	if err := p.Validate(); err != nil {
		return nil, err
	}
	if p.Job != nil && (p.Job.Status == "running" || p.Job.Status == "cancelling") {
		p.Job.Status = "interrupted"
		p.Job.Message = "上次任务中断，可重新执行；人工编辑已保留"
	}
	return &p, nil
}
