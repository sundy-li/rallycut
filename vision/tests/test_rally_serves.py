"""Frame-space serve/stroke episodes for horizontal-play views without side geometry."""
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation import Interval,evaluate
from rally_activity import activity_intervals
from rally_serves import calibrate,episodes as calibrated_episodes,horizontal_view
from visual import Track

STEP=1/30
# Fixed (S, W) for single-rally fixtures (too few runs to self-calibrate):
# 0.935 frame widths/s, 0.526 frame widths.
SCALE=(.935,.526)


def episodes(tracks,lo,hi,scale=SCALE):return calibrated_episodes(tracks,lo,hi,scale=scale)


def path(start,x0,x1,seconds,y0=.55,y1=None,arc=.06):
    """Ball run in normalized frame coords -> 960x540 points."""
    y1=y0 if y1 is None else y1
    out=[];n=max(2,round(seconds/STEP))
    for i in range(n+1):
        f=i/n;x=x0+(x1-x0)*f;y=y0+(y1-y0)*f-arc*4*f*(1-f)
        out.append((start+i*STEP,x*960,y*540,.9))
    return out


def toss(start,x=.75):
    """High serve toss: the ball rises ~0.3 frame heights and drops back."""
    return path(start,x,x+.01,.5,.55,.55,arc=.3)


def rally(start,strokes,seconds=.5,x=.75):
    out=[];t=start;other=1.05-x
    for _ in range(strokes):
        out+=path(t,x,other,seconds);t+=seconds+STEP;x,other=other,x
    return out,t-STEP


class FrameServeTests(unittest.TestCase):
    def test_toss_serve_rally_then_pause_then_next_point(self):
        first,end1=rally(3.0,5)
        second,end2=rally(end1+8.6,3,x=.3)
        tracks=[Track(1,toss(2.4)+first),Track(2,toss(end1+8,x=.3)+second)]
        found=episodes(tracks,0,40)
        self.assertEqual(len(found),2,found)
        (a,b,r1,f1,p1),(c,d,r2,f2,p2)=found
        self.assertEqual((p1,p2),(False,False))      # no bounce burst seen
        self.assertAlmostEqual(a,2.4-1.2,delta=.05)   # toss start minus lead
        self.assertAlmostEqual(b,end1+.8,delta=.05)  # last stroke plus tail
        self.assertAlmostEqual(c,end1+8-1.2,delta=.05)
        self.assertEqual((r1,r2),('stroke_gap','stroke_gap'))
        self.assertAlmostEqual(f1,3.0,delta=.05)

    def test_bounce_burst_before_the_serve_starts_the_rally(self):
        def bounce(start,x,n=4):
            # ball bounced on the table: short down / up runs at one spot
            pts=[];t=start
            for i in range(n):
                y0,y1=(.45,.55) if i%2==0 else (.55,.45)
                pts+=path(t,x,x+.002,.2,y0,y1,arc=0);t+=.2+STEP
            return pts,t-STEP
        burst,end=bounce(3.0,.85)
        serve_at=end+5.0                                 # pause, then toss + serve
        first,_=rally(serve_at+.6,4)
        main=[Track(2,toss(serve_at)+first)]
        (a,b,r,f,prep),=episodes([Track(1,burst)]+main,0,40)
        self.assertTrue(prep)
        self.assertAlmostEqual(a,3.0-.2,delta=.05)      # starts at the bounces
        # Too long before the serve, on the receiver's side, or before the
        # previous rally ended: the usual toss lead applies.
        early,_=bounce(serve_at-12,.85)
        other,_=bounce(3.0,.2)
        for extra in (early,other):
            (a,b,r,f,prep),=episodes([Track(1,extra)]+main,0,40)
            self.assertFalse(prep);self.assertAlmostEqual(a,serve_at-1.2,delta=.05)
        # A single bounce / toss is not a burst.
        single,_=bounce(serve_at-3,.85,n=2)
        self.assertFalse(episodes([Track(1,single)]+main,0,40)[0][4])

    def test_slow_drift_after_the_strokes_ends_the_rally(self):
        import rally_serves
        first,end=rally(3.0,4)
        drift=path(end+.1,.3,.15,1.3,arc=0)            # ball rolls / carried: 0.12 S
        back=path(end+1.5,.15,.6,1.0)                    # slow pass back to the server
        serve,_=rally(end+3.7,2)                         # next point, no toss seen
        tracks=[Track(1,toss(2.4)+first),Track(2,drift+back),Track(3,serve)]
        found=episodes(tracks,0,40)
        self.assertEqual(len(found),2,found)
        self.assertAlmostEqual(found[0][1],end+.8,delta=.05)
        self.assertAlmostEqual(found[1][0],end+3.7-1.0,delta=.05)
        old=rally_serves.DEAD_DRIFT_SECONDS
        try:
            rally_serves.DEAD_DRIFT_SECONDS=99
            self.assertEqual(len(episodes(tracks,0,40)),1)   # what v4 did
        finally:rally_serves.DEAD_DRIFT_SECONDS=old
        # A lob inside a rally is slow but still crosses within ~1 s pace.
        a,t=rally(3.0,3)
        lob=path(t+.05,.3,.8,1.2,arc=.25)                 # 0.45 S
        b,_=rally(t+1.3,3,x=.8)
        self.assertEqual(len(episodes([Track(1,toss(2.4)+a+lob+b)],0,40)),1)

    def test_attack_straight_off_a_slow_ball_keeps_the_rally(self):
        first,end=rally(3.0,4)
        drift=path(end+.1,.3,.15,1.3,arc=0)            # slow 0.12 S ball ...
        attack=path(end+1.5,.15,.8,.4)                   # ... smashed at once
        more,_=rally(end+1.93,2,x=.8)
        found=episodes([Track(1,toss(2.4)+first),Track(2,drift+attack+more)],0,40)
        self.assertEqual(len(found),1,found)

    def test_high_ball_after_in_play_motion_is_not_a_new_toss(self):
        first,end=rally(3.0,2)
        block=path(end+.03,.3,.4,.4)                     # soft in-play touch
        lob=toss(end+.45,x=.4)                           # steep high ball
        reply=path(end+1.5,.41,.85,.5)
        found=episodes([Track(1,toss(2.4)+first+block+lob+reply)],0,40)
        self.assertEqual(len(found),1,found)
        # The same toss after a quiet pause is a new serve.
        lob2=toss(end+1.2,x=.8);reply2=path(end+1.8,.81,.35,.5)
        self.assertEqual(len(episodes([Track(1,toss(2.4)+first),Track(2,lob2+reply2)],0,40)),2)

    def test_soft_strokes_before_the_first_fast_one_start_the_rally(self):
        # Soft serve and pushes (below the calibrated stroke speed) going back
        # and forth, then the first fast stroke: the rally starts at the soft
        # serve, not at the fast stroke.
        soft=[];t=3.0
        for x0,x1 in ((.40,.55),(.55,.40),(.40,.55)):
            soft+=path(t,x0,x1,.75,arc=0);t+=.75+STEP
        fast,_=rally(t,3,x=.75)                       # first fast stroke goes -x
        (a,b,r,f,p),=episodes([Track(1,soft),Track(2,fast)],0,40)
        self.assertAlmostEqual(a,3.0-1.0,delta=.05)
        self.assertAlmostEqual(f,3.0,delta=.05)
        # No back-and-forth: a ball carried the same way as the first stroke,
        # or handed back and then a pause (catch, toss) before the serve.
        carried=path(3.0,.95,.80,.75,arc=0)
        fast,_=rally(3.0+.75+STEP,3,x=.75)
        (a,b,r,f,p),=episodes([Track(1,carried),Track(2,fast)],0,40)
        self.assertAlmostEqual(a,3.0+.75+STEP-1.0,delta=.05)
        handed=path(3.0,.40,.62,.75,arc=0)
        fast,_=rally(3.0+.75+1.2,3,x=.75)
        (a,b,r,f,p),=episodes([Track(1,handed),Track(2,fast)],0,40)
        self.assertAlmostEqual(a,3.0+.75+1.2-1.0,delta=.05)

    def test_lone_flight_without_toss_is_not_a_rally(self):
        # One ball hit back / away between points, nothing else moving.
        self.assertEqual(episodes([Track(1,path(3.0,.8,.3,.5))],0,20),[])
        # The same stroke with a toss is a serve (a fault still counts) ...
        self.assertEqual(len(episodes([Track(1,toss(2.4,x=.8)+path(3.0,.8,.3,.5))],0,20)),1)
        # ... and with a return it is play.
        self.assertEqual(len(episodes([Track(1,path(3.0,.8,.3,.5)+path(3.5+STEP,.3,.6,.6))],0,20)),1)

    def test_pop_up_is_not_a_toss_and_thrown_in_ball_is_not_a_serve(self):
        # After the last stroke the ball pops up high AND travels across the
        # table; a slow hit right after is not "toss + serve".
        first,end=rally(3.0,3)
        pop=path(end+3.5,.3,.55,1.2,.6,.6,arc=.5)       # high AND ~0.5 W across
        slow=path(end+4.8,.55,.35,.6)                   # below opening speed
        found=episodes([Track(1,toss(2.4)+first),Track(2,pop+slow)],0,40)
        self.assertEqual(len(found),1,found)
        # A ball entering from the frame edge, hit on at once: not a serve.
        thrown=path(3.0,.01,.25,.5)
        hit,_=rally(3.5+.3,2,x=.25)
        self.assertEqual(episodes([Track(1,thrown),Track(2,hit)],0,40),[])
        hit,_=rally(3.5+2.0,2,x=.25)                     # later: an ordinary opening
        self.assertEqual(len(episodes([Track(1,thrown),Track(2,hit)],0,40)),1)

    def test_slow_serve_needs_its_toss(self):
        serve=path(2,.75,.4,1.3)            # 0.27 frame widths/s
        self.assertEqual(episodes([Track(1,serve)],0,10),[])
        self.assertEqual(len(episodes([Track(1,toss(1.2)+serve)],0,10)),1)

    def test_ball_thrown_in_from_the_frame_edge_is_not_a_rally(self):
        thrown=path(3,.99,.3,1.0,.3,.6)     # fast, but enters from outside
        self.assertEqual(episodes([Track(1,thrown)],0,10),[])
        idle=[(4+i*STEP,.55*960,.5*540,.9) for i in range(60)]  # held / lying ball
        self.assertEqual(episodes([Track(2,idle)],0,10),[])

    def test_hop_between_still_balls_is_not_a_stroke(self):
        # Server bounces / holds the ball at x=.35 while a ball lies at x=.57;
        # the tracker alternates between them (04:45 on the spectator clip).
        hold=lambda t,x,n:[(t+i*STEP,x*960,.6*540,.9) for i in range(n)]
        hops=hold(1,.57,3)+hold(1.2,.35,3)+hold(1.5,.57,3)+hold(1.8,.35,3)+hold(2.1,.57,3)
        self.assertEqual(episodes([Track(1,hops)],0,10),[])
        # A real fast stroke with one missing-frame jump is still a stroke.
        flight=[p for i,p in enumerate(path(1,.7,.2,.4)) if i not in (5,6,7)]+path(1.4+STEP,.2,.7,.4)
        self.assertEqual(len(episodes([Track(1,flight)],0,10)),1)

    def test_tracking_gap_inside_rally_is_bridged_by_weak_motion(self):
        head,t=rally(1,3)
        # Short slow pushes / partial tracking: weak, not strokes.
        slow=path(t+.3,.6,.5,.6)+path(t+.95,.5,.6,.6)+path(t+1.6,.6,.5,.6)
        tail,end=rally(t+2.6,2)
        found=episodes([Track(1,toss(.4)+head+slow+tail)],0,20)
        self.assertEqual(len(found),1,found)
        self.assertAlmostEqual(found[0][1],end+.8,delta=.05)
        # Without the bridging motion a 2.6 s silence ends the rally.
        self.assertEqual(len(episodes([Track(1,toss(.4)+head+tail)],0,20)),2)

    def test_new_toss_starts_a_new_rally_even_after_a_short_gap(self):
        head,t=rally(1,2)
        tail,_=rally(t+1.6,2)
        self.assertEqual(len(episodes([Track(1,toss(.4)+head),Track(2,toss(t+1.1)+tail)],0,20)),2)
        self.assertEqual(len(episodes([Track(1,toss(.4)+head),Track(2,tail)],0,20)),1)

    def test_zoom_and_camera_distance_do_not_change_episodes(self):
        # A whole match filmed from further away / zoomed out: positions and
        # speeds shrink by the same factor; the calibrated rule must agree.
        video=[]
        t=1.0
        for i in range(14):
            x=.75 if i%2 else .3
            head,end=rally(t+.6,3+i%3,x=x)
            video.append(Track(i,toss(t,x=x)+head));t=end+6
        def zoom(k):
            return [Track(tr.id,[(p[0],480+(p[1]-480)*k,270+(p[2]-270)*k,p[3]) for p in tr.points]) for tr in video]
        near=calibrated_episodes(video,0,t)
        self.assertEqual(len(near),14)
        S,W=calibrate(video)
        # Fixed frame-unit thresholds lose everything at 0.4x ...
        self.assertEqual(calibrated_episodes(zoom(.4),0,t,scale=(S,W)),[])
        for k in (.4,.6,1.4):  # ... the calibrated rule does not.
            far=calibrated_episodes(zoom(k),0,t)
            self.assertEqual([(round(a,2),round(b,2)) for a,b,*_ in far],[(round(a,2),round(b,2)) for a,b,*_ in near])
        S2,W2=calibrate(zoom(.6))
        self.assertAlmostEqual(S2/S,.6,delta=.02);self.assertAlmostEqual(W2/W,.6,delta=.02)
        # Too little evidence to calibrate: the rule does not guess.
        self.assertIsNone(calibrate(video[:2]))
        self.assertEqual(calibrated_episodes(video[:2],0,t),[])

    def test_horizontal_view_gate(self):
        tracks=[Track(i,rally(i*10,4)[0]) for i in range(12)]
        self.assertTrue(horizontal_view(tracks))
        # End-on broadcast: the ball travels along image y.
        vertical=[Track(i,[(p[0],480+(p[2]-297)*.2,(p[1]/960)*540,.9) for p in rally(i*10,4)[0]]) for i in range(40)]
        self.assertFalse(horizontal_view(vertical))
        self.assertFalse(horizontal_view(tracks[:2]))   # too little evidence

    def test_activity_uses_frame_rule_across_geometry_churn(self):
        first,end1=rally(1.0,6)
        tracks=[Track(i,rally(20+i*10,4)[0]) for i in range(10)]+[Track(99,toss(.4)+first)]
        # Wide perspective box re-followed every few seconds, sometimes lost
        # (moving spectator camera): one rally regardless of the churn.
        segs=[{'start':0,'end':1.5,'bounds':[.3,.6,.75,.7],'method':'perspective-rims'},
              {'start':1.5,'end':3,'bounds':[.31,.61,.76,.71],'method':'perspective-rims'},
              {'start':3,'end':5,'bounds':[],'method':'unavailable'}]
        segs+=[{'start':s,'end':s+5,'bounds':[.3,.6,.75,.7],'method':'perspective-rims'} for s in range(5,200,5)]
        out=[i for i in activity_intervals(tracks,segs,200) if i[0]<10]
        self.assertEqual(len(out),1,out)
        self.assertEqual(out[0][2],'live_ball_evidence')
        # No geometry at all: the self-calibrated frame rule still runs ...
        from rally_activity import frame_rule_active
        none=[{'start':0,'end':200,'bounds':[],'method':'unavailable'}]
        self.assertTrue(frame_rule_active(tracks,segs,200))
        self.assertTrue(frame_rule_active(tracks,none,200))
        self.assertEqual(activity_intervals(tracks,none,200)[0][2],'live_ball_evidence')
        # ... unless play does not run along x (end-on broadcast): fail open.
        end_on=[Track(t.id,[(p[0],480+(p[2]-297)*.2,(p[1]/960)*540,.9) for p in t.points]) for t in tracks]
        self.assertFalse(frame_rule_active(end_on,none,200))
        self.assertEqual(activity_intervals(end_on,none,200),[(0,200,None,None)])
        # A fixed perspective box also uses the frame rule (better on 0044) ...
        from rally_activity import _episodes
        fixed=[{'start':0,'end':200,'bounds':[.3,.6,.75,.7],'method':'perspective-rims'}]
        frame=[(a,b) for a,b,*_ in calibrated_episodes(tracks,0,200)]
        self.assertEqual([i[:2] for i in activity_intervals(tracks,fixed,200)],frame)
        # ... and the perspective rule remains the fallback where the frame
        # rule cannot run (play not along x).
        end_on_fixed=[Track(t.id,[(p[0],480+(p[2]-297)*.2,(p[1]/960)*540,.9) for p in t.points]) for t in tracks]
        self.assertEqual([i[:3] for i in activity_intervals(end_on_fixed,fixed,200)],
                         [(a,b,'live_ball_evidence') for a,b,_ in _episodes(
                             sorted({p[0]:(p[0],p[1]/960,p[2]/540,p[3]) for t in end_on_fixed for p in t.points}.values()),
                             fixed[0]['bounds'],0,200)])
        # Side-view geometry keeps the side-transit rule.
        side=[{'start':0,'end':200,'bounds':[.17,.38,.84,.50],'method':'side-color-rim'}]
        from rally_transits import episodes as transit
        self.assertEqual([i[:2] for i in activity_intervals(tracks,side,200)],
                         [e[:2] for e in transit(tracks,side[0]['bounds'],0,200)])


@unittest.skipUnless(os.environ.get('RALLYCUT_FRAME_SERVE_AB'),'private spectator-view A/B')
class PrivateFrameServeAB(unittest.TestCase):
    """RALLYCUT_FRAME_SERVE_AB=<analysis.json>:<labels.json> (headless --include-tracks)."""

    def test_labelled_range(self):
        analysis,labels=os.environ['RALLYCUT_FRAME_SERVE_AB'].split(':')
        d=json.loads(Path(analysis).read_text());truth=json.loads(Path(labels).read_text())
        horizon=truth['horizon']
        self.assertIn('frame-serve-v8',d['summary']['activity_rule_version'].split('+'))
        T=[Interval(r['id'],r['start'],r['end']) for r in truth['rallies'] if not r.get('optional')]
        C=[Interval(str(i),s['start'],s['end']) for i,s in enumerate(d['segments']) if s['start']<horizon]
        loose=evaluate(T,C,.3,1.0)
        self.assertGreaterEqual(loose['recall'],.9)
        self.assertGreaterEqual(loose['precision'],.9)


if __name__=='__main__':
    unittest.main()
