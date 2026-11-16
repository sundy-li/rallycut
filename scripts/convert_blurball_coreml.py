#!/usr/bin/env python3
"""Convert the pinned BlurBall detector to Core ML (FP16) and benchmark it.

Conversion, the torch parity gate and the sidecar live in vision/coreml_model.py,
shared with the desktop setup; this script adds the speed comparison.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vision"))

from pretrained import Config, locate_weights  # noqa: E402
from vendor.blurball.network import BlurBall  # noqa: E402

INPUT_SHAPE = (1, 9, 288, 512)


class SigmoidHead(torch.nn.Module):
    """Match predict_heatmaps(): scale-0 logits followed by sigmoid."""

    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, frames: torch.Tensor) -> torch.Tensor:
        return self.model(frames)[0].sigmoid()


def load_model() -> torch.nn.Module:
    config = Config(json.loads((ROOT / "vision/vendor/blurball/config.json").read_text()))
    model = BlurBall(config)
    checkpoint = torch.load(locate_weights(), map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    return model.eval()


def benchmark(path: Path, batch: int, iterations: int) -> None:
    import coremltools as ct

    frames = np.random.RandomState(0).randn(batch, *INPUT_SHAPE[1:]).astype(np.float32)
    units = {
        "ANE+GPU+CPU": ct.ComputeUnit.ALL,
        "CPU+GPU": ct.ComputeUnit.CPU_AND_GPU,
        "CPU only": ct.ComputeUnit.CPU_ONLY,
    }
    for label, unit in units.items():
        model = ct.models.MLModel(str(path), compute_units=unit)
        for _ in range(5):
            model.predict({"frames": frames})
        started = time.perf_counter()
        for _ in range(iterations):
            model.predict({"frames": frames})
        elapsed = (time.perf_counter() - started) / iterations * 1000
        device = ""
        try:
            device = model.get_compute_device()
        except Exception:
            pass
        print(f"coreml {label:10s} {elapsed:7.2f} ms/call  {3*batch/elapsed*1000:7.1f} frames/s {device}")

    model = load_model().to("mps")
    tensor = torch.from_numpy(frames).to("mps")
    with torch.inference_mode():
        for _ in range(5):
            SigmoidHead(model)(tensor)
        torch.mps.synchronize()
        started = time.perf_counter()
        for _ in range(iterations):
            SigmoidHead(model)(tensor)
        torch.mps.synchronize()
        elapsed = (time.perf_counter() - started) / iterations * 1000
    print(f"torch MPS fp32     {elapsed:7.2f} ms/call  {3*batch/elapsed*1000:7.1f} frames/s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT), help="writes <root>/models/derived/BlurBall.mlpackage")
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=60)
    parser.add_argument("--force", action="store_true", help="reconvert even if a verified package exists")
    args = parser.parse_args()
    import coreml_model
    target = coreml_model.derived_dir(args.root)
    if args.force:
        (target / coreml_model.SIDECAR).unlink(missing_ok=True)
    # Same conversion + parity gate + sidecar as the desktop setup.
    path, report = coreml_model.ensure(args.root)
    print(f"{path}: {'reused verified package' if report is None else report}")
    benchmark(path, args.batch, args.iterations)


if __name__ == "__main__":
    main()
