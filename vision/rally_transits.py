"""Side-view rally episodes from cross-table transits, NOT net/out adjudication.

Only trusted side-view (`side-color-rim`) geometry enables this auxiliary rule;
it never removes model points or tracks. In-play strokes cross the table fast
and low; between points the ball is picked up and returned slowly and/or with a
high lob. An episode therefore starts at a strong transit (optionally preceded
by an end-of-table vertical serve toss), is extended by further transits within
a short gap, and closes when no transit follows. Audio is never used.

Units: positions are normalized to the video, then expressed in table widths
(x) and table heights (y) of the current shot's geometry. Times are source PTS.
"""

VERSION='side-transit-v4'

# Strong transit: normal stroke (long + fast), or a shorter very fast/flat one.
# 1.0 table widths/s admits a slow, low serve that is not returned (0041
# 16:14 / 20:54); 0.9-1.0 give identical results on all labelled footage.
STRONG_DX=.55;STRONG_SPEED=1.0;STRONG_APEX=1.6
SHORT_DX=.30;SHORT_SPEED=1.4;SHORT_APEX=1.0
# A stroke clears the net, so it peaks above the table's far edge; a fast piece
# that never rises above the lower half of the table band is a ball on the
# floor / under the table (lowest in-rally strong transit on 0041: -0.23).
STRONG_FLOOR=-.5
# Weak transit can continue, never start, an episode (e.g. lob defence).
WEAK_DX=.15;WEAK_SPEED=.6;WEAK_APEX=2.2
# A strong but high and only moderately fast transit (a paddle return of the
# ball to the server) may continue an episode, never open one.
OPEN_APEX=1.0;OPEN_FAST=1.5
# 1.2 s keeps a rally whose far player stands outside the frame (the ball is
# unseen while it travels to them and back); points are >=2 s apart here.
STRONG_GAP=1.2;WEAK_GAP=.5
# Start: the earlier of (serve toss - pad) and (first transit - lead). Players
# prepare ~1.1-1.5 s before the first transit; a detected toss can be late.
TOSS_WINDOW=2.5;TOSS_PAD=.2;NO_TOSS_LEAD=1.3;TAIL=.5
# An episode with a single strong transit is a serve (fault) only if low;
# serves stay <=0.7 table heights, a ball sent back to the server is higher.
SINGLE_APEX=.8
# Sparse toss points can sit within RUN_GAP of the serve and inflate its apex:
# a near-vertical first step (<0.05 widths across, >0.5 heights up/down) is
# dropped from the front of a piece.
PEEL_DX=.05;PEEL_DY=.5
RUN_GAP=.15;REVERSAL_STEP=.002;TOSS_SPAN=.01
# Teleport: one horizontal step >= 0.06 frame widths between points that are
# otherwise still (mean |dx| <= 0.005 frame widths per point on both sides).
# The tracker linked a held / bouncing ball with another ball at rest; that is
# no flight. Frame units: a still ball is still at any zoom.
TELEPORT_STEP=.06;TELEPORT_STILL=.005
# Analysis corridor (table units): neighbouring tables / floor are not play.
CORRIDOR_X=.35;CORRIDOR_ABOVE=3.0;CORRIDOR_BELOW=1.5


def side_view(segment):
    bounds=segment.get('bounds')
    if segment.get('method')!='side-color-rim' or not bounds or len(bounds)!=4:return False
    left,top,right,bottom=bounds
    return right>left and bottom>top and (right-left)/(bottom-top)>4


def _runs(points):
    """Split one track into horizontally monotone pieces.

    A vertical toss followed by the serve stroke is split as well, so the toss
    is recognised and does not dilute the serve transit's speed.
    """
    runs=[];run=[points[0]]
    for a,c in zip(points,points[1:]):
        reversal=(len(run)>=2 and (c[1]-run[-1][1])*(run[-1][1]-run[0][1])<0 and
                  abs(c[1]-run[-1][1])>REVERSAL_STEP)
        span=max(p[1] for p in run)-min(p[1] for p in run)
        launched=len(run)>=5 and span<=TOSS_SPAN and abs(c[1]-a[1])>REVERSAL_STEP*3
        if c[0]-a[0]>RUN_GAP or reversal or launched:runs.append(run);run=[]
        run.append(c)
    runs.append(run)
    return runs


def _teleports(points):
    """Split one track where it hops between two (nearly) still objects."""
    pieces=[[points[0]]]
    steps=[abs(b[1]-a[1]) for a,b in zip(points,points[1:])]
    for i,step in enumerate(steps):
        before=steps[max(0,i-2):i];after=steps[i+1:i+3]
        # A track edge counts as still: one jump into / out of a still ball
        # is no evidence of flight either.
        still=lambda side:not side or sum(side)/len(side)<=TELEPORT_STILL
        if step>=TELEPORT_STEP and (before or after) and still(before) and still(after):pieces.append([])
        pieces[-1].append(points[i+1])
    return pieces


def ball_runs(points):
    """Monotone horizontal pieces of one track (normalized frame coords),
    after removing tracker hops. Shared by all rally rules."""
    if len(points)<3:return []
    return [run for piece in _teleports(points) if len(piece)>=3 for run in _runs(piece)]


def transits(tracks,bounds,lo,hi,track_size=(960,540)):
    """Return per-track horizontal pieces with table-relative features."""
    left,top,right,bottom=bounds;width=right-left;height=bottom-top
    sx,sy=track_size;out=[]
    for track in tracks:
        points=[(p[0],p[1]/sx,p[2]/sy) for p in track.points if lo<=p[0]<hi]
        for run in ball_runs(points):
            if len(run)<3:continue
            elapsed=run[-1][0]-run[0][0]
            if elapsed<=0:continue
            xs=[(p[1]-left)/width for p in run];ys=[p[2] for p in run]
            while (len(xs)>3 and abs(xs[1]-xs[0])<PEEL_DX and
                   abs(ys[1]-ys[0])/height>PEEL_DY):
                run=run[1:];xs=xs[1:];ys=ys[1:]
            elapsed=run[-1][0]-run[0][0]
            if (max(xs)<-CORRIDOR_X or min(xs)>1+CORRIDOR_X or
                min(ys)>bottom+height*CORRIDOR_BELOW or max(ys)<top-height*CORRIDOR_ABOVE):continue
            dx=abs(xs[-1]-xs[0])
            out.append({'t0':run[0][0],'t1':run[-1][0],'dx':dx,'speed':dx/elapsed,
                        'apex':(top-min(ys))/height,'dy':(max(ys)-min(ys))/height,'x0':xs[0]})
    return sorted(out,key=lambda item:(item['t0'],item['t1']))


def _kind(item):
    if STRONG_FLOOR<=item['apex']<=STRONG_APEX and ((item['dx']>=STRONG_DX and item['speed']>=STRONG_SPEED) or
        (item['dx']>=SHORT_DX and item['speed']>=SHORT_SPEED and item['apex']<=SHORT_APEX)):return 'strong'
    if item['dx']>=WEAK_DX and item['speed']>=WEAK_SPEED and item['apex']<=WEAK_APEX:return 'weak'
    return None


def _toss(item):
    # Vertical toss at a player end: little horizontal travel, clearly rising
    # above the table. A hand bounce or a slow roll fails these limits.
    return item['dx']<=.15 and item['dy']>=.5 and item['apex']>=.4 and (item['x0']<.15 or item['x0']>.85)


def episodes(tracks,bounds,lo,hi,track_size=(960,540)):
    """[(start, end, end_reason, first_transit)] inside [lo, hi).

    Reason '' means still open; first_transit is the first live-ball evidence
    (start may lead it by the serve toss / preparation allowance).
    """
    items=transits(tracks,bounds,lo,hi,track_size)
    tosses=[item for item in items if _toss(item)]
    groups=[];current=None
    for item in items:
        kind=_kind(item)
        if not kind:continue
        if current and item['t0']-current['end']<=(STRONG_GAP if kind=='strong' else WEAK_GAP):
            current['end']=max(current['end'],item['t1']);current['strong']+=kind=='strong';continue
        if kind!='strong' or (item['apex']>OPEN_APEX and item['speed']<OPEN_FAST):continue
        if current:groups.append(current)
        current={'first':item['t0'],'end':item['t1'],'strong':1,'apex':item['apex']}
    if current:groups.append(current)
    out=[];floor=lo
    for group in groups:
        # A lone strong transit must look like a serve (it bounces on the
        # server's side first, so it stays low); a higher one is a return.
        if group['strong']==1 and group['apex']>SINGLE_APEX:continue
        serve=[t for t in tosses if group['first']-TOSS_WINDOW<=t['t0']<=group['first']-.1 and t['t0']>=floor]
        start=group['first']-NO_TOSS_LEAD
        if serve:start=min(start,serve[-1]['t0']-TOSS_PAD)
        start=max(floor,start)
        end=min(hi,group['end']+TAIL)
        if end-start<.2:continue
        # Not enough source time after the last transit to know it ended.
        reason='' if hi-group['end']<STRONG_GAP else 'transit_gap'
        out.append((start,end,reason,group['first']));floor=end
    return out
