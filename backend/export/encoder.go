package export

import (
	"fmt"
	"rallycut/backend/project"
	"strconv"
)

type encodingPlan struct {
	Name     string
	Codec    string
	Hardware bool
	Args     []string
}

// Keep software-only preset/CRF options away from VideoToolbox. -allow_sw 0
// prevents a nominally hardware export from silently using software internally.
func encodingPlans(goos string, settings project.ExportSettings, sourceBitRate int64) ([]encodingPlan, error) {
	if err := project.ValidateExport(settings); err != nil {
		return nil, err
	}
	s := settings.Normalized()
	bitrate := s.BitRate
	if bitrate == 0 {
		bitrate = sourceBitRate
	}
	if bitrate <= 0 {
		bitrate = 8_000_000
	}
	if bitrate < 500_000 {
		bitrate = 500_000
	}
	if bitrate > 200_000_000 {
		bitrate = 200_000_000
	}
	rate := strconv.FormatInt(bitrate, 10)
	plans := []encodingPlan{}
	if goos == "darwin" && s.Encoder == "auto" {
		name := s.Codec + "_videotoolbox"
		args := []string{"-c:v", name, "-allow_sw", "0", "-b:v", rate}
		if s.Codec == "hevc" {
			args = append(args, "-tag:v", "hvc1")
		}
		plans = append(plans, encodingPlan{Name: name, Codec: s.Codec, Hardware: true, Args: args})
	}
	name := "libx264"
	crf := "20"
	if s.Codec == "hevc" {
		name = "libx265"
		crf = "23"
	}
	args := []string{"-c:v", name, "-preset", "fast"}
	// Explicit bitrate also applies to a software fallback; otherwise use its
	// conventional quality-based default rather than implying equal quality.
	if s.BitRate > 0 {
		args = append(args, "-b:v", rate)
	} else {
		args = append(args, "-crf", crf)
	}
	if s.Codec == "hevc" {
		args = append(args, "-tag:v", "hvc1")
	}
	plans = append(plans, encodingPlan{Name: name, Codec: s.Codec, Args: args})
	if len(plans) == 0 {
		return nil, fmt.Errorf("没有可用编码策略")
	}
	return plans, nil
}
