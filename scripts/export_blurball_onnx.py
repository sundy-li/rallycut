#!/usr/bin/env python3
"""Export the pinned BlurBall detector to ONNX for Windows (DirectML/CUDA/CPU)."""
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


class SigmoidHead(torch.nn.Module):
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


def export(output: Path) -> None:
    wrapper = SigmoidHead(load_model()).eval()
    example = torch.randn(1, 9, 288, 512)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        wrapper,
        example,
        str(output),
        input_names=["frames"],
        output_names=["heatmap"],
        dynamic_axes={"frames": {0: "batch"}, "heatmap": {0: "batch"}},
        opset_version=17,
        do_constant_folding=True,
        dynamo=False,
    )
    print(f"saved {output} ({output.stat().st_size/1e6:.2f} MB)")


def benchmark(output: Path, iterations: int) -> None:
    import onnxruntime as ort

    providers = [p for p in ("DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
    session = ort.InferenceSession(str(output), providers=providers)
    name = session.get_inputs()[0].name
    batch = np.random.RandomState(0).randn(4, 9, 288, 512).astype(np.float32)

    reference = SigmoidHead(load_model())(torch.from_numpy(batch)).detach().numpy()
    prediction = session.run(None, {name: batch})[0]
    diff = np.abs(prediction - reference)
    print(f"parity: max={diff.max():.5f} mean={diff.mean():.6f} providers={session.get_providers()}")

    for _ in range(3):
        session.run(None, {name: batch})
    started = time.perf_counter()
    for _ in range(iterations):
        session.run(None, {name: batch})
    elapsed = (time.perf_counter() - started) / iterations * 1000
    print(f"onnx {providers[0]:22s} {elapsed:7.2f} ms / {batch.shape[0]} windows  {3*batch.shape[0]/elapsed*1000:7.1f} frames/s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "models/derived/BlurBall.onnx"))
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--skip-export", action="store_true")
    args = parser.parse_args()
    path = Path(args.out)
    if not args.skip_export:
        export(path)
    benchmark(path, args.iterations)


if __name__ == "__main__":
    main()
