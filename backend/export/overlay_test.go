package export

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"rallycut/backend/media"
	"rallycut/backend/project"
	"rallycut/backend/timeline"
)

func pixel(buf []byte, w, x, y int) [4]byte {
	i := (y*w + x) * 4
	return [4]byte{buf[i], buf[i+1], buf[i+2], buf[i+3]}
}

func TestOverlayDrawsTrackInPlayerWindowAndClears(t *testing.T) {
	spec := overlaySpec{Width: 400, Height: 200, FPS: 10, Start: 1, Length: 2, Tracks: []project.BallTrack{{
		ID: "a",
		Points: []project.TrackPoint{
			{T: 1.0, X: 0.25, Y: 0.5}, {T: 1.1, X: 0.5, Y: 0.5}, {T: 1.2, X: 0.75, Y: 0.5},
		},
	}, {
		ID: "far", OffPlay: true,
		Points: []project.TrackPoint{{T: 1.1, X: 0.5, Y: 0.1}},
	}}}
	r := newOverlayRenderer(spec)
	frame := r.frame(1) // t=1.1 → window [0.8,1.2] holds all three points
	mid := pixel(frame, 400, 150, 100)
	if mid[3] < 150 || mid[0] != 0xff || mid[1] != 0xbd {
		t.Fatalf("polyline pixel = %v, want opaque #ffbd68", mid)
	}
	// Hollow ring (r = 7/1000·width = 2.8px) around the newest point (300,100).
	if ring := pixel(frame, 400, 303, 100); ring[3] == 0 {
		t.Fatal("ring around the newest point is missing")
	}
	if off := pixel(frame, 400, 200, 20); off[3] != 0 {
		t.Fatalf("off-play track was drawn: %v", off)
	}
	// t=1.6: every point is older than t-0.3, so the frame must be fully clear.
	frame = r.frame(6)
	for i := 3; i < len(frame); i += 4 {
		if frame[i] != 0 {
			t.Fatalf("stale pixel at byte %d after the track left the window", i)
		}
	}
}

func TestLabelFollowsRallyBoundariesInsideSpan(t *testing.T) {
	labels := []timeline.Label{{Number: 3, From: 10}, {Number: 4, From: 14}}
	if got := labelAt(labels, 10); got != 3 {
		t.Fatalf("start = %d", got)
	}
	if got := labelAt(labels, 13.9); got != 3 {
		t.Fatalf("before switch = %d", got)
	}
	if got := labelAt(labels, 14); got != 4 {
		t.Fatalf("after switch = %d", got)
	}
}

func TestLabelBadgeRendersChineseText(t *testing.T) {
	face, err := labelFace(360)
	if err != nil {
		t.Skip(err)
	}
	spec := overlaySpec{Width: 640, Height: 360, FPS: 10, Start: 0, Length: 1, Labels: []timeline.Label{{Number: 3, From: 0}}, Face: face}
	frame := newOverlayRenderer(spec).frame(0)
	bright, plate := 0, 0
	for y := 0; y < 60; y++ {
		for x := 0; x < 200; x++ {
			p := pixel(frame, 640, x, y)
			if p[3] > 0 {
				plate++
			}
			if p[3] > 200 && p[0] > 200 {
				bright++
			}
		}
	}
	if plate == 0 || bright < 40 {
		t.Fatalf("badge missing: plate=%d text=%d", plate, bright)
	}
	if p := pixel(frame, 640, 600, 300); p[3] != 0 {
		t.Fatal("badge leaked outside the top-left corner")
	}
}

// End to end: a real FFmpeg encode with both overlays burned in.
func TestRunBurnsOverlayIntoExport(t *testing.T) {
	if _, err := exec.LookPath(media.Binary("ffmpeg")); err != nil {
		t.Skip("ffmpeg not available")
	}
	if _, err := labelFace(360); err != nil {
		t.Skip(err)
	}
	ctx := context.Background()
	dir := t.TempDir()
	src := filepath.Join(dir, "source.mp4")
	// Solid dark gray source so any bright pixel must come from the overlay.
	if out, err := exec.Command(media.Binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x202020:s=640x360:r=30:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", src).CombinedOutput(); err != nil {
		t.Fatalf("make source: %v %s", err, out)
	}
	v, err := media.Probe(ctx, src)
	if err != nil {
		t.Fatal(err)
	}
	v.Fingerprint, err = media.Fingerprint(ctx, src)
	if err != nil {
		t.Fatal(err)
	}
	p := project.New(v)
	p.Rules.PreRoll, p.Rules.PostRoll = 0, 0
	p.Rallies = []project.Rally{{ID: "r1", Start: 1, End: 3, Selected: true}}
	var pts []project.TrackPoint
	for i := 0; i <= 60; i++ {
		t := 1 + float64(i)/30
		pts = append(pts, project.TrackPoint{T: t, X: 0.3 + 0.4*float64(i)/60, Y: 0.6})
	}
	p.Tracks = []project.BallTrack{{ID: "1", Points: pts}}
	p.ExportSettings = project.ExportSettings{Encoder: "software", ShowTrajectory: true, ShowRallyLabels: true}
	p.SyncActive()
	out := filepath.Join(dir, "out.mp4")
	if err := Run(ctx, p, out, func(float64, string) {}); err != nil {
		t.Fatal(err)
	}
	// Grab the output frame at 1s (source 2s): ball near x≈0.5, label top-left.
	still := filepath.Join(dir, "still.rgb")
	if o, err := exec.Command(media.Binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-ss", "1", "-i", out, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", still).CombinedOutput(); err != nil {
		t.Fatalf("still: %v %s", err, o)
	}
	rgb, err := os.ReadFile(still)
	if err != nil {
		t.Fatal(err)
	}
	at := func(x, y int) [3]byte { i := (y*640 + x) * 3; return [3]byte{rgb[i], rgb[i+1], rgb[i+2]} }
	orange := 0
	for x := 250; x < 390; x++ {
		c := at(x, 216)
		if c[0] > 180 && c[1] > 120 && c[2] < 150 {
			orange++
		}
	}
	if orange < 5 {
		t.Fatalf("trajectory not burned in near y=216 (orange px=%d)", orange)
	}
	white := 0
	for y := 8; y < 45; y++ {
		for x := 14; x < 140; x++ {
			if c := at(x, y); c[0] > 200 && c[1] > 200 && c[2] > 200 {
				white++
			}
		}
	}
	if white < 20 {
		t.Fatalf("rally label not burned in (white px=%d)", white)
	}
	if c := at(600, 40); c[0] > 60 {
		t.Fatalf("overlay leaked elsewhere: %v", c)
	}
}
