"""Accelerated heatmap backends with a PyTorch fallback.

macOS: Core ML / Apple Neural Engine. Windows/Linux: ONNX Runtime with DirectML,
CUDA or CPU. Artifacts are local derivatives of the pinned weights and are never
committed; build them with `just models`.
"""
import os
import sys
from pathlib import Path


def _candidates(kind):
    suffix = "BlurBall.mlpackage" if kind == "coreml" else "BlurBall.onnx"
    roots = []
    if os.environ.get("RALLYCUT_DATA_DIR"):
        roots.append(Path(os.environ["RALLYCUT_DATA_DIR"]))
    roots.append(Path.cwd())
    roots.append(Path(__file__).resolve().parent.parent)
    for root in roots:
        for relative in ("models/derived", "build/coreml", "build/onnx", "models"):
            yield root / relative / suffix


def locate_artifact(kind):
    """Find a converted model, preferring RALLYCUT_COREML_MODEL / RALLYCUT_ONNX_MODEL."""
    env = {"coreml": "RALLYCUT_COREML_MODEL", "onnx": "RALLYCUT_ONNX_MODEL"}[kind]
    explicit = os.environ.get(env)
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None
    for candidate in _candidates(kind):
        if candidate.exists():
            return candidate
    return None


class CoreMLBackend:
    """FP16 mlpackage compiled for macOS 15+, scheduled by Core ML (ANE first)."""

    def __init__(self, path):
        import coremltools as ct
        self.model = ct.models.MLModel(str(path), compute_units=ct.ComputeUnit.ALL)
        self.name = "coreml"

    def predict(self, batch):
        import numpy as np
        # The package enumerates batch 1 and 4; pad the tail, then slice back.
        outputs = []
        index = 0
        while index < len(batch):
            chunk = batch[index:index + 4]
            index += 4
            if chunk.shape[0] in (1, 4):
                outputs.append(self.model.predict({"frames": chunk.astype("float32")})["heatmap"])
            else:
                padded = np.repeat(chunk[-1:], 4, axis=0)
                outputs.append(
                    self.model.predict({"frames": padded.astype("float32")})["heatmap"][: chunk.shape[0]]
                )
        return np.concatenate(outputs, axis=0)


class OnnxBackend:
    """ONNX Runtime; DirectML on Windows, CUDA on NVIDIA, CPU everywhere."""

    def __init__(self, path, require_accelerator=False):
        import onnxruntime as ort
        available = ort.get_available_providers()
        wanted = [
            provider
            for provider in (
                "DmlExecutionProvider",
                "CUDAExecutionProvider",
                "CPUExecutionProvider",
            )
            if provider in available
        ]
        self.session = ort.InferenceSession(str(path), providers=wanted)
        self.input = self.session.get_inputs()[0].name
        self.providers = self.session.get_providers()
        if require_accelerator and self.providers == ["CPUExecutionProvider"]:
            # Measured 395 ms/window on CPU; never slower than the torch path.
            raise RuntimeError("no DirectML/CUDA provider, keeping torch")
        self.name = "onnx:" + (self.providers[0] if self.providers else "cpu")

    def predict(self, batch):
        import numpy as np
        result = self.session.run(None, {self.input: batch.astype("float32")})[0]
        return np.asarray(result)


def create_backend(runtime=None):
    """Return a backend, or None to keep the PyTorch path."""
    runtime = (runtime or "auto").lower()
    if runtime == "auto":
        runtime = os.environ.get("RALLYCUT_RUNTIME", "auto").lower()
    if runtime in ("torch", "none", "off"):
        return None
    order = ["coreml", "onnx"] if runtime == "auto" else [runtime]
    if runtime == "auto" and sys.platform != "darwin":
        order = ["onnx"]
    for kind in order:
        if kind == "coreml" and sys.platform != "darwin":
            continue
        path = locate_artifact(kind)
        if path is None:
            continue
        try:
            if kind == "coreml":
                return CoreMLBackend(path)
            return OnnxBackend(path, require_accelerator=runtime == "auto")
        except Exception as error:  # missing wheel, unsupported op, bad artifact
            print(f"[backends] {kind} unavailable: {error}", file=sys.stderr)
    return None
