// export-demo renders a short showcase through the desktop app's real exporter.
// It reads but never modifies the source project. Private project paths and
// timestamps are command-line arguments, not built-in demo fixtures.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"

	videoexport "rallycut/backend/export"
	"rallycut/backend/project"
	"rallycut/backend/timeline"
)

func main() {
	input := flag.String("project", "", "existing project JSON (read only)")
	output := flag.String("output", "", "new output MP4 path; never overwritten")
	numbers := flag.String("rallies", "", "1-based rally numbers from the active source, e.g. 2,9,11")
	limit := flag.Float64("limit", 30, "maximum planned duration, including padding, in seconds")
	flag.Parse()
	if err := render(*input, *output, *numbers, *limit); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func render(input, output, numbers string, limit float64) error {
	if input == "" || output == "" || numbers == "" || !project.Finite(limit) || limit <= 0 {
		return fmt.Errorf("provide --project, --output, --rallies and a positive --limit")
	}
	data, err := os.ReadFile(input)
	if err != nil {
		return err
	}
	var p project.Project
	if err := json.Unmarshal(data, &p); err != nil {
		return err
	}
	if p.Video.Path == "" || len(p.Rallies) == 0 {
		return fmt.Errorf("project has no active video or rallies")
	}
	selected := map[int]bool{}
	for _, value := range strings.Split(numbers, ",") {
		n, err := strconv.Atoi(strings.TrimSpace(value))
		if err != nil || n < 1 || n > len(p.Rallies) || selected[n] {
			return fmt.Errorf("invalid or repeated rally number %q", value)
		}
		if p.Rallies[n-1].Invalid {
			return fmt.Errorf("rally %d is marked invalid", n)
		}
		selected[n] = true
	}
	for i := range p.Rallies {
		p.Rallies[i].Selected = selected[i+1]
	}
	// Export only this source, never other selected sources in the project.
	p.Sources = nil
	p.ActiveSourceID = ""
	p.Rules = project.Rules{PreRoll: .2, PostRoll: .3}
	p.ExportSettings = project.ExportSettings{Codec: "h264", Encoder: "software", BitRate: 5000000, Overlap: project.OverlapSequential, ShowTrajectory: true, ShowRallyLabels: true}
	spans, err := timeline.ExportSegments(p.Rallies, p.Rules, p.ExportSettings, p.Video.Duration)
	if err != nil {
		return err
	}
	var duration float64
	for _, span := range spans {
		duration += span.End - span.Start
	}
	if duration <= 0 || duration > limit {
		return fmt.Errorf("planned duration %.3fs exceeds limit %.3fs (or no exportable rallies)", duration, limit)
	}
	fmt.Fprintf(os.Stderr, "Rendering %d rallies, %.3fs, with real saved tracks and rally labels\n", len(selected), duration)
	return videoexport.Run(context.Background(), &p, output, func(fraction float64, message string) {
		fmt.Fprintf(os.Stderr, "%.0f%% %s\n", fraction*100, message)
	})
}
