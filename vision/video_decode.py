"""Default OpenCV capture, optional explicitly verified VideoToolbox experiment.

No nominal-FPS timestamps and no silent software fallback under a hardware label.
PyAV/FFmpeg conversion can differ from OpenCV, so this is not the default.
"""
import sys


class VideoToolboxCapture:
    def __init__(self,path,state):
        if sys.platform!='darwin':
            raise ValueError('VideoToolbox decoder requires macOS; use --decoder opencv')
        try:
            import av
            from av.codec.hwaccel import HWAccel
        except ImportError as error:
            raise ValueError('Optional decoder missing: install vision/requirements-decode.txt, or skill setup --with-decoder; use opencv otherwise') from error
        self.container=av.open(str(path),hwaccel=HWAccel('videotoolbox',allow_software_fallback=False))
        try:
            self.stream=self.container.streams.video[0]
            self.frames=iter(self.container.decode(self.stream))
            self.origin=self.stream.start_time or 0
            self.frame=None
            self.state=state
            self.checked=False
        except BaseException:
            self.container.close()
            raise

    def isOpened(self):return True

    def grab(self):
        try:self.frame=next(self.frames)
        except StopIteration:return False
        if self.frame.pts is None or self.frame.time_base is None:
            raise ValueError('Hardware decoder did not provide source PTS')
        if getattr(self.frame,'rotation',0):
            raise ValueError('Rotated VideoToolbox input is not validated; use --decoder opencv')
        if not self.checked:
            if not self.stream.codec_context.is_hwaccel:
                raise ValueError('VideoToolbox not active; refusing to label software decoding as hardware')
            self.state.update(hardware_decode=True,decode_format=self.frame.format.name)
            self.checked=True
        return True

    def retrieve(self):
        return True,self.frame.to_ndarray(format='bgr24')

    def get(self,prop):
        import cv2
        if prop!=cv2.CAP_PROP_POS_MSEC:
            raise ValueError('unsupported decoder metadata request')
        return float((self.frame.pts-self.origin)*self.frame.time_base)*1000

    def release(self):self.container.close()


def open_capture(path,decoder,state):
    import cv2
    state.update(decoder=decoder,hardware_decode=False)
    if decoder=='opencv':
        return cv2.VideoCapture(str(path),cv2.CAP_FFMPEG)
    if decoder=='auto':
        # Explicit opt-in: try hardware, verify it, otherwise fall back loudly.
        if sys.platform=='darwin':
            try:
                capture=VideoToolboxCapture(path,state)
                state.update(decoder='videotoolbox')
                return capture
            except Exception as error:
                state.update(decoder='opencv',decode_fallback=str(error))
        state.update(decoder='opencv')
        return cv2.VideoCapture(str(path),cv2.CAP_FFMPEG)
    if decoder=='videotoolbox':
        return VideoToolboxCapture(path,state)
    raise ValueError('decoder must be opencv, videotoolbox or auto')
