"""Local Core ML derivative of the pinned BlurBall weights (Apple silicon).

The .mlpackage is derived from the weights, so it is never shipped: the
desktop setup converts it once on the user's Mac. A sidecar JSON written only
after a parity check against torch marks a package as usable; backends.py
ignores packages without a matching sidecar and keeps the torch path.

    python coreml_model.py convert --data-dir <RallyCut data dir>
    python coreml_model.py status  --data-dir <RallyCut data dir>   # ready | failed | missing

Exit 0 means a verified package (or an already valid one) exists. Any failure
writes a marker so setup does not retry the same converter / weights forever.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# The desktop runs this with `python -I` (no script dir on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Bump when conversion settings change; old packages then stop matching.
CONVERTER = 'coreml-fp16-b14-v1'
PACKAGE = 'BlurBall.mlpackage'
SIDECAR = PACKAGE + '.json'
FAILED = PACKAGE + '.failed.json'
# Measured on random inputs: max |diff| 2e-4, corr 0.99999.
MAX_ABS_DIFF = 1e-2
MIN_CORRELATION = 0.999


def derived_dir(data_dir):
    return Path(data_dir) / 'models' / 'derived'


def _weights_sha256():
    from pretrained import WEIGHTS_SHA256
    return WEIGHTS_SHA256


def sidecar_ok(package):
    """True when `package` was produced and verified by this converter."""
    package = Path(package)
    try:
        meta = json.loads((package.parent / SIDECAR).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return (package.is_dir() and meta.get('converter') == CONVERTER and
            meta.get('weights_sha256') == _weights_sha256() and meta.get('package') == PACKAGE)


def failure_recorded(data_dir):
    """True when this converter already failed for these weights on this Mac."""
    try:
        meta = json.loads((derived_dir(data_dir) / FAILED).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return meta.get('converter') == CONVERTER and meta.get('weights_sha256') == _weights_sha256()


def _load_torch_model():
    import torch
    from pretrained import BlurBallDetector
    detector = BlurBallDetector(device='cpu', runtime='torch')  # verifies size + SHA-256

    class SigmoidHead(torch.nn.Module):
        """Match BlurBallDetector.predict_heatmaps(): scale-0 logits, then sigmoid."""
        def __init__(self, model):
            super().__init__()
            self.model = model

        def forward(self, frames):
            return self.model(frames)[0].sigmoid()

    return SigmoidHead(detector.model).eval()


def convert_package(output):
    """Trace + convert to an FP16 ML program with batch 1 and 4 (pipeline batch)."""
    import coremltools as ct
    import numpy as np
    import torch
    wrapper = _load_torch_model()
    example = torch.randn(4, 9, 288, 512)
    with torch.no_grad():
        traced = torch.jit.trace(wrapper, example)
    shapes = ct.EnumeratedShapes(shapes=[(1, 9, 288, 512), (4, 9, 288, 512)])
    model = ct.convert(
        traced,
        inputs=[ct.TensorType(name='frames', shape=shapes, dtype=np.float32)],
        outputs=[ct.TensorType(name='heatmap')],
        minimum_deployment_target=ct.target.macOS15,
        compute_precision=ct.precision.FLOAT16,
        convert_to='mlprogram',
    )
    model.short_description = 'RallyCut BlurBall heatmap (FP16, local derivative of pinned weights)'
    model.save(str(output))
    return wrapper


def parity(package, wrapper):
    """Compare the saved package with torch on fixed inputs; raises on mismatch."""
    import coremltools as ct
    import numpy as np
    import torch
    model = ct.models.MLModel(str(package), compute_units=ct.ComputeUnit.ALL)
    generator = torch.Generator().manual_seed(0)
    worst = 0.0
    lowest = 1.0
    for batch in (torch.randn(4, 9, 288, 512, generator=generator), torch.zeros(1, 9, 288, 512)):
        with torch.no_grad():
            reference = wrapper(batch).numpy()
        prediction = np.asarray(model.predict({'frames': batch.numpy()})['heatmap'])
        if prediction.shape != reference.shape or not np.isfinite(prediction).all():
            raise ValueError(f'Core ML output shape / values invalid: {prediction.shape}')
        worst = max(worst, float(np.abs(prediction - reference).max()))
        if reference.std() > 1e-6:
            lowest = min(lowest, float(np.corrcoef(prediction.ravel(), reference.ravel())[0, 1]))
    if worst > MAX_ABS_DIFF or lowest < MIN_CORRELATION:
        raise ValueError(f'Core ML parity failed: max diff {worst:.5f}, corr {lowest:.6f}')
    return {'max_abs_diff': round(worst, 6), 'min_correlation': round(lowest, 6)}


def _write_json(path, payload):
    temp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(temp, path)


def ensure(data_dir):
    """Convert into <data_dir>/models/derived unless a verified package exists."""
    target_dir = derived_dir(data_dir)
    package = target_dir / PACKAGE
    if sidecar_ok(package):
        return package, None
    target_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    stage = Path(tempfile.mkdtemp(prefix='.coreml-', dir=target_dir))
    try:
        import coremltools
        import torch
        built = stage / PACKAGE
        report = parity(built, convert_package(built))
        # Sidecar last: a crash in between leaves no marker, so it is retried.
        (target_dir / SIDECAR).unlink(missing_ok=True)
        if package.exists():
            shutil.rmtree(package)
        os.replace(built, package)
        _write_json(target_dir / SIDECAR, {
            'converter': CONVERTER, 'package': PACKAGE, 'weights_sha256': _weights_sha256(),
            'coremltools': coremltools.__version__, 'torch': torch.__version__,
            'parity': report, 'seconds': round(time.monotonic() - started, 1),
            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
        (target_dir / FAILED).unlink(missing_ok=True)
        return package, report
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('convert', 'status'):
        p = sub.add_parser(name)
        p.add_argument('--data-dir', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'status':
        # Cheap (no torch / coremltools import) for the setup readiness check.
        package = derived_dir(args.data_dir) / PACKAGE
        print('ready' if sidecar_ok(package) else 'failed' if failure_recorded(args.data_dir) else 'missing')
        return 0
    if sys.platform != 'darwin':
        raise SystemExit('Core ML conversion requires macOS')
    try:
        package, report = ensure(args.data_dir)
    except BaseException as error:  # record, then report the real cause
        if isinstance(error, KeyboardInterrupt):
            raise
        target_dir = derived_dir(args.data_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        _write_json(target_dir / FAILED, {'converter': CONVERTER, 'weights_sha256': _weights_sha256(),
                                          'error': f'{type(error).__name__}: {error}'[:2000]})
        print(f'Core ML conversion failed: {type(error).__name__}: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'package': str(package), 'parity': report, 'reused': report is None}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
