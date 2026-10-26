package export

import (
	"fmt"
	"math"
	"os"
	"strings"
	"sync"

	"image"
	"image/color"

	"golang.org/x/image/font"
	"golang.org/x/image/font/opentype"
	"golang.org/x/image/math/fixed"

	"rallycut/backend/project"
	"rallycut/backend/timeline"
)

// overlaySpec describes the transparent RGBA layer burned into one exported
// span. Coordinates follow the decoded (rotation-applied) frame, the same space
// the player draws ball tracks in.
type overlaySpec struct {
	Width, Height int
	FPS           float64
	Start, Length float64 // source seconds
	Tracks        []project.BallTrack
	Labels        []timeline.Label
	Face          font.Face
}

// Player style (TrajectoryOverlay.tsx): a 1000-unit-wide viewBox scaled to the
// frame width, points in [t-0.3, t+0.1], polyline stroke 2, hollow ring r=7.
const (
	trackBefore = 0.3
	trackAfter  = 0.1
	strokeUnits = 2.0
	ringUnits   = 7.0
)

var trackColor = [3]float64{0xff, 0xbd, 0x68}

func (s overlaySpec) frameCount() int {
	return int(math.Ceil(s.Length*s.FPS)) + 1
}

// overlayRenderer keeps one straight-alpha RGBA frame and only clears the
// rectangles touched by the previous frame, so mostly-empty frames stay cheap.
type overlayRenderer struct {
	spec   overlaySpec
	buf    []byte
	dirty  []image.Rectangle
	badges map[int]*image.NRGBA
}

func newOverlayRenderer(spec overlaySpec) *overlayRenderer {
	return &overlayRenderer{spec: spec, buf: make([]byte, spec.Width*spec.Height*4), badges: map[int]*image.NRGBA{}}
}

// frame renders output frame n (source time Start + n/FPS).
func (r *overlayRenderer) frame(n int) []byte {
	for _, rect := range r.dirty {
		for y := rect.Min.Y; y < rect.Max.Y; y++ {
			row := r.buf[(y*r.spec.Width+rect.Min.X)*4 : (y*r.spec.Width+rect.Max.X)*4]
			clear(row)
		}
	}
	r.dirty = r.dirty[:0]
	t := r.spec.Start + float64(n)/r.spec.FPS
	if len(r.spec.Tracks) > 0 {
		r.drawTracks(t)
	}
	if len(r.spec.Labels) > 0 && r.spec.Face != nil {
		r.drawLabel(t)
	}
	return r.buf
}

func (r *overlayRenderer) unit() float64 { return float64(r.spec.Width) / 1000 }

func (r *overlayRenderer) drawTracks(t float64) {
	w := math.Max(1.5, strokeUnits*r.unit())
	ring := ringUnits * r.unit()
	for _, track := range r.spec.Tracks {
		if track.OffPlay || len(track.Points) == 0 {
			continue
		}
		var pts [][2]float64
		for _, p := range track.Points {
			if p.T >= t-trackBefore && p.T <= t+trackAfter {
				pts = append(pts, [2]float64{p.X * float64(r.spec.Width), p.Y * float64(r.spec.Height)})
			}
		}
		if len(pts) == 0 {
			continue
		}
		r.stroke(func(x, y float64) float64 {
			if len(pts) == 1 {
				return math.Inf(1)
			}
			best := math.Inf(1)
			for i := 1; i < len(pts); i++ {
				best = math.Min(best, segmentDistance(x, y, pts[i-1], pts[i]))
			}
			return best - w/2
		}, bounds(pts, w+1))
		last := pts[len(pts)-1]
		r.stroke(func(x, y float64) float64 {
			return math.Abs(math.Hypot(x-last[0], y-last[1])-ring) - w/2
		}, bounds([][2]float64{last}, ring+w+1))
	}
}

func bounds(pts [][2]float64, pad float64) image.Rectangle {
	minX, minY, maxX, maxY := math.Inf(1), math.Inf(1), math.Inf(-1), math.Inf(-1)
	for _, p := range pts {
		minX, minY = math.Min(minX, p[0]), math.Min(minY, p[1])
		maxX, maxY = math.Max(maxX, p[0]), math.Max(maxY, p[1])
	}
	return image.Rect(int(math.Floor(minX-pad)), int(math.Floor(minY-pad)), int(math.Ceil(maxX+pad))+1, int(math.Ceil(maxY+pad))+1)
}

func segmentDistance(x, y float64, a, b [2]float64) float64 {
	dx, dy := b[0]-a[0], b[1]-a[1]
	l := dx*dx + dy*dy
	u := 0.0
	if l > 0 {
		u = math.Max(0, math.Min(1, ((x-a[0])*dx+(y-a[1])*dy)/l))
	}
	return math.Hypot(x-(a[0]+u*dx), y-(a[1]+u*dy))
}

// stroke fills one shape in the track color with ~1px anti-aliasing. sdf is a
// signed distance (negative inside). Coverage is computed once per pixel per
// shape, so overlapping segments of one polyline never darken their joints.
func (r *overlayRenderer) stroke(sdf func(x, y float64) float64, area image.Rectangle) {
	area = area.Intersect(image.Rect(0, 0, r.spec.Width, r.spec.Height))
	if area.Empty() {
		return
	}
	for y := area.Min.Y; y < area.Max.Y; y++ {
		for x := area.Min.X; x < area.Max.X; x++ {
			a := 0.5 - sdf(float64(x)+.5, float64(y)+.5)
			if a <= 0 {
				continue
			}
			r.blend(x, y, trackColor, math.Min(1, a))
		}
	}
	r.dirty = append(r.dirty, area)
}

// blend composites a straight-alpha color over the buffer (FFmpeg's overlay
// filter reads rawvideo rgba as straight alpha).
func (r *overlayRenderer) blend(x, y int, c [3]float64, a float64) {
	i := (y*r.spec.Width + x) * 4
	da := float64(r.buf[i+3]) / 255
	oa := a + da*(1-a)
	if oa <= 0 {
		return
	}
	for k := 0; k < 3; k++ {
		r.buf[i+k] = uint8(math.Round((c[k]*a + float64(r.buf[i+k])*da*(1-a)) / oa))
	}
	r.buf[i+3] = uint8(math.Round(oa * 255))
}

// labelAt returns the rally number shown at source time t: the last label whose
// From is not after t (the first label always covers the span start).
func labelAt(labels []timeline.Label, t float64) int {
	n := 0
	for _, l := range labels {
		if l.From <= t+1e-9 || n == 0 {
			n = l.Number
		}
	}
	return n
}

func (r *overlayRenderer) drawLabel(t float64) {
	n := labelAt(r.spec.Labels, t)
	if n <= 0 {
		return
	}
	badge := r.badges[n]
	if badge == nil {
		badge = renderBadge(r.spec.Face, fmt.Sprintf("回合 %02d", n), r.spec.Height)
		r.badges[n] = badge
	}
	x0 := int(math.Round(float64(r.spec.Width) * 0.025))
	y0 := int(math.Round(float64(r.spec.Height) * 0.03))
	b := badge.Bounds().Add(image.Pt(x0, y0)).Intersect(image.Rect(0, 0, r.spec.Width, r.spec.Height))
	for y := b.Min.Y; y < b.Max.Y; y++ {
		for x := b.Min.X; x < b.Max.X; x++ {
			p := badge.NRGBAAt(x-x0, y-y0)
			if p.A == 0 {
				continue
			}
			r.blend(x, y, [3]float64{float64(p.R), float64(p.G), float64(p.B)}, float64(p.A)/255)
		}
	}
	r.dirty = append(r.dirty, b)
}

// renderBadge draws white text on a rounded translucent dark plate.
func renderBadge(face font.Face, text string, frameHeight int) *image.NRGBA {
	metrics := face.Metrics()
	ascent, descent := metrics.Ascent.Ceil(), metrics.Descent.Ceil()
	textWidth := font.MeasureString(face, text).Ceil()
	padX := int(math.Round(float64(frameHeight) * 0.014))
	padY := int(math.Round(float64(frameHeight) * 0.008))
	w, h := textWidth+2*padX, ascent+descent+2*padY
	badge := image.NewNRGBA(image.Rect(0, 0, w, h))
	radius := float64(h) * 0.22
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			// Rounded-rect signed distance, 1px anti-aliased edge.
			qx := math.Max(math.Abs(float64(x)+.5-float64(w)/2)-(float64(w)/2-radius), 0)
			qy := math.Max(math.Abs(float64(y)+.5-float64(h)/2)-(float64(h)/2-radius), 0)
			a := math.Max(0, math.Min(1, 0.5-(math.Hypot(qx, qy)-radius)))
			badge.SetNRGBA(x, y, nrgba(0, 0, 0, a*0.55))
		}
	}
	mask := image.NewAlpha(badge.Bounds())
	d := font.Drawer{Dst: mask, Src: image.Opaque, Face: face, Dot: fixed.P(padX, padY+ascent)}
	d.DrawString(text)
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			ta := float64(mask.AlphaAt(x, y).A) / 255
			if ta == 0 {
				continue
			}
			bg := badge.NRGBAAt(x, y)
			ba := float64(bg.A) / 255
			oa := ta + ba*(1-ta)
			// Text is white; the plate is black, so only luminance blends.
			v := 255 * ta / oa
			badge.SetNRGBA(x, y, nrgba(v, v, v, oa))
		}
	}
	return badge
}

func nrgba(r, g, b, a float64) color.NRGBA {
	return color.NRGBA{R: uint8(math.Round(r)), G: uint8(math.Round(g)), B: uint8(math.Round(b)), A: uint8(math.Round(a * 255))}
}

// cjkFonts are system fonts able to render 「回合」; the first readable wins.
var cjkFonts = []string{
	"/System/Library/Fonts/STHeiti Medium.ttc",
	"/System/Library/Fonts/Hiragino Sans GB.ttc",
	"/System/Library/Fonts/STHeiti Light.ttc",
	"/System/Library/Fonts/Supplemental/Songti.ttc",
	"/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
	"/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
}

var (
	labelFontOnce sync.Once
	labelFont     *opentype.Font
	labelFontErr  error
)

func loadLabelFont() (*opentype.Font, error) {
	labelFontOnce.Do(func() {
		for _, path := range cjkFonts {
			data, err := os.ReadFile(path)
			if err != nil {
				continue
			}
			if strings.HasSuffix(strings.ToLower(path), ".ttc") {
				collection, err := opentype.ParseCollection(data)
				if err != nil || collection.NumFonts() == 0 {
					continue
				}
				if f, err := collection.Font(0); err == nil {
					labelFont = f
					return
				}
				continue
			}
			if f, err := opentype.Parse(data); err == nil {
				labelFont = f
				return
			}
		}
		labelFontErr = fmt.Errorf("未找到可用的中文字体，无法在导出画面上叠加回合编号；可取消该选项后再导出")
	})
	return labelFont, labelFontErr
}

func labelFace(frameHeight int) (font.Face, error) {
	f, err := loadLabelFont()
	if err != nil {
		return nil, err
	}
	size := math.Max(14, float64(frameHeight)*0.042)
	return opentype.NewFace(f, &opentype.FaceOptions{Size: size, DPI: 72, Hinting: font.HintingNone})
}
