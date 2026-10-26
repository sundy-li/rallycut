// Command analyze exercises the exact production pipeline without Wails dialogs.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"rallycut/backend/analysis"
	"rallycut/backend/media"
	"rallycut/backend/project"
	"rallycut/backend/storage"
	"rallycut/vision"
	"time"
)

func run() error {
	input := flag.String("input", "", "source video (read only)")
	output := flag.String("output", "", "analysis JSON output (required)")
	projectFile := flag.String("project", "", "optional new *-rallycut.json project")
	detector := flag.String("detector", analysis.Model, "detector: blurball-pretrained-v1 (default), classical-av-v1 (explicit comparison)")
	flag.Parse()
	if *input == "" || *output == "" {
		return fmt.Errorf("usage: analyze -input match.mp4 -output /tmp/analysis.json [-project /tmp/20261024-152433-rallycut.json]")
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	ctx, cancel := context.WithTimeout(ctx, 30*time.Minute)
	defer cancel()
	v, err := media.Inspect(ctx, *input)
	if err != nil {
		return err
	}
	for _, path := range []string{*output, *projectFile} {
		if path == "" {
			continue
		}
		abs, err := filepath.Abs(path)
		if err != nil {
			return err
		}
		if abs == v.Path {
			return fmt.Errorf("refusing to overwrite source video")
		}
		if _, err := os.Lstat(abs); err == nil {
			return fmt.Errorf("output already exists: %s", abs)
		} else if !os.IsNotExist(err) {
			return err
		}
	}
	dir, err := os.MkdirTemp("", "rallycut-worker-*")
	if err != nil {
		return err
	}
	defer os.RemoveAll(dir)
	worker, err := vision.Install(dir)
	if err != nil {
		return err
	}
	result, err := analysis.RunWithModel(ctx, analysis.Python(""), worker, v, *detector, func(p float64, msg string) { fmt.Fprintf(os.Stderr, "%5.1f%% %s\n", p*100, msg) })
	if err != nil {
		return err
	}
	if err := storage.WriteJSON(*output, result); err != nil {
		return err
	}
	if *projectFile != "" {
		p := project.New(v)
		p.ApplyAnalysis(result.Rallies, result.Model)
		p.Tracks = result.Tracks
		p.Analysis = result.Summary
		if err := p.Validate(); err != nil {
			return err
		}
		if err := storage.WriteJSON(*projectFile, p); err != nil {
			return err
		}
	}
	fmt.Printf("%s: %d decoded frames, %d tracks, %d rally candidates; NOT accuracy-validated\n", result.Model, result.Summary.DecodedFrames, len(result.Tracks), len(result.Rallies))
	return nil
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
