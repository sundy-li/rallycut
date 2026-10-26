import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rally_state import BallValidity,resegment,validate_net_region
from visual import Track,segment_rallies
from audio_features import fuse_audio_visual

TABLE=[.2,.4,.8,.5]


def feed(state,points):
    for t,x,y in points:state.observe(t,[(x,y,.95)])


class RallyValidityTests(unittest.TestCase):
    def out(self):
        state=BallValidity(TABLE)
        points=[(i*.05,x,y) for i,(x,y) in enumerate([
            (.28,.25),(.36,.23),(.44,.22),(.52,.22),(.60,.23),(.68,.24),(.77,.25),(.81,.26),(.85,.27)])]
        feed(state,points);state.observe(.7,[])
        self.assertEqual(state.state,'WAIT_SERVE')
        self.assertEqual(state.events[0]['reason'],'out_without_table_bounce')
        return state,points

    def test_out_and_return_toss_do_not_count_as_next_serve(self):
        state,points=self.out()
        feed(state,[(.9,.86,.24),(.95,.75,.22),(1,.64,.23),(1.05,.52,.25),
                    (1.1,.42,.30),(1.15,.35,.42),(1.2,.29,.36),(1.25,.23,.31)])
        self.assertEqual(state.state,'WAIT_SERVE')
        self.assertEqual(len(state.events),1)
        # Genuine serve: starts on left, bounces on OWN half while moving inward.
        serve=[(1.5,.23,.34),(1.55,.27,.38),(1.6,.32,.44),(1.65,.37,.39),(1.7,.42,.35)]
        feed(state,serve)
        self.assertEqual(state.state,'IN_PLAY')
        self.assertEqual(state.events[-1]['reason'],'serve_own_half_bounce')
        self.assertGreaterEqual(state.dead_intervals[0]['end'],1.5)

    def test_normal_crossings_bounces_and_wide_returns_are_not_dead(self):
        state=BallValidity(TABLE)
        points=[(i*.05,x,y) for i,(x,y) in enumerate([
            (.28,.3),(.4,.28),(.53,.3),(.63,.36),(.72,.45),(.78,.39),(.83,.34),
            (.76,.30),(.65,.32),(.54,.35),(.44,.40),(.34,.45),(.26,.38),(.18,.32)])]
        feed(state,points);state.finish(2)
        self.assertEqual(state.events,[])

    def test_net_drop_requires_actual_geometry_and_not_merely_midpoint(self):
        points=[(i*.05,x,y) for i,(x,y) in enumerate([
            (.36,.31),(.40,.32),(.44,.34),(.475,.35),(.48,.36),(.479,.37),
            (.476,.39),(.472,.415),(.47,.44),(.469,.455)])]
        for net in (None,[.5,.34,.43]):
            state=BallValidity(TABLE,net)
            feed(state,points);state.observe(.8,[])
            if net:self.assertEqual(state.events[0]['reason'],'net_drop_same_side')
            else:self.assertEqual(state.events,[])

    def test_net_graze_that_continues_through_is_not_ended(self):
        state=BallValidity(TABLE,[.5,.34,.43])
        feed(state,[(i*.05,x,y) for i,(x,y) in enumerate([
            (.36,.31),(.40,.32),(.44,.34),(.475,.35),(.48,.36),(.479,.37),(.476,.39),(.472,.415),
            (.53,.37),(.58,.35),(.64,.35)])])
        state.observe(.9,[]);self.assertEqual(state.events,[])

    def test_confirmed_held_ball_and_immediate_return_are_separate(self):
        state=BallValidity(TABLE)
        feed(state,[(i*.05,x,.3) for i,x in enumerate([.32,.4,.48,.56,.64,.73,.79])])
        feed(state,[(.35+i*.05,.79+(i%2)*.001,.30) for i in range(12)])
        state.observe(1.1,[])
        self.assertTrue(any(e['reason']=='held_after_flight' for e in state.events))

    def test_below_table_catch_ends_but_low_defensive_recovery_does_not(self):
        approach=[(i*.05,x,y) for i,(x,y) in enumerate([
            (.70,.28),(.64,.32),(.58,.37),(.53,.42),(.48,.47),(.43,.54),
            (.425,.545),(.42,.546),(.419,.546),(.418,.545),(.417,.546)])]
        caught=BallValidity(TABLE);feed(caught,approach);caught.observe(.9,[])
        self.assertTrue(any(e['reason']=='below_table_stopped' for e in caught.events))
        saved=BallValidity(TABLE);feed(saved,approach)
        feed(saved,[(.53,.49,.46),(.58,.57,.38),(.63,.65,.36)])
        saved.observe(1,[])
        self.assertFalse(any(e['reason']=='below_table_stopped' for e in saved.events))

    def test_audio_and_padding_cannot_bridge_dead_intervals(self):
        state,_=self.out()
        state._restart(1.5,1.7,(1.7,.4,.35,.9),'serve_own_half_bounce')
        # Continuous tracks and impacts would previously become a single rally.
        points=[(i*.05,.35+(i%10)*.02,.35,.9) for i in range(80)]
        tracks=[Track(1,points)];hits=[i*.3 for i in range(14)]
        old=fuse_audio_visual(segment_rallies(tracks,4),tracks,hits,4)
        self.assertEqual(len(old),1)
        new=resegment(tracks,hits,4,state)
        self.assertEqual(len(new),2)
        self.assertLessEqual(new[0]['end'],state.events[0]['time']+.000001)
        self.assertGreaterEqual(new[1]['start'],state.dead_intervals[0]['start'])
        self.assertLess(new[1]['start'],state.events[-1]['time'])
        self.assertTrue(new[1]['boundary_before'])
        self.assertEqual(new[0]['end_reason'],'out_without_table_bounce')

    def test_serve_restart_candidate_can_include_pre_observation_toss(self):
        state=BallValidity()
        state.dead_intervals=[{'start':0,'end':5,'event':{'type':'dead_ball'},'resume_reason':'serve_restart'}]
        track=Track(1,[(6+i/30,.2+i*.04,.35,.9) for i in range(36)])
        output=resegment([track],[],8,state,finalize=False)
        self.assertEqual(len(output),1)
        self.assertAlmostEqual(output[0]['start'],4.4,places=6)
        self.assertLess(output[0]['start'],5)

    def test_serve_preparation_and_strokes_are_one_rally(self):
        # Activity interval from the frame rule starting at the bounces: the
        # bounce points and, after a pause, the strokes stay one rally.
        from unittest import mock
        bounces=[(2+i/30,800,260+(i%6)*6,.9) for i in range(30)]
        strokes=[(9+i/30,200+i*12,250,.9) for i in range(60)]
        tracks=[Track(1,bounces),Track(2,strokes)]
        geometry=[{'start':0,'end':20,'bounds':[],'method':'unavailable'}]
        for reason,expected in (('serve_prep',1),('live_ball_evidence',2)):
            with mock.patch('rally_activity.activity_intervals',return_value=[(1.8,11.8,reason,'stroke_gap',9.0)]):
                out=resegment(tracks,[],20,BallValidity(),geometry_segments=geometry,track_size=(960,540))
            self.assertEqual(len(out),expected,out)
            if reason=='serve_prep':
                self.assertAlmostEqual(out[0]['start'],1.8,delta=.05)
                self.assertEqual(out[0]['start_reason'],'serve_prep')
                self.assertTrue(out[0]['boundary_before'])

    def test_frame_rule_episode_is_not_cut_by_a_slow_piece_mid_rally(self):
        # The frame rule saw strokes up to 9.0 s (episode end 9.8 = last
        # stroke + TAIL). If the visual segmenter's tail trim stops at a slow
        # piece mid-rally (4.9 s), the rally still runs to the episode end.
        from unittest import mock
        points=[(2+i/30,200+(i%30)*18,250,.9) for i in range(210)]
        geometry=[{'start':0,'end':20,'bounds':[],'method':'unavailable'}]
        trimmed=[{'id':'visual-00001','start':1.6,'end':4.9,'confidence':.6,'score':40,'selected':True,'edited':False}]
        out={}
        for source in ('frame','other'):
            evidence=(2.0,'frame') if source=='frame' else (2.0,)
            with mock.patch('rally_activity.activity_intervals',return_value=[(1.0,9.8,'live_ball_evidence','stroke_gap',*evidence)]),\
                 mock.patch('rally_activity.frame_rule_active',return_value=True),\
                 mock.patch('rally_state.segment_rallies',side_effect=lambda *a,**k:[dict(r) for r in trimmed]):
                out[source]=resegment([Track(1,points)],[],20,BallValidity(),geometry_segments=geometry,track_size=(960,540))
        self.assertEqual([(r['start'],r['end']) for r in out['frame']],[(1.6,9.8)])
        self.assertEqual([(r['start'],r['end']) for r in out['other']],[(1.6,4.9)])   # non-frame rules unchanged

    def test_frame_rule_episode_is_not_trimmed_by_a_perspective_box(self):
        # Strokes low in the image, below a perspective box: the frame rule
        # chose this episode without the box, so the box must not erase it.
        from unittest import mock
        # A brief flight over the box, then the rally continues low in the
        # image (below the box: the box-based tail trim calls it pickup).
        strokes=[(3+i/30,200+(i%30)*18,200 if i<8 else 500,.9) for i in range(150)]
        geometry=[{'start':0,'end':20,'bounds':[.3,.4,.75,.55],'method':'perspective-rims'}]
        counts=[]
        for active in (True,False):
            with mock.patch('rally_activity.activity_intervals',return_value=[(2.5,8.5,'live_ball_evidence','stroke_gap',3.0)]),\
                 mock.patch('rally_activity.frame_rule_active',return_value=active):
                counts.append(len(resegment([Track(1,strokes)],[],20,BallValidity(),geometry_segments=geometry,track_size=(960,540))))
        self.assertEqual(counts,[1,0])

    def test_resegment_scales_normalized_table_for_pixel_tracks(self):
        state=BallValidity()
        points=[(3+i/30,200+i*.015*960,200,.9) for i in range(36)]
        points += [(4.25+i/30,500+(i%2)*2,200,.9) for i in range(36)]
        points += [(5.7+i/30,200+i*.015*960,200,.9) for i in range(24)]
        geometry=[{'start':0,'end':8,'bounds':[.1,.2,.7,.5],'method':'side-color-rim'}]
        output=resegment([Track(1,points)],[],8,state,geometry_segments=geometry,track_size=(960,540))
        self.assertEqual(len(output),1)
        self.assertLess(output[0]['end'],5.3)

    def test_live_resegment_does_not_finalize_open_dead_interval(self):
        state,_=self.out()
        resegment([],[],4,state,finalize=False,horizon=1)
        self.assertIsNone(state.dead_intervals[0]['end'])
        self.assertEqual(state.state,'WAIT_SERVE')

    def test_perspective_view_does_not_assume_table_end_from_bbox(self):
        state=BallValidity(TABLE,geometry_method='perspective-rims')
        feed(state,[(i*.05,x,.3) for i,x in enumerate([.3,.4,.5,.6,.7,.8,.85,.9])])
        state.finish(2);self.assertEqual(state.events,[])

    def test_invalid_manual_net_geometry_rejected(self):
        for value in ([.5,.3,.4],[-1,.3,.4,.7,.3,.4],[.7,.3,.4,.5,.3,.4]):
            with self.assertRaises(ValueError):validate_net_region(value)
        validate_net_region([.45,.32,.39,.65,.34,.44])

    @unittest.skipUnless(os.getenv('RALLYCUT_FULL_DEAD_BALL_DIR'),'explicit complete raw detection replay')
    def test_both_user_0043_cases_with_original_model_observations(self):
        root=Path(os.environ['RALLYCUT_FULL_DEAD_BALL_DIR'])
        data=json.loads((root/'0043-full-v2.json').read_text())
        state=BallValidity(data['summary']['table_bounds'],data['summary'].get('net_region'))
        for line in (root/'0043-full-v2-predictions.jsonl').read_text().splitlines():
            frame=json.loads(line);state.observe(frame['t'],frame['roi_candidates'])
        tracks=[Track(t['id'],[(p['t'],p['x']*960,p['y']*540,p['confidence']) for p in t['points']]) for t in data['tracks']]
        duration=json.loads((root/'0043-full-v2-provenance.json').read_text())['source']['duration']
        output=resegment(tracks,[i*.3 for i in range(int(duration/.3))],duration,state)
        self.assertTrue(any(e['reason']=='out_without_table_bounce' and 17.7<e['time']<18.2 for e in state.events))
        self.assertTrue(any(e['reason']=='below_table_stopped' and 34.1<e['time']<34.8 for e in state.events))
        self.assertFalse(any(r['start']<17.9 and r['end']>20.5 for r in output))
        self.assertFalse(any(r['start']<34.3 and r['end']>36.6 for r in output))

    @unittest.skipUnless(os.getenv('RALLYCUT_DEAD_BALL_DIR'),'explicit real-video replay artifacts')
    def test_user_0043_out_catch_and_serve_regression(self):
        root=Path(os.environ['RALLYCUT_DEAD_BALL_DIR'])
        data=json.loads((root/'0043-baseline.json').read_text())
        state=BallValidity(data['summary']['table_bounds'])
        for line in (root/'0043-predictions.jsonl').read_text().splitlines():
            frame=json.loads(line);state.observe(frame['t'],frame['roi_candidates'])
        tracks=[Track(t['id'],[(p['t'],p['x']*960,p['y']*540,p['confidence']) for p in t['points']]) for t in data['tracks']]
        # Extremely dense audio must still not undo the dead-ball exclusion.
        result=resegment(tracks,[i*.3 for i in range(100)],30,state)
        event=next(e for e in state.events if e['type']=='dead_ball')
        self.assertTrue(17.7<event['time']<18.2,event)
        restart=next(e for e in state.events if e['type']=='restart')
        self.assertTrue(20<restart['time']<21,restart)
        self.assertFalse(any(r['start']<17.9 and r['end']>20.5 for r in result))
        self.assertTrue(any(r.get('boundary_before') for r in result))


if __name__=='__main__':unittest.main()
