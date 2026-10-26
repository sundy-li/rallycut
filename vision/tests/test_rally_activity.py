"""Activity boundaries are evidence candidates, never fabricated net faults."""
import json
import math
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rally_activity import activity_intervals
from rally_state import BallValidity,resegment
from visual import Track

BOUNDS=[.2,.4,.8,.6]


def points(start,end,fn):
    out=[]
    for i in range(round((end-start)/.03)+1):
        t=start+i*.03;x,y=fn(t-start)
        out.append((t,x*960,y*540,.95))
    return out


def toss(start):return points(start,start+.6,lambda t:(.25,.50-.20*math.sin(math.pi*t/.6)))
def play(start,end):return points(start,end,lambda t:(.5-.27*math.cos(2*math.pi*t/.8),.46+.02*math.sin(t*6)))


class ActivityTests(unittest.TestCase):
    def segments(self,duration=10):return [{'start':0,'end':duration,'bounds':BOUNDS,'method':'perspective-rims'}]

    def test_preparation_and_one_way_returns_do_not_start_play(self):
        prep=points(0,2,lambda t:(.25+.008*math.sin(t*8),.46+.015*math.sin(t*12)))
        returned=points(3,3.8,lambda t:(.75-.5*t/.8,.47))
        self.assertEqual(activity_intervals([Track(1,prep),Track(2,returned)],self.segments(),10),[])

    def test_serve_play_settle_return_and_new_serve_are_separate(self):
        stream=toss(0)+play(.63,3.3)+points(3.33,4.5,lambda t:(.5+.005*math.sin(t),.49))
        stream+=points(5,5.8,lambda t:(.75-.5*t/.8,.47))+toss(6)+play(6.63,9)
        tracks=[Track(1,stream)]
        intervals=activity_intervals(tracks,self.segments(),10)
        self.assertEqual(len(intervals),2,intervals)
        # End at the observed confirmation, not the beginning of the slow
        # window; still stop before the separate return toss at 5 seconds.
        self.assertGreater(intervals[0][1],3.8)
        self.assertLess(intervals[0][1],4.5)
        self.assertGreaterEqual(intervals[1][0],5.8)
        rallies=resegment(tracks,[i*.1 for i in range(100)],10,BallValidity(),geometry_segments=self.segments())
        self.assertEqual(len(rallies),2,rallies)
        self.assertTrue(rallies[1]['boundary_before'])
        self.assertEqual(rallies[0]['end_reason'],'ball_settled')

    def test_normal_reciprocal_play_and_high_lob_are_not_cut(self):
        stream=toss(0)+points(.63,8,lambda t:(.5-.27*math.cos(2*math.pi*t/.8),.25 if 2<t<2.6 else .46))
        result=activity_intervals([Track(1,stream)],self.segments(),10)
        self.assertEqual(len(result),1,result)
        self.assertGreater(result[0][1],7.9)

    def test_local_fast_recovery_before_full_transit_cancels_pending_stop(self):
        stream=toss(0)+play(.63,2.01)
        stream+=points(2.04,2.64,lambda t:(.55,.48))
        stream+=points(2.67,2.97,lambda t:(.55+.7*t,.48))
        stream+=play(3,6)
        for offset in (0,100):
            shifted=[(t+offset,x,y,c) for t,x,y,c in stream]
            result=activity_intervals([Track(1,shifted)],self.segments(offset+8),offset+8)
            self.assertEqual(len(result),1,result)
            self.assertGreater(result[0][1],offset+5.9)

    def test_one_position_spike_is_not_sustained_recovery(self):
        base=toss(0)+play(.63,2.01)+points(2.04,4,lambda t:(.55,.48))
        noisy=[(t,x+(.2*960 if abs(t-2.85)<.001 else 0),y,c) for t,x,y,c in base]
        result=activity_intervals([Track(1,noisy)],self.segments(5),5)
        self.assertEqual(len(result),1,result)
        self.assertEqual(result[0][3],'ball_settled')
        self.assertLess(result[0][1],3.4)

    def test_no_geometry_side_view_and_geometry_acquisition_fail_open(self):
        for segments in ([{'start':0,'end':10,'bounds':[],'method':'unavailable'}],
                         [{'start':0,'end':2,'bounds':[]},{'start':2,'end':10,'bounds':BOUNDS,'method':'side-color-rim'}]):
            self.assertEqual(activity_intervals([],segments,10),[(0,10,None,None)])

    def test_failed_serve_is_preserved_without_invented_net_event(self):
        tracks=[Track(1,toss(1))]
        validity=BallValidity()
        rallies=resegment(tracks,[],10,validity,geometry_segments=self.segments())
        self.assertEqual(len(rallies),1,rallies)
        self.assertLess(rallies[0]['end']-rallies[0]['start'],1)
        self.assertEqual(validity.events,[])
        self.assertNotIn('net',rallies[0]['end_reason'])

    @unittest.skipUnless(os.getenv('RALLYCUT_FEEDBACK_AB_DIR'),'explicit private-video fresh A/B artifacts')
    def test_user_feedback_first_segment_fresh_ab(self):
        root=Path(os.environ['RALLYCUT_FEEDBACK_AB_DIR'])
        before=json.loads((root/'baseline.json').read_text());after=json.loads((root/'corrected.json').read_text())
        self.assertEqual((root/'baseline-predictions.jsonl').read_text(),(root/'corrected-predictions.jsonl').read_text())
        self.assertEqual(before['tracks'],after['tracks'])
        rows=after['rallies']
        self.assertFalse(any(r['start']<16 and r['end']>10 for r in rows))
        for boundary in (29.5,50.5,57,83):
            self.assertFalse(any(r['start']<boundary-.5 and r['end']>boundary+1 for r in rows),(boundary,rows))
        self.assertTrue(any(68<r['start']<70 and 70<r['end']<72 for r in rows))
        self.assertFalse(after['summary']['rally_events'])


    @unittest.skipUnless(os.getenv('RALLYCUT_END_EARLY_AB_DIR'),'explicit private-video end-early fresh A/B')
    def test_end_early_feedback_and_invalid_prefix_fresh_ab(self):
        root=Path(os.environ['RALLYCUT_END_EARLY_AB_DIR'])
        before=json.loads((root/'baseline.json').read_text());after=json.loads((root/'corrected.json').read_text())
        self.assertEqual((root/'baseline-predictions.jsonl').read_bytes(),(root/'corrected-predictions.jsonl').read_bytes())
        self.assertEqual(before['tracks'],after['tracks'])
        rows=after['rallies']
        self.assertFalse(any(r['start']<4 for r in rows))
        for inside,minimum_end,maximum_end in ((151,154.3,156),(160,163.2,166),(169,171.6,173),(183,188,190)):
            target=[r for r in rows if r['start']<inside<r['end']]
            self.assertEqual(len(target),1,(inside,target))
            self.assertGreater(target[0]['end'],minimum_end)
            self.assertLess(target[0]['end'],maximum_end)
        # The ongoing fourth rally must not be split again at 185 seconds.
        self.assertTrue(any(r['start']<183 and r['end']>187.9 for r in rows))
        self.assertFalse(any('net' in r.get('end_reason','') for r in rows))
        self.assertFalse(any(r['start']<16 and r['end']>10 for r in rows))
        for boundary in (29.5,50.5,57,83):
            self.assertFalse(any(r['start']<boundary-.5 and r['end']>boundary+1 for r in rows),(boundary,rows))
        self.assertTrue(any(68<r['start']<70 and 70<r['end']<72 for r in rows))


if __name__=='__main__':unittest.main()
