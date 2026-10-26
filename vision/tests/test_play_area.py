"""Off-play track marking (display only)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from play_area import off_play_tracks
from visual import Track

STEP=1/30


def flight(tid,start,x0,x1,seconds=.5,y=.4,arc=.08):
    n=round(seconds/STEP);pts=[]
    for i in range(n+1):
        f=i/n;pts.append((start+i*STEP,(x0+(x1-x0)*f)*960,(y-arc*4*f*(1-f))*540,.9))
    return Track(tid,pts)


def rolling(tid,start,x,y,seconds=1.0,dx=.04):
    n=round(seconds/STEP)
    return Track(tid,[(start+i*STEP,(x+dx*i/n)*960,y*540,.9) for i in range(n+1)])


def match(scale=1.0,shift=(0,0),strokes=60):
    """Strokes across a table spanning x .25-.75; zoom / pan via scale+shift."""
    tracks=[flight(i,i*2.0,.25,.75) if i%2==0 else flight(i,i*2.0,.75,.25) for i in range(strokes)]
    move=lambda t:Track(t.id,[(p[0],(480+(p[1]-480)*scale)+shift[0]*960,(270+(p[2]-270)*scale)+shift[1]*540,p[3]) for p in t.points])
    return [move(t) for t in tracks],move


class PlayAreaTests(unittest.TestCase):
    def test_floor_ball_far_from_play_is_marked_but_play_is_not(self):
        tracks,_=match()
        floor=rolling(1000,30.2,.04,.93)           # corner of the hall
        near=rolling(1001,40.2,.45,.42)            # slow ball over the table
        marked=off_play_tracks(tracks+[floor,near])
        self.assertEqual(marked,{1000})

    def test_a_fast_stroke_is_never_marked_even_away_from_play(self):
        tracks,_=match()
        wide=flight(1000,30.2,.95,.55,y=.9)        # a real flight low and wide
        self.assertNotIn(1000,off_play_tracks(tracks+[wide]))

    def test_zoom_and_pan_do_not_change_the_marks(self):
        tracks,move=match()
        extra=[rolling(1000,30.2,.04,.93),rolling(1001,40.2,.45,.42)]
        base=off_play_tracks(tracks+extra)
        for scale,shift in ((.6,(0,0)),(.7,(.1,-.05))):
            moved,move=match(scale,shift)
            self.assertEqual(off_play_tracks(moved+[move(t) for t in extra]),base)

    def test_area_follows_a_moving_camera(self):
        early,_=match(strokes=40)
        late,_=match(shift=(0,.35),strokes=40)
        late=[Track(t.id+100,[(p[0]+300,p[1],p[2],p[3]) for p in t.points]) for t in late]
        # Same image spot: off-play while play is high in the frame, in play
        # once the camera has moved and play happens there.
        spot=lambda tid,t:rolling(tid,t,.5,.75)
        marked=off_play_tracks(early+late+[spot(1000,40.2),spot(1001,340.2)])
        self.assertIn(1000,marked)
        self.assertNotIn(1001,marked)

    def test_without_enough_evidence_nothing_is_marked(self):
        tracks,_=match(strokes=10)
        self.assertEqual(off_play_tracks(tracks+[rolling(1000,5.2,.04,.93)]),set())
        far_later,_=match(strokes=60)
        lone=rolling(1000,500,.04,.93)              # no play within +-45 s
        self.assertEqual(off_play_tracks(far_later+[lone]),set())


class SerializeTests(unittest.TestCase):
    def test_flag_is_written_only_for_marked_tracks(self):
        from neural_analysis import serialize_tracks
        tracks=[rolling(1,0,.5,.5),rolling(2,1,.5,.5)]
        out=serialize_tracks(tracks,{2})
        self.assertNotIn('off_play',out[0])
        self.assertIs(out[1]['off_play'],True)
        self.assertEqual(len(out[1]['points']),len(tracks[1].points))   # nothing dropped


if __name__=='__main__':
    unittest.main()
