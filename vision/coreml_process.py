"""Core ML inference in a child process, fed through shared memory.

In-process, coremltools' predict() competes with the decode thread for the
GIL: on a 1080p H.264 match the decode thread dropped from ~520 to ~330
frames/s while Core ML ran in the same interpreter, and kept ~440 frames/s
when the model ran in another process. The parent writes uint8 RGB windows
into shared memory; the child normalizes them with pretrained.normalize_input
(the exact in-process arithmetic) and runs the same CoreMLBackend, so the
heatmaps are identical to the in-process backend.

Protocol: the parent sends "<n>\\n" on the child's stdin, the child replies
"ok\\n" or "err <message>\\n" on a private fd once the heatmaps are in the
output block. The child exits when stdin closes, including on parent death.
"""
import os
import select
import subprocess
import sys
from pathlib import Path

MAX_WINDOWS = 8
IN_SHAPE = (MAX_WINDOWS, 9, 288, 512)
OUT_SHAPE = (MAX_WINDOWS, 3, 288, 512)
START_TIMEOUT = 180.0  # first Core ML load can compile the model
PREDICT_TIMEOUT = 120.0


def _reply(stream, timeout):
    """Read one reply line from the child, bounded by `timeout` seconds."""
    fd = stream.fileno()
    data = b''
    while not data.endswith(b'\n'):
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            raise TimeoutError('Core ML 子进程无响应')
        chunk = os.read(fd, 4096)
        if not chunk:
            raise RuntimeError('Core ML 子进程意外退出')
        data += chunk
    return data.decode('utf-8', 'replace').strip()


class ProcessCoreMLBackend:
    """Same results as backends.CoreMLBackend, without holding our GIL."""

    def __init__(self, path):
        import numpy as np
        from multiprocessing import shared_memory
        self.name = 'coreml'
        self.process = None
        self._inputs = shared_memory.SharedMemory(create=True, size=int(np.prod(IN_SHAPE)))
        self._outputs = shared_memory.SharedMemory(create=True, size=int(np.prod(OUT_SHAPE)) * 4)
        self.inputs = np.ndarray(IN_SHAPE, dtype=np.uint8, buffer=self._inputs.buf)
        self.outputs = np.ndarray(OUT_SHAPE, dtype=np.float32, buffer=self._outputs.buf)
        try:
            read_fd, write_fd = os.pipe()
            try:
                self.process = subprocess.Popen(
                    [sys.executable, '-I', str(Path(__file__).resolve()), 'serve', str(path),
                     self._inputs.name, self._outputs.name, str(write_fd)],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, pass_fds=(write_fd,))
            finally:
                os.close(write_fd)
            self.replies = os.fdopen(read_fd, 'rb', buffering=0)
            status = _reply(self.replies, START_TIMEOUT)
            if status != 'ready':
                raise RuntimeError(f'Core ML 子进程启动失败：{status}')
        except BaseException:
            self.close()
            raise

    def predict_windows(self, windows):
        """windows: n x 3 frames of (uint8 CHW RGB, transform); returns n x 3 heatmaps."""
        n = len(windows)
        if not 1 <= n <= MAX_WINDOWS or any(len(window) != 3 for window in windows):
            raise ValueError('expected 1-8 windows of exactly 3 real frames')
        for index, window in enumerate(windows):
            for frame, pair in enumerate(window):
                if pair[0].shape != (3, 288, 512) or pair[0].dtype != self.inputs.dtype:
                    raise ValueError('inconsistent frame dtype or dimensions')
                self.inputs[index, frame * 3:(frame + 1) * 3] = pair[0]
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError('Core ML 子进程已退出')
        self.process.stdin.write(f'{n}\n'.encode())
        self.process.stdin.flush()
        status = _reply(self.replies, PREDICT_TIMEOUT)
        if status != 'ok':
            raise RuntimeError(f'Core ML 推理失败：{status}')
        return self.outputs[:n].copy()  # the block is reused by the next batch

    def close(self):
        process, self.process = self.process, None
        if process is not None:
            try:
                process.stdin.close()
                process.wait(timeout=5)
            except Exception:
                process.kill()
                process.wait()
        if getattr(self, 'replies', None) is not None:
            self.replies.close()
            self.replies = None
        for block in (getattr(self, '_inputs', None), getattr(self, '_outputs', None)):
            if block is None:
                continue
            try:
                block.close()
                block.unlink()
            except Exception:
                pass
        self._inputs = self._outputs = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def serve(path, input_name, output_name, reply_fd):
    import numpy as np
    from multiprocessing import resource_tracker, shared_memory
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    replies = os.fdopen(int(reply_fd), 'wb', buffering=0)
    # The parent owns and unlinks the blocks; attaching must not register them
    # with a tracker that would unlink them when this child exits.
    resource_tracker.register = lambda *args, **kwargs: None
    try:
        from backends import CoreMLBackend
        from pretrained import normalize_input
        inputs_block = shared_memory.SharedMemory(name=input_name)
        outputs_block = shared_memory.SharedMemory(name=output_name)
        inputs = np.ndarray(IN_SHAPE, dtype=np.uint8, buffer=inputs_block.buf)
        outputs = np.ndarray(OUT_SHAPE, dtype=np.float32, buffer=outputs_block.buf)
        backend = CoreMLBackend(path)
    except BaseException as error:
        replies.write(f'{type(error).__name__}: {error}'.replace('\n', ' ').encode() + b'\n')
        return 1
    replies.write(b'ready\n')
    for line in sys.stdin.buffer:
        try:
            n = int(line)
            if not 1 <= n <= MAX_WINDOWS:
                raise ValueError(f'bad window count {n}')
            heatmaps = backend.predict(normalize_input(inputs[:n].astype(np.float32)))
            if heatmaps.shape != (n, 3, 288, 512):
                raise ValueError(f'unexpected heatmap shape {heatmaps.shape}')
            outputs[:n] = heatmaps
            replies.write(b'ok\n')
        except Exception as error:
            replies.write(f'err {type(error).__name__}: {error}'.replace('\n', ' ').encode() + b'\n')
    return 0


if __name__ == '__main__':
    if len(sys.argv) == 6 and sys.argv[1] == 'serve':
        sys.exit(serve(*sys.argv[2:]))
    raise SystemExit('internal helper: started by ProcessCoreMLBackend')
