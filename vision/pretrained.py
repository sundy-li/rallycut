"""Pinned BlurBall inference. No auto-download or unsafe pickle loading."""
import hashlib
import json
import os
import sys
from pathlib import Path

MODEL = 'blurball-pretrained-v1'
WEIGHTS_SHA256 = '3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f'
WEIGHTS_URL = 'https://cloud.cs.uni-tuebingen.de/public.php/dav/files/6Z8TpM3sXRKHzGC/blurball_best'


class Config(dict):
    def __getattr__(self, key):
        value = self[key]
        return Config(value) if isinstance(value, dict) else value


def locate_weights():
    explicit = os.environ.get('RALLYCUT_MODEL_PATH')
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ValueError(f'RALLYCUT_MODEL_PATH 不存在: {path}')
        return path
    roots = [Path.cwd(), Path(sys.executable).absolute().parent, Path(__file__).resolve().parent]
    if os.environ.get('RALLYCUT_DATA_DIR'):
        roots.insert(0, Path(os.environ['RALLYCUT_DATA_DIR']))
    roots.append(Path.home()/'Library/Application Support/RallyCut')
    for root in roots:
        for parent in [root, *list(root.parents)[:6]]:
            for relative in ('models/weights/blurball_best.pth', 'models/blurball_best.pth'):
                path = parent/relative
                if path.is_file():
                    return path
    raise ValueError('未安装本地视觉模型权重，请运行 just setup-model；不会退回传统视觉或模拟结果')


class BlurBallDetector:
    def __init__(self, weights=None, device='auto', threshold=.7, precision='fp32', runtime='auto'):
        from backends import create_backend
        if not .01 <= threshold <= .99:
            raise ValueError('invalid heatmap threshold')
        self.threshold=threshold
        self.backend=create_backend(runtime)
        if self.backend is not None:
            import numpy as np
            self.model=None
            self.device=self.backend.name
            self.precision='fp16'
            self.sha256=WEIGHTS_SHA256
            self._np_mean=np.array([.485,.456,.406]*3,dtype='float32').reshape(1,9,1,1)
            self._np_std=np.array([.229,.224,.225]*3,dtype='float32').reshape(1,9,1,1)
            return
        import torch
        from vendor.blurball.network import BlurBall
        if precision not in ('fp32','fp16'):
            raise ValueError('precision must be fp32 or fp16')
        path = Path(weights) if weights else locate_weights()
        if path.stat().st_size != 6156034:
            raise ValueError('视觉模型权重 SHA-256 / 文件大小不匹配，拒绝加载未知 checkpoint')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != WEIGHTS_SHA256:
            raise ValueError('视觉模型权重 SHA-256 不匹配，拒绝加载未知 checkpoint')
        device = os.environ.get('RALLYCUT_INFERENCE_DEVICE', device)
        if device == 'auto':
            device = 'mps' if torch.backends.mps.is_available() else 'cpu'
        if device not in ('mps', 'cpu'):
            raise ValueError('supported devices: auto, mps, cpu')
        if device == 'mps' and not torch.backends.mps.is_available():
            raise ValueError('MPS unavailable')
        if precision=='fp16' and device=='cpu':
            raise ValueError('FP16 requires MPS; use fp32 on CPU')
        # Leave cores for the decode and postprocess threads but do not pin
        # inference to 2 threads: CPU-only hosts (including x64 builds inside a
        # Windows-on-ARM VM) gain from the remaining cores.
        torch.set_num_threads(max(2, min(4, os.cpu_count() or 2)))
        cfg = Config(json.loads((Path(__file__).parent/'vendor/blurball/config.json').read_text()))
        self.model = BlurBall(cfg)
        checkpoint = torch.load(path, map_location='cpu', weights_only=True)
        self.model.load_state_dict(checkpoint['model_state_dict'], strict=True)
        self.model.eval().to(device)
        if precision=='fp16':
            self.model.half()
        self.device, self.threshold, self.precision = device, threshold, precision
        self._mean=torch.tensor([.485,.456,.406]*3,dtype=torch.float32).view(1,9,1,1)
        self._std=torch.tensor([.229,.224,.225]*3,dtype=torch.float32).view(1,9,1,1)
        self.sha256 = digest

    @staticmethod
    def prepare_frame(frame):
        import cv2
        import numpy as np
        height, width = frame.shape[:2]
        scale = min(512/width, 288/height)
        matrix = np.array([[scale, 0, (512-width*scale)/2], [0, scale, (288-height*scale)/2]], dtype='float32')
        # Channel permutation commutes with per-channel affine interpolation.
        # Convert only the 512x288 result, not every full-resolution source pixel.
        small = cv2.warpAffine(frame, matrix, (512, 288), flags=cv2.INTER_LINEAR)
        image = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        return image.transpose(2,0,1), (scale,float(matrix[0,2]),float(matrix[1,2]),width,height)

    @staticmethod
    def preprocess(frame):
        """Legacy FP32 API retained for parity checks and external callers."""
        import numpy as np
        tensor,transform=BlurBallDetector.prepare_frame(frame)
        tensor=tensor.astype('float32')/255
        tensor=(tensor-np.array([.485,.456,.406],dtype='float32')[:,None,None])/np.array([.229,.224,.225],dtype='float32')[:,None,None]
        return tensor,transform

    @staticmethod
    def peaks(heatmap, transform, threshold):
        import cv2
        import numpy as np
        scale, tx, ty, width, height = transform
        n, labels, stats, _ = cv2.connectedComponentsWithStats((heatmap>=threshold).astype('uint8'), 8)
        detections = []
        for index in range(1, n):
            x, y, bw, bh, area = stats[index]
            if area < 1 or area > 400:
                continue
            yy, xx = np.where(labels[y:y+bh,x:x+bw] == index)
            values = heatmap[y+yy,x+xx]
            cx = (float(np.sum((x+xx)*values)/values.sum())-tx)/scale
            cy = (float(np.sum((y+yy)*values)/values.sum())-ty)/scale
            if 0 <= cx < width and 0 <= cy < height:
                detections.append((cx/width, cy/height, float(values.max())))
        return sorted(detections,key=lambda p:-p[2])[:8]

    def prepare_batch(self, windows):
        """Normalize once per batch in FP32; bounded uint8 producer buffers.

        Keep the exact RGB affine transform, unlike the local fork's BGR resize
        shortcut. This preserves the already-validated coordinate convention.
        """
        import numpy as np
        import torch
        if not 1<=len(windows)<=8 or any(len(window)!=3 for window in windows):
            raise ValueError('expected 1-8 windows of exactly 3 real frames')
        dtype=windows[0][0][0].dtype
        if dtype not in (np.dtype('uint8'),np.dtype('float32')):
            raise ValueError('expected uint8 RGB or legacy normalized float32')
        batch=np.empty((len(windows),9,288,512),dtype=dtype)
        for index,window in enumerate(windows):
            for frame,pair in enumerate(window):
                if pair[0].shape!=(3,288,512) or pair[0].dtype!=dtype:
                    raise ValueError('inconsistent frame dtype or dimensions')
                batch[index,frame*3:(frame+1)*3]=pair[0]
        tensor=torch.from_numpy(batch)
        if dtype==np.dtype('uint8'):
            tensor=tensor.float().div_(255).sub_(self._mean).div_(self._std)
        return tensor

    def prepare_input(self, windows):
        """Normalized NCHW batch for the accelerated backends (no torch)."""
        import numpy as np
        if not 1<=len(windows)<=8 or any(len(window)!=3 for window in windows):
            raise ValueError('expected 1-8 windows of exactly 3 real frames')
        dtype=windows[0][0][0].dtype
        if dtype not in (np.dtype('uint8'),np.dtype('float32')):
            raise ValueError('expected uint8 RGB or legacy normalized float32')
        batch=np.empty((len(windows),9,288,512),dtype=np.float32)
        for index,window in enumerate(windows):
            for frame,pair in enumerate(window):
                if pair[0].shape!=(3,288,512) or pair[0].dtype!=dtype:
                    raise ValueError('inconsistent frame dtype or dimensions')
                batch[index,frame*3:(frame+1)*3]=pair[0]
        if dtype==np.dtype('uint8'):
            batch=batch/255.0
        return (batch-self._np_mean)/self._np_std

    def predict_heatmaps(self, windows):
        if self.backend is not None:
            return self.backend.predict(self.prepare_input(windows))
        """GPU-only phase; the calling thread owns MPS and the CPU transfer."""
        import torch
        batch=self.prepare_batch(windows)
        dtype=torch.float16 if self.precision=='fp16' else torch.float32
        with torch.inference_mode():
            logits=self.model(batch.to(device=self.device,dtype=dtype))[0]
            # FP32 sigmoid also in FP16 mode avoids extra half-score rounding.
            return logits.float().sigmoid().cpu().numpy()

    def postprocess(self, windows, prediction):
        return [[self.peaks(prediction[b,i],windows[b][i][1],self.threshold) for i in range(3)] for b in range(len(windows))]

    def predict(self, windows):
        return self.postprocess(windows,self.predict_heatmaps(windows))
