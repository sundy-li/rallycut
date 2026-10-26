#!/usr/bin/env python3
"""Convert the pinned BlurBall detector to Core ML (FP16) and benchmark it.

Torch MPS stays the reference: the converted model must reproduce its heatmaps
before it is allowed anywhere near the analysis pipeline.
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


def convert(output: Path, batch: int) -> None:
    import coremltools as ct

    wrapper = SigmoidHead(load_model()).eval()
    example = torch.randn(batch, *INPUT_SHAPE[1:])
    with torch.no_grad():
        traced = torch.jit.trace(wrapper, example)
    # The pipeline runs four 3-frame windows per call. Enumerated shapes keep a
    # single Python/Core ML round-trip per batch instead of one per window.
    shapes = ct.EnumeratedShapes(shapes=[(1, 9, 288, 512), (4, 9, 288, 512)])
    model = ct.convert(
        traced,
        inputs=[ct.TensorType(name="frames", shape=shapes, dtype=np.float32)],
        outputs=[ct.TensorType(name="heatmap")],
        minimum_deployment_target=ct.target.macOS15,
        compute_precision=ct.precision.FLOAT16,
        convert_to="mlprogram",
    )
    model.short_description = "RallyCut BlurBall heatmap (FP16, ANE-capable)"
    output.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(output))
    print(f"saved {output} ({sum(f.stat().st_size for f in output.rglob('*') if f.is_file())/1e6:.2f} MB)")


def parity(path: Path, batch: int) -> None:
    import coremltools as ct

    torch.manual_seed(0)
    frames = torch.randn(batch, *INPUT_SHAPE[1:])
    with torch.no_grad():
        reference = SigmoidHead(load_model())(frames).numpy()
    model = ct.models.MLModel(str(path), compute_units=ct.ComputeUnit.ALL)
    prediction = model.predict({"frames": frames.numpy()})["heatmap"]
    diff = np.abs(prediction - reference)
    print(
        f"parity: max={diff.max():.5f} mean={diff.mean():.6f} "
        f"corr={np.corrcoef(prediction.ravel(), reference.ravel())[0,1]:.6f}"
    )


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
    parser.add_argument("--out", default=str(ROOT / "models/derived/BlurBall.mlpackage"))
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=60)
    parser.add_argument("--skip-convert", action="store_true")
    args = parser.parse_args()
    path = Path(args.out)
    if not args.skip_convert:
        convert(path, args.batch)
    parity(path, args.batch)
    benchmark(path, args.batch, args.iterations)


if __name__ == "__main__":
    main()
