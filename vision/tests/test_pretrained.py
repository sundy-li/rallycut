import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pretrained import BlurBallDetector, MODEL, WEIGHTS_SHA256
from evaluate_points import evaluate


class PretrainedAdapterTests(unittest.TestCase):
    def test_rgb_normalization_and_letterbox(self):
        frame=np.zeros((100,400,3),dtype='uint8')
        frame[:,:,2]=255  # BGR red -> RGB channel 0
        tensor,transform=BlurBallDetector.preprocess(frame)
        self.assertEqual(tensor.shape,(3,288,512))
        self.assertAlmostEqual(float(tensor[0,144,256]),(1-.485)/.229,places=5)
        self.assertAlmostEqual(float(tensor[2,144,256]),(0-.406)/.225,places=5)
        self.assertAlmostEqual(transform[0],1.28)
        self.assertAlmostEqual(transform[2],80)

    @unittest.skipUnless(importlib.util.find_spec('torch'),'torch optional outside model installation')
    def test_uint8_batch_normalization_matches_legacy_fp32_exactly(self):
        import torch
        detector=BlurBallDetector.__new__(BlurBallDetector)
        detector._mean=torch.tensor([.485,.456,.406]*3,dtype=torch.float32).view(1,9,1,1)
        detector._std=torch.tensor([.229,.224,.225]*3,dtype=torch.float32).view(1,9,1,1)
        image=np.random.default_rng(7).integers(0,256,size=(100,400,3),dtype='uint8')
        compact=BlurBallDetector.prepare_frame(image)
        legacy=BlurBallDetector.preprocess(image)
        self.assertEqual(compact[0].dtype,np.uint8)
        self.assertEqual(compact[0].nbytes*4,legacy[0].nbytes)
        self.assertEqual(compact[1],legacy[1])
        actual=detector.prepare_batch([[compact]*3]).numpy()
        expected=detector.prepare_batch([[legacy]*3]).numpy()
        np.testing.assert_array_equal(actual,expected)
        with self.assertRaises(ValueError):detector.prepare_batch([[compact]*2])
        with self.assertRaises(ValueError):detector.prepare_batch([])

    def test_resize_then_color_is_bit_exact_for_resolutions_and_letterboxing(self):
        import cv2
        random=np.random.default_rng(29)
        for height,width in ((1080,1920),(2160,3840),(480,640),(720,1280),(640,360),(99,403)):
            image=random.integers(0,256,(height,width,3),dtype='uint8')
            actual,transform=BlurBallDetector.prepare_frame(image)
            scale,tx,ty,_,_=transform
            matrix=np.array([[scale,0,tx],[0,scale,ty]],dtype='float32')
            legacy=cv2.warpAffine(cv2.cvtColor(image,cv2.COLOR_BGR2RGB),matrix,(512,288),flags=cv2.INTER_LINEAR)
            np.testing.assert_array_equal(actual,legacy.transpose(2,0,1))

    def test_weighted_heatmap_center_and_inverse_transform(self):
        heatmap=np.zeros((288,512),dtype='float32')
        heatmap[143:146,255:258]=.9
        points=BlurBallDetector.peaks(heatmap,(1.28,0,80,400,100),.7)
        self.assertEqual(len(points),1)
        self.assertAlmostEqual(points[0][0],.5,places=5)
        self.assertAlmostEqual(points[0][1],.5,places=5)
        self.assertEqual(BlurBallDetector.peaks(heatmap,(1.28,0,80,400,100),.95),[])
        heatmap[:]=0;heatmap[0,0]=.9  # Outside original image, in letterbox.
        self.assertEqual(BlurBallDetector.peaks(heatmap,(1.28,0,80,400,100),.7),[])

    def test_point_evaluation_counts_wrong_location_as_both_fp_and_fn(self):
        labels={'source_dimensions':[100,100],'tolerance_pixels':5,'samples':[
            {'t':0,'visibility':'visible','xy':[10,20]},
            {'t':1,'visibility':'visible','xy':[10,20]},
            {'t':2,'visibility':'not_visible_in_playing_area','xy':None},
            {'t':3,'visibility':'uncertain','xy':None}]}
        report=evaluate(labels,[{'t':0,'detections':[(.1,.2,.9)]},{'t':1,'detections':[(.9,.9,.9)]},{'t':2,'detections':[]}])
        self.assertEqual((report['tp'],report['fp'],report['fn'],report['true_negative_frames'],report['excluded_uncertain_frames']),(1,1,1,1,1))

    def test_missing_weights_returns_error_without_classical_fallback(self):
        worker=Path(__file__).resolve().parents[1]/'worker.py'
        request={'protocol_version':1,'type':'analyze','job_id':'missing-model','video_path':'never-read.mp4','duration':10,'config':{'detector':MODEL}}
        result=subprocess.run([sys.executable,worker],input=json.dumps(request)+'\n',capture_output=True,text=True,env={**os.environ,'RALLYCUT_MODEL_PATH':'/no-such-rallycut-model.pth'})
        self.assertEqual(result.returncode,1)
        events=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(events[-1]['type'],'error')
        self.assertFalse(any(event['type']=='result' for event in events))

    @unittest.skipUnless(os.getenv('RALLYCUT_RUN_MODEL_TESTS')=='1','explicit opt-in for real local weights')
    def test_safe_checkpoint_strict_load_and_finite_inference(self):
        detector=BlurBallDetector()
        self.assertEqual(detector.sha256,WEIGHTS_SHA256)
        # An absent ball must not become a synthetic trajectory.
        frame=np.zeros((1080,1920,3),dtype='uint8')
        pair=detector.preprocess(frame)
        result=detector.predict([[pair,pair,pair]])
        self.assertEqual(result,[[[],[],[]]])
        with tempfile.TemporaryDirectory() as directory:
            bad=Path(directory)/'bad.pth';bad.write_bytes(b'not weights')
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                BlurBallDetector(weights=bad)


if __name__=='__main__':
    unittest.main()
