"""Frame-space rally episodes for side-on spectator views, NOT net/out calls.

Used where no trusted side-view geometry exists but the ball clearly travels
along the image x axis (`horizontal_view`): e.g. an elevated hand-held
spectator recording, whose table box is perspective / missing / drifting and
whose players stand metres behind the table. Table-relative rules reject such
strokes; here the video calibrates its own scale instead: W is the typical
horizontal extent of a ball run (90th percentile, about one table length in
the image) and S the typical speed of long runs (75th percentile). Distance
thresholds are fractions of W, speeds fractions of S, so camera distance /
zoom do not change the rule. Times are seconds (play tempo is not scale
dependent).

A rally opens at a horizontal stroke run, either right after a serve toss (a
near-vertical run, the stroke may then be slower: the serve) or fast enough on
its own; it continues on further strokes within a short gap (weak motion may
bridge a longer one), a new toss + serve always opens a new rally, and it ends
a short tail after the last stroke. A run entering from the frame edge is a
ball thrown in from outside, not a stroke; a single jump between two still
balls (tracker hop while the server bounces the ball) is not one either.
Audio is never used.

Later additions (each kept only because no labeled video got worse; evidence,
sensitivity ranges and rejected alternatives: docs/spectator-frame-serves.md,
docs/evaluation.md):
- v4 serve preparation: a burst of >= 3 alternating short vertical runs on the
  server's side within 8 s before the serve starts the rally (serve_prep).
- v5 dead drift: a >= 1 s horizontal drift slower than 0.33 S after the
  strokes is the ball rolling / carried back: the rally ends there.
- v6 a high ball straight after in-play motion is a lob, not a new toss; a
  fast stroke <= 0.5 s after a slow drift keeps the rally (attack off a slow
  ball).
- v7 soft lead-in: soft strokes going back and forth right before the first
  fast stroke belong to the rally; one-way motion does not (v8: >= 1
  reversal, a soft serve and its fast return are already one).
- v8 lone flight (no toss, one ball run, nothing else moving) is not a
  rally; a high ball also crossing >= 0.4 W is a pop-up, not a toss; a ball
  that just entered from the frame edge is not served; rally_state keeps a
  frame-rule episode whole up to its last stroke.
User-confirmed labeling conventions (start at bounce or toss, let optional,
serve fault counts, hand-back / ball pick-up is not play) live in
docs/evaluation.md; check `just eval run --compare <baseline> --gate`.
"""

VERSION='frame-serve-v8'

# Stroke: horizontal monotone run. *_DX in W, *_SPEED in S (see above).
STROKE_DX=.29;STROKE_SPEED=.37
EDGE=.06             # frame fraction: a run entering from the frame edge
SERVE_SPEED=.21      # first stroke after a toss (perspective-slowed serve)
OPEN_SPEED=.64       # a stroke without a toss must be this fast to open
# Toss: mostly vertical run near where the serve then starts (TOSS_DY /
# TOSS_NEAR in W; TOSS_RATIO compares physical scales, dimensionless).
TOSS_DY=.29;TOSS_RATIO=1.5;TOSS_LINK=2.5;TOSS_NEAR=.29;TOSS_BREAK_GAP=1.0
# A toss stays at the server: a high ball also travelling >= TOSS_MAX_DX W
# across is a pop-up / lob after play, not a toss (same results 0.29-0.5 W).
TOSS_MAX_DX=.4
# No toss and the ball entered from the frame edge <= THROWN_IN_GAP s before:
# not a serve (same results 0.8-3 s, edge run 0.1-0.6 W).
THROWN_IN_GAP=1.5
# Lone flight: a toss-less episode with a single ball run >= LONE_DX W and
# nothing else is dropped (same results 0.06-0.2 W; no labeled rally lost).
LONE_DX=.12
# Weak motion keeps a rally alive across short tracking gaps.
WEAK_DX=.06;WEAK_SPEED=.11;WEAK_GAP=.8
# Scale calibration: runs moving >= CAL_FLOOR frame widths; S from runs >=
# CAL_LONG * W. Too few runs: no calibration, the rule does not run.
CAL_FLOOR=.05;CAL_SPAN_Q=.9;CAL_SPEED_Q=.75;CAL_LONG=.3
STROKE_GAP=1.8;BRIDGE_GAP=3.0
DEAD_DRIFT_SECONDS=1.0;DEAD_DRIFT_SPEED=.33;DRIFT_ATTACK_GAP=.5
TOSS_LEAD=1.2;NO_TOSS_LEAD=1.0;TAIL=.8
# Serve preparation: the server bounces the ball (on the table or floor) a few
# times before serving. A bounce burst is >= 3 alternating short vertical runs
# (each 0.06-0.6 W, little horizontal drift, <= 0.35 s apart, same spot). If
# one ends within PREP_WINDOW s before the serve (toss, else first stroke), on
# the server's side and after the previous rally, the rally starts there:
# viewers see the preparation. Not seen: the usual toss / stroke lead.
BOUNCE_DY=(.06,.6);BOUNCE_DRIFT=.5;BOUNCE_GAP=.35;BOUNCE_SPOT=.2;BOUNCE_MIN=3
PREP_WINDOW=8.0;PREP_PAD=.2
# Soft lead-in: a rally may open with slow strokes (soft serve, pushes) below
# the stroke speed calibrated on the video's fast play. Once a rally is open,
# its start moves back over the directly preceding chain of horizontal runs
# (each >= LEAD_DX W and >= WEAK_SPEED S, gaps <= WEAK_GAP s) when that chain
# goes back and forth at least LEAD_REVERSALS times (a soft serve then the
# first fast return is one reversal): a ball carried back one way is not
# play, and a hand-back to the server is followed by a pause (catch, toss)
# longer than WEAK_GAP. Same counts for LEAD_DX 0.04-0.12 W on all labeled
# videos (v8).
LEAD_DX=.08;LEAD_REVERSALS=1
# Video-level gate: share of long ball runs that move mainly horizontally.
VIEW_MIN_RUNS=40;VIEW_RUN=.12;VIEW_HORIZONTAL=.7


def _runs(points,lo,hi):
    from rally_transits import ball_runs
    points=[p for p in points if lo<=p[0]<hi]
    out=[]
    for run in ball_runs(points):
        if len(run)<3:continue
        elapsed=run[-1][0]-run[0][0]
        if elapsed<=0:continue
        xs=[p[1] for p in run];ys=[p[2] for p in run]
        dx=abs(xs[-1]-xs[0])
        out.append({'t0':run[0][0],'t1':run[-1][0],'x0':xs[0],'x1':xs[-1],'dx':dx,
                    'speed':dx/elapsed,'dy':max(ys)-min(ys),'dy_signed':ys[-1]-ys[0]})
    return out


def _vertical_pieces(points,ratio):
    """Vertical monotone pieces; positions in frame widths (y * ratio)."""
    out=[];piece=[];direction=0
    def close():
        if len(piece)>=3 and piece[-1][0]>piece[0][0]:
            xs=[p[1] for p in piece];ys=[p[2]*ratio for p in piece]
            out.append({'t0':piece[0][0],'t1':piece[-1][0],'x':sum(xs)/len(xs),
                        'dy':ys[-1]-ys[0],'drift':max(xs)-min(xs)})
    for p in points:
        if piece:
            step=(p[2]-piece[-1][2])*ratio
            moving=abs(step)>.002
            # Direction of the last real movement (repeated frames do not
            # hide the turn at the bottom / top of a bounce).
            reversal=moving and direction and (step>0)!=(direction>0)
            if p[0]-piece[-1][0]>.15 or reversal:
                close();piece=[piece[-1]] if reversal else [];direction=0
            if moving:direction=step
        piece.append(p)
    close()
    return out


def bounce_bursts(normalized,lo,hi,span,ratio):
    """[(t0, t1, x)] bursts of short alternating vertical runs at one spot."""
    pieces=sorted((v for points in normalized for v in _vertical_pieces([p for p in points if lo<=p[0]<hi],ratio)
                   if BOUNCE_DY[0]*span<=abs(v['dy'])<=BOUNCE_DY[1]*span and v['drift']<=BOUNCE_DRIFT*abs(v['dy'])),
                  key=lambda v:v['t0'])
    bursts=[];run=[]
    for v in pieces:
        if run and v['t0']-run[-1]['t1']<=BOUNCE_GAP and (v['dy']>0)!=(run[-1]['dy']>0) and abs(v['x']-run[-1]['x'])<=BOUNCE_SPOT*span:
            run.append(v);continue
        if len(run)>=BOUNCE_MIN:bursts.append((run[0]['t0'],run[-1]['t1'],run[0]['x']))
        run=[v]
    if len(run)>=BOUNCE_MIN:bursts.append((run[0]['t0'],run[-1]['t1'],run[0]['x']))
    return bursts


def _normalized(tracks,track_size):
    sx,sy=track_size
    return [[(p[0],p[1]/sx,p[2]/sy) for p in track.points] for track in tracks]


def calibrate(tracks,track_size=(960,540)):
    """(S, W) of this video's ball runs, or None without enough evidence."""
    runs=[run for points in _normalized(tracks,track_size) for run in _runs(points,-1,float('inf'))
          if run['dx']>=CAL_FLOOR]
    if len(runs)<VIEW_MIN_RUNS:return None
    quantile=lambda values,q:sorted(values)[int(q*(len(values)-1))]
    span=quantile([run['dx'] for run in runs],CAL_SPAN_Q)
    long=[run['speed'] for run in runs if run['dx']>=CAL_LONG*span]
    return quantile(long,CAL_SPEED_Q),span


def horizontal_view(tracks,track_size=(960,540)):
    """True when long ball runs mostly travel along the image x axis.

    End-on (broadcast behind the server) views move the ball along y; the
    frame-space x rule must not run there.
    """
    total=horizontal=0
    for points in _normalized(tracks,track_size):
        for run in _runs(points,-1,float('inf')):
            # 16:9 frame: compare displacements in the same physical scale.
            dx=run['dx'];dy=abs(run['dy_signed'])*9/16
            if max(dx,dy)<VIEW_RUN:continue
            total+=1;horizontal+=dx>2*dy
    return total>=VIEW_MIN_RUNS and horizontal/total>=VIEW_HORIZONTAL


def _inside(run):return EDGE<run['x0']<1-EDGE


def episodes(tracks,lo,hi,track_size=(960,540),scale=None):
    """[(start, end, end_reason, first_stroke, serve_prep)] inside [lo, hi).

    scale: (S, W) from calibrate() over the whole video; computed here when
    omitted. No calibration evidence: no episodes.
    """
    scale=scale or calibrate(tracks,track_size)
    if not scale:return []
    speed,span=scale
    stroke_dx,toss_dy,toss_near,weak_dx=(k*span for k in (STROKE_DX,TOSS_DY,TOSS_NEAR,WEAK_DX))
    stroke_speed,serve_speed,open_speed,weak_speed=(k*speed for k in (STROKE_SPEED,SERVE_SPEED,OPEN_SPEED,WEAK_SPEED))
    toss_max_dx=TOSS_MAX_DX*span
    _toss=lambda run:run['dy']>=toss_dy and run['dy']>=TOSS_RATIO*run['dx'] and run['dx']<toss_max_dx
    normalized=_normalized(tracks,track_size)
    items=sorted((run for points in normalized for run in _runs(points,lo,hi)),
                 key=lambda run:(run['t0'],run['t1']))
    bursts=bounce_bursts(normalized,lo,hi,span,track_size[1]/track_size[0])
    tosses=[run for run in items if _toss(run)]

    def tossed(run,after=None):
        for toss in tosses:
            if (run['t0']-TOSS_LINK<=toss['t0']<=run['t0'] and abs(toss['x1']-run['x0'])<=toss_near and
                    (after is None or toss['t0']>after)):return toss
        return None

    groups=[];current=None
    for run in items:
        stroke=run['dx']>=stroke_dx and _inside(run)
        strong=stroke and run['speed']>=stroke_speed
        weak=run['dx']>=weak_dx and run['speed']>=weak_speed
        idle=current is None or run['t0']-current['last']>BRIDGE_GAP
        if stroke and not strong and run['speed']>=serve_speed and idle and tossed(run):strong=True
        # A long slow drift after the strokes is the ball rolling / carried
        # back, not play: in play the ball crosses within about a second.
        # It stays pending: an attack straight off that slow ball (a fast
        # stroke right after it) proves the ball was still in play.
        if (current and run['t1']-run['t0']>=DEAD_DRIFT_SECONDS and run['speed']<DEAD_DRIFT_SPEED*speed and
                run['dx']>=weak_dx and run['t0']>=current['last']-.05):
            current['drift']=run['t1'];continue
        if current and current.get('drift') is not None:
            if strong and run['speed']>=open_speed and run['t0']-current['drift']<=DRIFT_ATTACK_GAP:
                current['drift']=None;current['weak']=max(current['weak'],run['t0'])
            elif strong or run['t0']-current['drift']>DRIFT_ATTACK_GAP:
                groups.append(current);current=None
        if current and _toss(run) and 0<=run['t0']-current['weak']<=WEAK_GAP and run['t0']-current['last']<=BRIDGE_GAP:
            # High ball in play (lob, steep block): vertical motion straight
            # after in-play motion keeps the chain and is not a new toss.
            current['weak']=max(current['weak'],run['t1']);current.setdefault('lobs',[]).append(run['t0'])
        if current and strong:
            gap=run['t0']-current['last']
            toss=tossed(run,current['last'])
            new_serve=gap>=TOSS_BREAK_GAP and toss is not None and toss['t0'] not in current.get('lobs',())
            if not new_serve and (gap<=STROKE_GAP or (gap<=BRIDGE_GAP and run['t0']-current['weak']<=WEAK_GAP)):
                current['last']=max(current['last'],run['t1']);current['weak']=max(current['weak'],current['last']);continue
        elif current and weak:
            if run['t0']-current['weak']<=WEAK_GAP and run['t0']-current['last']<=BRIDGE_GAP:
                current['weak']=max(current['weak'],run['t1'])
            continue
        if not strong:continue
        toss=tossed(run)
        if not toss and run['speed']<open_speed:continue
        if not toss and any(not _inside(r) and r['dx']>=stroke_dx and 0<=run['t0']-r['t1']<=THROWN_IN_GAP
                            for r in items if run['t0']-THROWN_IN_GAP-1<r['t1']<=run['t0']+1e-6):
            # The ball just came in from the frame edge (thrown / hit over
            # from outside): hitting it on is not a serve.
            continue
        if current:groups.append(current)
        current={'first':run['t0'],'last':run['t1'],'weak':run['t1'],'toss':toss['t0'] if toss else None,
                 'serve':(run['x0'],run['x1'])}
    if current:groups.append(current)
    lead_dx=LEAD_DX*span;lone_dx=LONE_DX*span

    def lead_in(group,floor):
        if group['toss'] is not None:return None
        t=group['first'];x0,x1=group['serve'];direction=x1>x0;reversals=0;earliest=None
        for run in reversed([r for r in items if r['t1']<=group['first']+1e-6 and r['t0']>=floor]):
            if t-run['t1']>WEAK_GAP:break
            if run['dx']<lead_dx or run['speed']<weak_speed or not _inside(run):continue
            way=run['x1']>run['x0']
            if way!=direction:reversals+=1;direction=way
            earliest=run;t=run['t0']
        return earliest if earliest is not None and reversals>=LEAD_REVERSALS else None

    out=[];floor=lo
    for group in groups:
        lead=lead_in(group,floor)
        if lead is not None:
            toss=tossed(lead,floor)
            group['first']=lead['t0'];group['toss']=toss['t0'] if toss else None
        start=max(floor,group['toss']-TOSS_LEAD if group['toss'] is not None else group['first']-NO_TOSS_LEAD)
        serve=group['toss'] if group['toss'] is not None else group['first']
        x0,x1=group['serve'];middle=(x0+x1)/2
        prep=[b for b in bursts if b[0]>=floor and serve-PREP_WINDOW<=b[1]<=serve and (b[2]-middle)*(x0-middle)>0]
        if prep:start=max(floor,min(start,prep[0][0]-PREP_PAD))
        end=min(hi,group['last']+TAIL)
        if end-start<.2:continue
        if group['toss'] is None and not prep:
            # Lone flight: no toss, one stroke and no other ball motion at
            # all (no receive, no bounce, no weak return): a single ball hit
            # back / away between points, not a rally.
            moving=[r for r in items if group['first']-1e-6<=r['t0']<end and r['dx']>=lone_dx]
            if len(moving)<=1:continue
        reason='' if hi-group['last']<STROKE_GAP else 'stroke_gap'
        out.append((start,end,reason,group['first'],bool(prep)));floor=end
    return out
