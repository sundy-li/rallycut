"""Side-view transit episodes: candidate boundaries, never net/out adjudication."""
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation import Interval,evaluate
from rally_activity import activity_intervals
from rally_state import BallValidity,resegment
from rally_transits import episodes
from visual import Track

# Shaped like a real side-view rim (wide, thin) in normalized video coords.
BOUNDS=[.17,.38,.84,.50]
WIDTH=BOUNDS[2]-BOUNDS[0];HEIGHT=BOUNDS[3]-BOUNDS[1]
STEP=1/30


def pixel(u,h):
    """Table units (u: 0 left end .. 1 right end, h: heights above top) to px."""
    return (BOUNDS[0]+u*WIDTH)*960,(BOUNDS[1]-h*HEIGHT)*540


def flight(start,u0,u1,seconds,apex):
    out=[];n=round(seconds/STEP)
    for i in range(n+1):
        f=i/n;x,y=pixel(u0+(u1-u0)*f,apex*4*f*(1-f))
        out.append((start+i*STEP,x,y,.95))
    return out


def toss(start,u=-.05):
    out=[];n=round(.6/STEP)
    for i in range(n+1):
        f=i/n;x,y=pixel(u,1.2*4*f*(1-f))
        out.append((start+i*STEP,x,y,.95))
    return out


def rally(start,strokes,seconds=.5,apex=.5,u=0):
    """Reciprocal fast low strokes from end `u`; returns (points, end time)."""
    out=[];t=start
    for _ in range(strokes):
        out+=flight(t,u,1-u,seconds,apex);t+=seconds+STEP;u=1-u
    return out,t-STEP


def segments(end=30,method='side-color-rim',bounds=BOUNDS):
    return [{'start':0,'end':end,'bounds':bounds,'method':method}]


class TransitEpisodeTests(unittest.TestCase):
    def test_slow_return_between_points_separates_two_rallies(self):
        first,end1=rally(1.7,6)
        # Pickup + slow high return lob to the server; not play.
        returned=flight(end1+1.5,1.1,-.1,1.6,2.6)
        second,end2=rally(end1+5.7,4)
        tracks=[Track(1,toss(1)+first),Track(2,returned),Track(3,toss(end1+5)+second)]
        found=episodes(tracks,BOUNDS,0,30)
        self.assertEqual(len(found),2,found)
        (a,b,r1,_),(c,d,r2,_)=found
        self.assertAlmostEqual(a,1.7-1.3,places=3)         # preparation lead before the toss
        self.assertAlmostEqual(b,end1+.5,places=3)
        self.assertLess(b,end1+1.5)                         # stops before the return lob
        self.assertAlmostEqual(c,end1+5.7-1.3,places=3)
        self.assertEqual((r1,r2),('transit_gap','transit_gap'))

    def test_far_player_out_of_frame_keeps_one_rally_but_next_point_splits(self):
        # The ball leaves the frame towards the far player and is unseen ~1 s
        # until their return comes back across the table.
        head,t=rally(1,4)                                   # ends at the left end
        tail,end=rally(t+1.05,3)
        found=episodes([Track(1,head+tail)],BOUNDS,0,30)
        self.assertEqual(len(found),1,found)
        # Same picture but the server catches it and serves 2 s later.
        tail,_=rally(t+2.0,3)
        self.assertEqual(len(episodes([Track(1,head+tail)],BOUNDS,0,30)),2)

    def test_high_paddle_return_cannot_open_but_can_continue(self):
        # Gentle paddle return to the server: strong-looking, but high + slow.
        returned=flight(1,1,0,.85,1.3)
        self.assertEqual(episodes([Track(1,returned)],BOUNDS,0,10),[])
        head,t=rally(1,4)
        lifted=flight(t+.2,0,1,.85,1.3)
        tail,end=rally(t+1.1,3,u=1)
        found=episodes([Track(1,head+lifted+tail)],BOUNDS,0,30)
        self.assertEqual(len(found),1,found)
        self.assertGreater(found[0][1],end)

    def test_early_toss_wins_over_fixed_lead(self):
        early=toss(1)                                       # toss 2.2 s before the serve
        serve,_=rally(3.2,4)
        found=episodes([Track(1,early+serve)],BOUNDS,0,30)
        self.assertAlmostEqual(found[0][0],1-.2,places=3)
        self.assertAlmostEqual(found[0][3],3.2,places=3)    # first transit = evidence time

    def test_single_high_transit_is_a_return_not_a_serve_fault(self):
        # Ball picked up and sent back across to the server: strong, one-way,
        # but higher than any serve; a low lone transit stays a serve fault.
        self.assertEqual(episodes([Track(1,flight(1,0,.9,.5,.95))],BOUNDS,0,10),[])
        self.assertEqual(len(episodes([Track(1,flight(1,0,.9,.5,.45))],BOUNDS,0,10)),1)
        head,_=rally(1,1,apex=.95)
        tail,_=rally(1.53,3,u=1)
        self.assertEqual(len(episodes([Track(1,head+tail)],BOUNDS,0,10)),1)  # reciprocal: kept

    def test_slow_low_serve_that_is_not_returned_is_kept(self):
        # ~1.0 table widths/s, low: an unreturned slow serve (0041 20:54).
        slow=flight(2,.05,.85,.8,.4)
        found=episodes([Track(1,slow)],BOUNDS,0,10)
        self.assertEqual(len(found),1,found)
        # Slower still (0.8 widths/s) is not enough evidence to open a rally.
        self.assertEqual(episodes([Track(1,flight(2,.05,.85,1.0,.4))],BOUNDS,0,10),[])

    def test_fast_ball_on_the_floor_cannot_open_a_rally(self):
        # Fast but never above the lower half of the table band: rolling on
        # the floor / under the table beyond the end.
        floor=flight(2,1.2,.8,.2,0)
        floor=[(t,x,y+.9*HEIGHT*540,s) for t,x,y,s in floor]
        self.assertEqual(episodes([Track(1,floor)],BOUNDS,0,10),[])

    def test_toss_tail_glued_to_the_serve_does_not_make_it_a_return(self):
        # Two sparse toss points (3.0, then 1.0 table heights) right before a
        # low serve, inside one tracker run.
        x,_=pixel(-.15,0)
        head=[(1.85,x,pixel(-.15,3.0)[1],.9),(1.97,x+.005*960,pixel(-.14,1.0)[1],.9)]
        serve=flight(2.07,-.1,1.1,.75,.4)
        found=episodes([Track(1,head+serve)],BOUNDS,0,10)
        self.assertEqual(len(found),1,found)

    def test_tracker_hop_between_still_balls_is_not_a_transit(self):
        # Shared run layer: a held ball and a ball at rest across the table,
        # linked by the tracker, must not look like a fast cross-table stroke.
        from rally_transits import ball_runs
        hold=lambda t,x,n:[(t+i/30,x,.4) for i in range(n)]
        hops=hold(1,.25,4)+hold(1.14,.7,3)+hold(1.24,.25,3)+hold(1.34,.7,4)
        self.assertEqual([r for r in ball_runs(hops) if abs(r[-1][1]-r[0][1])>.1],[])
        moving=[(1+i/30,.2+.02*i,.4) for i in range(25)]
        self.assertEqual(len(ball_runs(moving)),1)

    def test_lob_defence_inside_rally_is_not_split(self):
        head,t=rally(1,4)
        lob=flight(t+.2,0,1,1.3,1.9)                        # weak transit: high and slow
        tail,end=rally(t+1.7,4)
        found=episodes([Track(1,head+lob+tail)],BOUNDS,0,30)
        self.assertEqual(len(found),1,found)
        self.assertGreater(found[0][1],end)

    def test_serve_fault_kept_and_return_only_is_not_a_rally(self):
        fault=flight(2.7,0,1,.5,.5)                         # one strong transit, then nothing
        found=episodes([Track(1,toss(2)+fault)],BOUNDS,0,10)
        self.assertEqual(len(found),1,found)
        self.assertLess(found[0][1]-found[0][0],2.5)
        for slow in (flight(1,1,0,1.8,1.0),flight(1,1,0,.9,2.6),toss(1)):
            self.assertEqual(episodes([Track(1,slow)],BOUNDS,0,10),[])

    def test_neighbouring_table_motion_outside_corridor_is_ignored(self):
        # Same play pattern, but well above this table's playing corridor.
        out=[(t,x+960*WIDTH*.5,y-540*HEIGHT*4,c) for t,x,y,c in rally(1,6)[0]]
        self.assertEqual(episodes([Track(1,out)],BOUNDS,0,10),[])

    def test_open_episode_at_horizon_has_no_end_reason(self):
        points,end=rally(1,6)
        found=episodes([Track(1,points)],BOUNDS,0,end+.3)
        self.assertEqual(found[-1][2],'')

    def test_only_trusted_wide_side_geometry_enables_rule(self):
        points,_=rally(1,6)
        tracks=[Track(1,points)]
        for segs in (segments(bounds=[.2,.4,.8,.6]),segments(bounds=[]),segments(method='unavailable')):
            self.assertEqual(activity_intervals(tracks,segs,30),[(0,30,None,None)])
        self.assertEqual(activity_intervals(tracks,segments(),30)[0][2],'live_ball_evidence')


class ResegmentTransitTests(unittest.TestCase):
    def test_resegment_splits_at_transit_gap_and_keeps_no_net_claim(self):
        first,end1=rally(1.7,6)
        returned=flight(end1+1.5,1.1,-.1,1.6,2.6)
        second,_=rally(end1+5.7,4)
        tracks=[Track(1,toss(1)+first),Track(2,returned),Track(3,toss(end1+5)+second)]
        validity=BallValidity()
        out=resegment(tracks,[i*.1 for i in range(300)],30,validity,geometry_segments=segments(),track_size=(960,540))
        self.assertEqual(len(out),2,out)
        self.assertTrue(all(r['boundary_before'] and r['start_reason']=='live_ball_evidence' for r in out))
        self.assertEqual(out[0]['end_reason'],'transit_gap')
        self.assertLess(out[0]['end'],end1+1.5)
        self.assertFalse(any('net' in r.get('end_reason','') or 'out' in r.get('end_reason','') for r in out))
        self.assertEqual(validity.events,[])

    def test_dead_ball_inside_serve_lead_leaves_no_fragment(self):
        # A (misread) dead ball between the preparation lead and the first
        # transit must not leave the lead as a sub-second rally of its own.
        points,_=rally(3,6)
        dead=type('V',(),{'events':[],'dead_intervals':[{'start':2.2,'end':2.6,'event':{'type':'dead_ball','reason':'held_after_flight','time':2.2,'confidence':.8}}],
                          'finish':lambda self,d:self.dead_intervals})()
        out=resegment([Track(1,toss(1.6)+points)],[],30,dead,geometry_segments=segments(),track_size=(960,540))
        self.assertEqual(len(out),1,out)
        self.assertGreaterEqual(out[0]['start'],2.6-1.6)
        self.assertGreater(out[0]["end"],6.5)

    def test_camera_cut_and_missing_geometry_after_cut_fail_open(self):
        first,_=rally(1.7,4)
        later,_=rally(12,4)
        segs=[{'start':0,'end':10,'bounds':BOUNDS,'method':'side-color-rim'},
              {'start':10,'end':20,'bounds':[],'method':'unavailable'}]
        out=resegment([Track(1,toss(1)+first),Track(2,later)],[],20,BallValidity(),cuts=[10],
                      geometry_segments=segs,track_size=(960,540))
        self.assertEqual(len(out),2,out)
        self.assertTrue(out[0]['end']<=10<=out[1]['start'])
        self.assertEqual(out[1]['start_reason'],'camera_cut')


@unittest.skipUnless(os.getenv('RALLYCUT_SIDE_TRANSIT_AB_DIR'),'explicit private-video fresh A/B artifacts')
class PrivateSideTransitAB(unittest.TestCase):
    """{tag}-baseline.json / {tag}-new.json: headless --include-tracks, same backend;
    {tag}-truth.json: manual rallies with `horizon` seconds of coverage."""

    def load(self,tag):
        root=Path(os.environ['RALLYCUT_SIDE_TRANSIT_AB_DIR'])
        before,after,truth=(json.loads((root/f'{tag}-{name}.json').read_text()) for name in ('baseline','new','truth'))
        # Same model input unless shot detection changed: a different cut set
        # shifts the non-overlapping three-frame window phase after the cut.
        cuts=lambda d:[s['start'] for s in d['summary']['table_segments'] if s['method']=='unavailable' and s['start']>0]
        if cuts(before)==cuts(after):
            self.assertEqual(before['tracks'],after['tracks'])
            self.assertEqual(before['summary']['rally_events'],after['summary']['rally_events'])
        horizon=truth['horizon']
        pick=lambda rows:[Interval(str(i),r['start'],r['end']) for i,r in enumerate(rows) if r['start']<horizon]
        return pick(truth['rallies']),pick(before['segments']),pick(after['segments']),after['segments']

    def test_side_view_points_are_not_merged_and_do_not_regress(self):
        for tag in ('0041','0043'):
            truth,before,after,_=self.load(tag)
            old,new=evaluate(truth,before,.5,1.0),evaluate(truth,after,.5,1.0)
            self.assertEqual(new['merges'],[],tag)
            self.assertGreaterEqual(new['tp'],old['tp'],tag)
            self.assertLessEqual(new['fp'],old['fp'],tag)
            self.assertGreaterEqual(new['boundary_accuracy'],old['boundary_accuracy'],tag)

    def test_0043_reported_hard_cases_keep_geometric_ends(self):
        _,_,_,rows=self.load('0043')
        out=[r for r in rows if r['start']<17<r['end']]
        self.assertEqual(len(out),1);self.assertLess(out[0]['end'],18.2)
        self.assertEqual(out[0]['end_reason'],'out_without_table_bounce')
        self.assertFalse(any(r['start']<34 and r['end']>35.5 for r in rows))


if __name__=='__main__':unittest.main()
