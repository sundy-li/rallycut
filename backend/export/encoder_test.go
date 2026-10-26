package export

import (
	"rallycut/backend/project"
	"slices"
	"testing"
)

func TestMacVideoToolboxAndSoftwareFallbackPlans(t *testing.T) {
	for _, codec := range []string{"h264", "hevc"} {
		plans, err := encodingPlans("darwin", project.ExportSettings{Codec: codec}, 8233650)
		if err != nil {
			t.Fatal(err)
		}
		hw := plans[0]
		if len(plans) != 2 || !hw.Hardware || hw.Name != codec+"_videotoolbox" || !slices.Contains(hw.Args, "8233650") {
			t.Fatal(plans)
		}
		if slices.Contains(hw.Args, "-preset") || slices.Contains(hw.Args, "-crf") {
			t.Fatal("software arguments leaked into VideoToolbox")
		}
		if codec == "hevc" && !slices.Contains(hw.Args, "hvc1") {
			t.Fatal("HEVC Apple-compatible tag missing")
		}
		if plans[1].Hardware || !slices.Contains(plans[1].Args, "-preset") {
			t.Fatal("missing software fallback")
		}
	}
}
func TestSoftwareModeAndNonMac(t *testing.T) {
	for _, tc := range []struct{ os, mode string }{{"darwin", "software"}, {"linux", "auto"}} {
		plans, err := encodingPlans(tc.os, project.ExportSettings{Encoder: tc.mode, BitRate: 9000000}, 0)
		if err != nil || len(plans) != 1 || plans[0].Hardware || !slices.Contains(plans[0].Args, "9000000") {
			t.Fatal(plans, err)
		}
	}
	if _, err := encodingPlans("darwin", project.ExportSettings{Codec: "arbitrary"}, 0); err == nil {
		t.Fatal("unknown codec accepted")
	}
}
