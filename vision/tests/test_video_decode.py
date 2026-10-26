from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch,Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_decode import open_capture,VideoToolboxCapture


class VideoDecodeTests(unittest.TestCase):
    def test_default_has_no_pyav_or_hardware_requirement(self):
        import cv2
        state={}
        with patch.dict(sys.modules,{'av':None}),patch.object(cv2,'VideoCapture',return_value='opencv'):
            self.assertEqual(open_capture('video.mp4','opencv',state),'opencv')
        self.assertEqual(state,{'decoder':'opencv','hardware_decode':False})
        with self.assertRaises(ValueError):open_capture('video.mp4','unknown',state)

    def test_platform_and_missing_dependency_fail_explicitly(self):
        with patch('video_decode.sys.platform','linux'):
            with self.assertRaisesRegex(ValueError,'requires macOS'):VideoToolboxCapture('source',{})
        with patch('video_decode.sys.platform','darwin'),patch.dict(sys.modules,{'av':None}):
            with self.assertRaisesRegex(ValueError,'Optional decoder missing'):VideoToolboxCapture('source',{})

    def fake(self,hardware=True,pts=2,rotation=0):
        frame=SimpleNamespace(pts=pts,time_base=Fraction(1,30),rotation=rotation,format=SimpleNamespace(name='p010le'),to_ndarray=lambda **_:b'pixels')
        stream=SimpleNamespace(start_time=0,codec_context=SimpleNamespace(is_hwaccel=hardware))
        container=SimpleNamespace(streams=SimpleNamespace(video=[stream]),decode=lambda _:iter([frame]),close=Mock())
        opened=Mock(return_value=container);accelerator=Mock(return_value='hardware-config')
        modules={'av':SimpleNamespace(open=opened),'av.codec':SimpleNamespace(),
                 'av.codec.hwaccel':SimpleNamespace(HWAccel=accelerator)}
        return container,opened,accelerator,modules

    def test_real_pts_and_explicit_hardware_flag(self):
        import cv2
        container,opened,accel,modules=self.fake()
        state={}
        with patch('video_decode.sys.platform','darwin'),patch.dict(sys.modules,modules):
            capture=VideoToolboxCapture('source',state)
            self.assertTrue(capture.grab())
            self.assertAlmostEqual(capture.get(cv2.CAP_PROP_POS_MSEC),2/30*1000)
            self.assertEqual(capture.retrieve(),(True,b'pixels'))
            self.assertFalse(capture.grab());capture.release()
        accel.assert_called_once_with('videotoolbox',allow_software_fallback=False)
        self.assertEqual(state,{'hardware_decode':True,'decode_format':'p010le'})
        container.close.assert_called_once()

    def test_silent_software_missing_pts_and_rotation_are_rejected(self):
        for options,reason in (({'hardware':False},'not active'),({'pts':None},'source PTS'),({'rotation':90},'Rotated')):
            container,opened,accel,modules=self.fake(**options)
            with patch('video_decode.sys.platform','darwin'),patch.dict(sys.modules,modules):
                capture=VideoToolboxCapture('source',{})
                try:
                    with self.assertRaisesRegex(ValueError,reason):capture.grab()
                finally:capture.release()
            container.close.assert_called_once()


if __name__=='__main__':unittest.main()
