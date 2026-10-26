"""Regression for blue end-on table, blue floor, startup occlusion and neighbors."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from table_locator import candidates,stable_table,iou,calibrate,sampling_schedule


def perspective_scene(surface=(125,100,75), table=True):
    frame=np.full((540,960,3),(140,80,50),dtype='uint8')  # blue floor
    frame[:200]=(110,110,110)
    cv2.rectangle(frame,(570,175),(915,225),(100,45,35),-1)  # blue rear barrier
    if table:
        points=np.array([[315,256],[493,296],[704,236],[515,216]],dtype='int32')
        cv2.fillConvexPoly(frame,points,surface)
        cv2.polylines(frame,[points],True,(225,225,225),3)
    return frame


def item(bounds,score=20000):
    return {'bounds':bounds,'score':score,'method':'unit-test'}


class CalibrationCapture:
    def __init__(self,seek_supported=True,wrong_timestamp=False):
        self.position=0.0;self.closed=False;self.seeks=[];self.seek_supported=seek_supported;self.wrong_timestamp=wrong_timestamp
        self.frames=-1
    def isOpened(self):return True
    def set(self,_,milliseconds):
        self.position=milliseconds/1000;self.seeks.append(self.position);return self.seek_supported
    def read(self):return True,np.zeros((6,10,3),dtype='uint8')
    def get(self,*_):return (self.position+(10 if self.wrong_timestamp else 0))*1000
    def grab(self):
        self.frames+=1;self.position=self.frames*.5;return self.position<=600
    def retrieve(self):return self.read()
    def release(self):self.closed=True


class TableLocatorTests(unittest.TestCase):
    def test_blue_table_perspective_detected_without_selecting_blue_floor(self):
        found=candidates(perspective_scene())
        self.assertTrue(found)
        main=found[0]['bounds']
        self.assertGreater(iou(main,(315,216,705,298)),.65)
        self.assertEqual(found[0]['method'],'perspective-rims')
        self.assertLess(main[3],330)

    def test_floor_barrier_and_nonblue_surface_are_not_whole_frame_fallback(self):
        self.assertEqual(candidates(perspective_scene(table=False)),[])
        self.assertEqual(candidates(perspective_scene(surface=(40,110,40))),[])

    def test_validated_side_view_still_detected(self):
        frame=np.full((540,960,3),65,dtype='uint8')
        cv2.rectangle(frame,(150,210),(820,265),(150,75,75),-1)
        cv2.rectangle(frame,(150,210),(820,265),(225,225,225),3)
        found=candidates(frame)
        self.assertTrue(any(candidate['method']=='side-color-rim' and
                            iou(candidate['bounds'],(150,210,820,265))>.8 for candidate in found))

    def test_temporal_vote_ignores_occlusion_and_single_neighbor_misfire(self):
        main=(315,214,706,298)
        samples=[(0,[]),(1,[item((315,215,704,298))]),(2,[]),
                 (3,[item(main),item((700,170,940,225),90000)]),
                 (4,[item((317,212,707,296))])]
        result=stable_table(samples)
        self.assertEqual(result['observations'],3)
        self.assertGreater(iou(result['bounds'],main),.95)
        self.assertIsNone(stable_table([(0,[item(main)]),(1,[item(main)])]))

    def test_ambiguous_equal_tables_are_rejected(self):
        samples=[(t,[item((70,210,400,280)),item((550,210,880,280))]) for t in (0,1,2)]
        self.assertIsNone(stable_table(samples))

    def test_short_sources_use_proportional_temporal_span(self):
        main=item((315,214,706,298))
        samples=[(t,[main]) for t in (0,.2,.4,.6)]
        self.assertIsNone(stable_table(samples))
        self.assertIsNotNone(stable_table(samples,minimum_span=.4))

    def test_neural_pass_restarts_at_source_beginning_after_calibration(self):
        import neural_analysis
        class Capture:
            def __init__(self,*_):self.index=-1;self.closed=False
            def isOpened(self):return True
            def grab(self):self.index+=1;return self.index<6
            def retrieve(self):return True,np.full((6,10,3),self.index,dtype='uint8')
            def get(self,*_):return self.index*.04*1000
            def release(self):self.closed=True
        capture=Capture()
        class Detector:
            device='cpu';sha256='unit-test'
            def __init__(self,**_):pass
            def prepare_frame(self,frame,roi=None):return np.full((3,2,2),int(frame[0,0,0])),None
            def predict_heatmaps(self,batch):return [[[] for _ in window] for window in batch]
            def postprocess(self,_,heatmaps):return heatmaps
        seen=[]
        calibration={'bounds':(315,214,706,298),'method':'unit-test','observations':3,'last_evidence':8,
                     'search_seconds':600,'sampled_frames':9,'elapsed_seconds':.2,'strategy':'seek_sparse'}
        with mock.patch.object(neural_analysis,'BlurBallDetector',Detector),mock.patch('table_locator.calibrate',return_value=calibration),mock.patch.object(cv2,'VideoCapture',return_value=capture):
            result=neural_analysis.analyze('unit-fixture',.24,lambda *_:None,table_mode='precalibrate',
                                           frame_callback=lambda frame,*_:seen.append(frame['frame_index']))
        self.assertEqual(seen,[0,1,2,3,4,5])
        self.assertEqual(result['summary']['decoded_frames'],6)
        self.assertEqual(result['summary']['calibration_samples'],3)
        self.assertTrue(capture.closed)

    def test_pipeline_keeps_vfr_pts_duplicates_and_incomplete_tail_semantics(self):
        import neural_analysis
        timestamps=[0,.04,.09,.16,.17,.23,.31,.5]
        values=[0,1,1,2,3,4,5,6]
        class Capture:
            def __init__(self):self.index=-1;self.closed=False
            def isOpened(self):return True
            def grab(self):self.index+=1;return self.index<len(values)
            def retrieve(self):return True,np.full((6,10,3),values[self.index],dtype='uint8')
            def get(self,*_):return timestamps[self.index]*1000
            def release(self):self.closed=True
        class Detector:
            device='cpu';sha256='unit-test'
            def __init__(self,**_):pass
            def prepare_frame(self,frame,roi=None):return np.full((3,2,2),int(frame[0,0,0])),None
            def predict_heatmaps(self,batch):return [[[] for _ in window] for window in batch]
            def postprocess(self,_,heatmaps):return heatmaps
        calibration={'bounds':(315,214,706,298),'method':'unit-test','observations':3,'last_evidence':0,
                     'search_seconds':.55,'sampled_frames':3,'elapsed_seconds':.2,'strategy':'seek_sparse'}
        for pipeline in (True,False):
            capture=Capture();seen=[]
            with mock.patch.object(neural_analysis,'BlurBallDetector',Detector),mock.patch('table_locator.calibrate',side_effect=AssertionError('default must not pre-calibrate')),mock.patch.object(cv2,'VideoCapture',return_value=capture):
                result=neural_analysis.analyze('unit-fixture',.55,lambda *_:None,batch_size=1,pipeline=pipeline,
                    frame_callback=lambda frame,*_:seen.append((frame['frame_index'],frame['t'])))
            self.assertEqual([index for index,_ in seen],[0,1,3,4,5,6])
            for index,timestamp in seen:self.assertAlmostEqual(timestamp,timestamps[index])
            self.assertEqual(result['summary']['decoded_frames'],8)
            self.assertEqual(result['summary']['sampled_frames'],6)
            self.assertEqual(result['summary']['duplicate_frames'],1)
            self.assertTrue(capture.closed)

    def test_600_second_schedule_is_bounded_sparse_and_reaches_end(self):
        positions=sampling_schedule(600,1500)
        self.assertEqual(len(positions),145)
        self.assertEqual(positions[:31],list(range(31)))
        self.assertEqual(positions[31:34],[35,40,45])
        self.assertEqual(positions[-1],600)
        self.assertEqual(sampling_schedule(2.2,2.2)[-1],2.2)
        for invalid in (0,-1,float('nan'),float('inf'),3601):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                sampling_schedule(invalid,1500)

    def test_sparse_search_can_calibrate_after_first_30_seconds(self):
        capture=CalibrationCapture()
        def after_opening(_):
            return [item((315,214,706,298))] if capture.position>=40 else []
        with mock.patch.object(cv2,'VideoCapture',return_value=capture),mock.patch('table_locator.candidates',side_effect=after_opening):
            found=calibrate('fixture',1500,lambda *_:None)
        self.assertEqual(found['last_evidence'],50)
        self.assertEqual(found['strategy'],'seek_sparse')
        self.assertEqual(found['search_seconds'],600)
        self.assertEqual(found['sampled_frames'],35)
        self.assertTrue(capture.closed)

    def test_sparse_search_fails_only_after_covering_full_horizon(self):
        capture=CalibrationCapture()
        with mock.patch.object(cv2,'VideoCapture',return_value=capture),mock.patch('table_locator.candidates',return_value=[]),self.assertRaisesRegex(ValueError,'前 600 秒'):
            calibrate('fixture',1500,lambda *_:None,jump_samples=0)
        self.assertEqual(len(capture.seeks),145)
        self.assertEqual(capture.seeks[-1],600)
        self.assertTrue(capture.closed)

    def test_unsupported_or_inaccurate_seek_reopens_and_falls_back(self):
        for inaccurate in (False,True):
            first=CalibrationCapture(seek_supported=inaccurate,wrong_timestamp=inaccurate)
            second=CalibrationCapture()
            logs=[]
            with self.subTest(inaccurate=inaccurate),mock.patch.object(cv2,'VideoCapture',side_effect=[first,second]),mock.patch('table_locator.candidates',return_value=[item((315,214,706,298))]):
                found=calibrate('fixture',1500,lambda _,message:logs.append(message))
            self.assertEqual(found['strategy'],'sequential_fallback')
            self.assertTrue(first.closed and second.closed)
            self.assertTrue(any('重新顺序校准' in message for message in logs))
            self.assertEqual(found['first_evidence'],0)

    @unittest.skipUnless(os.getenv('RALLYCUT_TEST_TABLE_VIDEO'),'explicit real-video regression path')
    def test_real_failure_source_calibrates_foreground_not_neighbor(self):
        result=calibrate(os.environ['RALLYCUT_TEST_TABLE_VIDEO'],1497,lambda *_:None)
        self.assertEqual(result['method'],'perspective-rims')
        self.assertGreater(result['observations'],2)
        self.assertGreater(iou(result['bounds'],(315,214,706,298)),.85)
        self.assertLess(result['bounds'][2],750)  # rear table/barrier starts around x800


if __name__=='__main__':
    unittest.main()
