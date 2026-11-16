// rallycut-cli is the skill's planning / export tool. It shares the desktop
// app's timeline, overlap policy and FFmpeg export code (backend/agent,
// backend/timeline, backend/export), so an agent's cut matches what the
// desktop "export" button would render for the same selection.
//
//	rallycut-cli brief  --input <project|brief|segments.json>
//	rallycut-cli plan   --input <...> [selection flags]
//	rallycut-cli export --input <...> --output new.mp4 [selection flags]
//
// stdout carries one JSON document; progress and errors go to stderr as JSONL.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"

	"rallycut/backend/agent"
	"rallycut/backend/buildinfo"
	"rallycut/backend/export"
	"rallycut/backend/project"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func emit(w io.Writer, v any) {
	data, _ := json.Marshal(v)
	fmt.Fprintln(w, string(data))
}

func fail(stderr io.Writer, err error) int {
	emit(stderr, map[string]string{"status": "failed", "error": err.Error()})
	return 1
}

type optionalFloat struct{ value *float64 }

func (o *optionalFloat) String() string {
	if o.value == nil {
		return ""
	}
	return fmt.Sprint(*o.value)
}
func (o *optionalFloat) Set(s string) error {
	var v float64
	if _, err := fmt.Sscan(s, &v); err != nil {
		return err
	}
	o.value = &v
	return nil
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 || args[0] == "-h" || args[0] == "--help" {
		fmt.Fprintln(stderr, "usage: rallycut-cli brief|plan|export|version --input <project|brief|segments.json> [options]")
		return 2
	}
	command := args[0]
	if command == "version" {
		emit(stdout, buildinfo.Get())
		return 0
	}
	if command != "brief" && command != "plan" && command != "export" {
		return fail(stderr, fmt.Errorf("unknown command %q", command))
	}
	fs := flag.NewFlagSet(command, flag.ContinueOnError)
	fs.SetOutput(stderr)
	input := fs.String("input", "", "desktop project (*-rallycut.json), project brief or skill segments JSON")
	output := fs.String("output", "", "export: .mp4 path; an existing file is refused unless --overwrite")
	overwrite := fs.Bool("overwrite", false, "export: replace an existing output file after the new one is complete (never a source video)")
	markdown := fs.Bool("markdown", false, "brief: print the clipboard Markdown instead of JSON")
	rallies := fs.String("rallies", "", "comma-separated rally keys (<source id>/<rally id>) or ids to export; others are dropped")
	maxRallies := fs.Int("max-rallies", 0, "keep at most N rallies: favorites, then higher score, then longer")
	favorites := fs.Bool("favorites-only", false, "only rallies marked favorite")
	minDuration := fs.Float64("min-duration", 0, "drop rallies shorter than this many seconds")
	var preRoll, postRoll optionalFloat
	fs.Var(&preRoll, "pre-roll", "seconds kept before each rally (0-60; default from input)")
	fs.Var(&postRoll, "post-roll", "seconds kept after each rally (0-60; default from input)")
	codec := fs.String("codec", "", "h264 or hevc (default from input)")
	encoder := fs.String("encoder", "", "auto (VideoToolbox on macOS) or software")
	bitRate := fs.Int64("bit-rate", -1, "bits per second; 0 follows the source")
	overlap := fs.String("overlap", "", "human/machine overlap: merge, sequential, human, machine")
	trajectory := fs.Bool("trajectory", false, "burn in the ball trajectory (needs tracks: desktop project input only)")
	labels := fs.Bool("rally-labels", false, "burn in rally numbers")
	if err := fs.Parse(args[1:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if *input == "" {
		return fail(stderr, errors.New("--input is required"))
	}
	p, kind, err := agent.Load(*input)
	if err != nil {
		return fail(stderr, err)
	}
	if command == "brief" {
		path := ""
		if kind == "rallycut.project" {
			path, _ = filepath.Abs(*input)
		}
		b := agent.NewBrief(p, path)
		if *markdown {
			text, err := agent.Markdown(b)
			if err != nil {
				return fail(stderr, err)
			}
			fmt.Fprint(stdout, text)
			return 0
		}
		data, err := agent.CompactJSON(b)
		if err != nil {
			return fail(stderr, err)
		}
		fmt.Fprintln(stdout, string(data))
		return 0
	}
	settings := p.ExportSettings.Normalized()
	if *codec != "" {
		settings.Codec = *codec
	}
	if *encoder != "" {
		settings.Encoder = *encoder
	}
	if *bitRate >= 0 {
		settings.BitRate = *bitRate
	}
	if *overlap != "" {
		settings.Overlap = *overlap
	}
	if *trajectory && !hasTracks(p) {
		return fail(stderr, errors.New("--trajectory needs ball tracks; use the desktop project file as --input"))
	}
	if settings.ShowTrajectory && !hasTracks(p) {
		// Inherited from the project settings, but a brief / segments file
		// carries no tracks: export without the overlay instead of failing.
		settings.ShowTrajectory = false
		emit(stderr, map[string]string{"type": "warning", "message": "input has no ball tracks; trajectory overlay disabled (use the project file to keep it)"})
	}
	settings.ShowTrajectory = settings.ShowTrajectory || *trajectory
	settings.ShowRallyLabels = settings.ShowRallyLabels || *labels
	if err := project.ValidateExport(settings); err != nil {
		return fail(stderr, err)
	}
	p.ExportSettings = settings
	var keys []string
	if *rallies != "" {
		keys = strings.Split(*rallies, ",")
	}
	selected, err := agent.Apply(p, agent.Selection{Keys: keys, FavoritesOnly: *favorites, MinDuration: *minDuration,
		MaxRallies: *maxRallies, PreRoll: preRoll.value, PostRoll: postRoll.value})
	if err != nil {
		return fail(stderr, err)
	}
	plan, err := agent.NewPlan(p, selected)
	if err != nil {
		return fail(stderr, err)
	}
	if command == "plan" {
		enc := json.NewEncoder(stdout)
		enc.SetIndent("", " ")
		if err := enc.Encode(plan); err != nil {
			return fail(stderr, err)
		}
		return 0
	}
	if *output == "" {
		return fail(stderr, errors.New("--output is required for export"))
	}
	target, err := filepath.Abs(*output)
	if err != nil {
		return fail(stderr, err)
	}
	for _, s := range p.Sources {
		if same(target, s.Video.Path) {
			return fail(stderr, errors.New("refusing to write over a source video"))
		}
	}
	if *overwrite {
		if info, err := os.Lstat(target); err == nil && !info.Mode().IsRegular() {
			return fail(stderr, fmt.Errorf("refusing to overwrite a non-regular file: %s", target))
		}
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	err = export.RunWith(ctx, p, target, export.Options{Overwrite: *overwrite}, func(fraction float64, message string) {
		emit(stderr, map[string]any{"type": "progress", "progress": fraction, "message": message})
	})
	if err != nil {
		if ctx.Err() != nil {
			emit(stderr, map[string]string{"status": "cancelled"})
			return 130
		}
		return fail(stderr, err)
	}
	emit(stdout, map[string]any{"status": "completed", "output": target, "clips": len(plan.Spans),
		"rallies": plan.SelectedRallies, "duration": plan.TotalDuration})
	return 0
}

func hasTracks(p *project.Project) bool {
	for _, s := range p.Sources {
		if len(s.Tracks) > 0 {
			return true
		}
	}
	return false
}

func same(a, b string) bool {
	x, errA := os.Stat(a)
	y, errB := os.Stat(b)
	if errA == nil && errB == nil {
		return os.SameFile(x, y)
	}
	return filepath.Clean(a) == filepath.Clean(b)
}
