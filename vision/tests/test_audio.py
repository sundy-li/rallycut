from pathlib import Path
import sys
import tempfile
import unittest
import wave
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_features import impact_times, fuse_audio_visual
from visual import Track


class AudioTests(unittest.TestCase):
    def test_no_visual_evidence_means_no_audio_only_rallies(self):
        self.assertEqual(fuse_audio_visual([], [], [1, 1.3, 1.6, 1.9, 2.2], 10), [])

    def test_audio_supports_occluded_flight_but_not_unrelated_sounds(self):
        track = Track(1, [(2+i*.04, 400+i*70, 200, .8) for i in range(3)])
        result = fuse_audio_visual([], [track], [1,1.4,1.8,2.2,2.6,3,7,7.4,7.8,8.2], 10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['evidence'], 'visual+audio')
        self.assertLess(result[0]['end'], 7)

    def test_static_noise_and_slow_preparation_do_not_corroborate_audio(self):
        for offset in (0, 100):
            tracks=[Track(1,[(offset+1+i*.04,400,200,.9) for i in range(3)]),
                    Track(2,[(offset+2+i*.04,650+i,260+i,.9) for i in range(20)])]
            hits=[offset+t for t in (.5,.8,1.1,1.4,1.8,2.2,2.6)]
            self.assertEqual(fuse_audio_visual([],tracks,hits,offset+5),[])

    def test_audio_extends_already_qualified_visual_even_when_local_motion_is_small(self):
        track=Track(1,[(2+i*.05,400+i,200,.9) for i in range(20)])
        visual=[{'start':1.8,'end':3.2,'confidence':.8,'score':20,'selected':True,'edited':False}]
        result=fuse_audio_visual(visual,[track],[1.4,1.8,2.2,2.6,3,3.4],10)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['evidence'],'visual+audio')
        self.assertGreater(result[0]['end'],3.2)

    def test_silence_and_synthetic_impacts_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            def write(name, samples):
                path=Path(directory)/name
                with wave.open(str(path), 'wb') as out:
                    out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000)
                    out.writeframes((samples*32767).astype('<i2').tobytes())
                return path
            quiet=np.zeros(16000*4,dtype='float32')
            self.assertEqual(impact_times(write('quiet.wav',quiet)), [])
            rng=np.random.default_rng(42)
            for start in (16000,24000,32000):
                quiet[start:start+240]=rng.uniform(-.7,.7,240)
            hits=impact_times(write('hits.wav',quiet))
            self.assertEqual(len(hits),3)
            for hit,expected in zip(hits,(1,1.5,2)):
                self.assertLess(abs(hit-expected),.06)


if __name__=='__main__':
    unittest.main()
