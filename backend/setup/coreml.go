package setup

import (
	"context"

	"rallycut/backend/analysis"
)

const coreMLMissingDetail = "需要在本机生成 Apple 神经引擎加速模型（不联网，约 1 分钟）"

// coreMLApplies: only the pip-managed macOS runtime on Apple silicon converts
// a local Core ML package. Prebuilt Windows bundles never do.
func (p *Provisioner) coreMLApplies(root string) bool {
	return analysis.CoreMLSupported() && root == "" && p.bundleSpec() == nil && p.options.Worker != ""
}

// ensureCoreML converts the pinned weights to a verified local Core ML
// package. Failure is recorded by the converter and is not fatal: analysis
// then keeps torch MPS, which produces the same detector's results.
func (p *Provisioner) ensureCoreML(ctx context.Context, python, root string) {
	if !p.coreMLApplies(root) {
		return
	}
	if analysis.CoreMLStatus(ctx, python, p.options.Worker, p.options.DataDir) != "missing" {
		return
	}
	p.update(0.9, "model", "生成本机加速模型（Core ML）…", "只在本机转换已校验的权重，不联网；约 1 分钟")
	p.setIndeterminate(true)
	defer p.setIndeterminate(false)
	if err := analysis.ConvertCoreML(ctx, python, p.options.Worker, p.options.DataDir); err != nil {
		p.options.Log.Warn("core ml conversion failed; analysis keeps torch MPS", "error", err)
		p.update(0.95, "model", "加速模型未生成，分析继续使用 MPS", "")
		return
	}
	p.options.Log.Info("core ml package ready")
}

func checkDetail(checks []CheckItem, id string) string {
	for _, c := range checks {
		if c.ID == id {
			return c.Detail
		}
	}
	return ""
}
