"""Full-frame contract tests use explicit fake heatmaps, not accuracy evidence."""
from pathlib import Path
import sys
import unittest
from unittest import mock
import numpy as np
import cv2

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import neural_analysis
from rally_state import BallValidity
from test_table_locator import item


class Capture:
    def __init__(self,cut=None):self.index=-1;self.closed=False;self.cut=cut
    def isOpened(self):return True
    def grab(self):self.index+=1;return self.index<48
    def retrieve(self):
        base=30+self.index if self.cut is None or self.index<self.cut else 180+self.index-self.cut
        frame=np.full((180,320,3),base,dtype='uint8');frame[0,0]=self.index
        return True,frame
    def get(self,*_):return self.index*100
    def release(self):self.closed=True


class Detector:
    device='cpu';sha256='unit-test'
    windows=[]
    def __init__(self,**_):pass
    def prepare_frame(self,frame,roi=None):return np.full((3,2,2),int(frame[0,0,0])),None
    def predict_heatmaps(self,batch):
        result=[]
        for window in batch:
            indexes=[int(pair[0][0,0,0]) for pair in window];self.windows.append(indexes)
            result.append([[(.15+index*.005,.85,.95)] for index in indexes])
        return result
    def postprocess(self,_,heatmaps):return heatmaps


class FullFrameTests(unittest.TestCase):
    def run_mode(self,mode='optional',geometry=False,cut=None,pipeline=True,recorder=None):
        cap=Capture(cut);Detector.windows=[];seen=[]
        result=None
        with mock.patch.object(neural_analysis,'BlurBallDetector',Detector),mock.patch.object(cv2,'VideoCapture',return_value=cap),\
             mock.patch('table_locator.calibrate',side_effect=ValueError('no table')) as prepass,\
             mock.patch('table_locator.candidates',return_value=[item((200,200,800,270))] if geometry else []):
            result=neural_analysis.analyze('unit-only',4.8,lambda *_:None,table_mode=mode,pipeline=pipeline,
                frame_callback=lambda r,raw,tracked:seen.append((r['t'],raw,tracked)),l0_recorder=recorder)
        self.assertTrue(cap.closed)
        self.assertEqual(prepass.call_count,1 if mode=='precalibrate' else 0)
        return result,seen,list(Detector.windows)

    def test_no_table_still_detects_tracks_and_rallies_without_fake_events(self):
        for mode in ('optional','off','precalibrate'):
            with self.subTest(mode=mode):
                result,seen,_=self.run_mode(mode)
                self.assertEqual(len(seen),48)
                self.assertTrue(result['tracks']);self.assertTrue(result['rallies'])
                self.assertEqual(result['summary']['table_bounds'],[])
                self.assertFalse(result['summary']['geometry_available'])
                self.assertEqual(result['summary']['rally_events'],[])
                self.assertFalse(any(r.get('end_reason') for r in result['rallies']))

    def test_l0_cache_replay_reproduces_the_fresh_result(self):
        # The cache is only evidence if replaying it equals the fresh run.
        import tempfile
        import detection_cache
        for mode,geometry,cut in (('optional',True,None),('off',False,22),('optional',False,None)):
            with self.subTest(mode=mode,geometry=geometry,cut=cut):
                recorder=detection_cache.Recorder()
                result,seen,_=self.run_mode(mode,geometry=geometry,cut=cut,recorder=recorder)
                with tempfile.TemporaryDirectory() as directory:
                    path=recorder.save(Path(directory)/'l0.json.gz')
                    document=detection_cache.load(path)
                self.assertIsNone(detection_cache.stale_reason(document))
                self.assertEqual(len(document['frames']['t']),len(seen))
                replayed=detection_cache.replay(document)
                self.assertTrue(result['rallies'])
                self.assertEqual(replayed['rallies'],result['rallies'])
                self.assertEqual(replayed['tracks'],result['tracks'])
                self.assertEqual(replayed['summary']['rally_events'],result['summary']['rally_events'])
                self.assertEqual(replayed['summary']['table_segments'],result['summary']['table_segments'])
                # A changed L0 source makes the cache stale, never silently replayed.
                with mock.patch.object(detection_cache,'source_digest',return_value='changed'):
                    self.assertIsNotNone(detection_cache.stale_reason(document))

    def test_optional_geometry_never_discards_model_points_outside_table(self):
        result,seen,_=self.run_mode(geometry=True)
        self.assertTrue(result['summary']['geometry_available'])
        self.assertTrue(result['tracks'])
        self.assertTrue(all(len(raw)==len(tracked)==1 for _,raw,tracked in seen))
        self.assertTrue(all(abs(points[0][1]/540-.85)<1e-9 for _,_,points in seen))
        self.assertEqual(result['summary']['rally_events'],[])

    def test_cut_breaks_tracks_windows_and_audio_merges_in_both_pipeline_modes(self):
        for pipeline in (False,True):
            result,seen,windows=self.run_mode('off',cut=22,pipeline=pipeline)
            self.assertEqual(result['summary']['camera_cuts'],1)
            self.assertTrue(all(all(i<22 for i in window) or all(i>=22 for i in window) for window in windows))
            self.assertEqual(result['summary']['unscored_frames'],3)
            self.assertFalse(any(track['points'][0]['t']<2.2<=track['points'][-1]['t'] for track in result['tracks']))
            self.assertFalse(any(r['start']<2.2<r['end'] for r in result['rallies']))
            self.assertTrue(any(r.get('boundary_before') for r in result['rallies']))
            self.assertEqual(result['summary']['rally_events'],[])

    def test_missing_geometry_is_not_a_full_frame_table(self):
        state=BallValidity()
        for i in range(60):state.observe(i*.04,[(.1+i*.01,.55,.95)])
        self.assertIsNone(state.width)
        self.assertEqual(state.finish(3),[])
        state.rebind([.1,.3,.9,.5],geometry_method='side-color-rim')
        self.assertIsNotNone(state.width)
        state.rebind(timestamp=3)
        self.assertIsNone(state.width);self.assertEqual(state.state,'IN_PLAY')


if __name__=='__main__':unittest.main()
