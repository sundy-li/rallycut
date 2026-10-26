"""Perspective-view activity segmentation, NOT net/out adjudication.

Only optional, trusted perspective geometry enables this auxiliary rule. All
model points/tracks are retained. Require a serve-like toss or reciprocal fast
transits to start; a lone return toss is not play. Sustained slow low motion or
a genuine observation gap closes an episode without inventing a net fault.
"""
from collections import deque
import statistics

from rally_serves import calibrate,episodes as serve_episodes,horizontal_view
from rally_transits import episodes as transit_episodes,side_view


def _episodes(points,bounds,lo,hi):
    left,top,right,bottom=bounds;width=right-left;height=bottom-top
    # Analysis-only corridor, never a detector/tracker ROI.
    points=[p for p in points if left-width*.25<=p[1]<=right+width*.25 and
            top-height*1.8<=p[2]<=bottom+height*.35]
    history=deque();flight_history=deque();pivot=None;transit=None;active=None;last=None;pending=None
    episodes=[];seed_end=-1;continuous_start=lo;first_fast=None
    for point in points:
        t,x,y,_=point
        if last and t-last[0]>.5:continuous_start=t;first_fast=None
        if last and t-last[0]>.8:
            if active is not None:episodes.append((active,min(hi,last[0]+.12),'activity_gap'))
            active=None;pending=None;history.clear();pivot=None;transit=None
        history.append(point);flight_history.append(point)
        while flight_history and t-flight_history[0][0]>3:flight_history.popleft()
        while history and t-history[0][0]>.95:history.popleft()
        seed=None
        # A real upward toss followed by descent at a player end. Small hand
        # bounces during preparation and blobs at a neighbouring table fail.
        recent=[p for p in history if left-width*.18<=p[1]<=right+width*.18 and
                ((x<left+width*.27 and p[1]<left+width*.27) or
                 (x>right-width*.27 and p[1]>right-width*.27))]
        if (len(recent)>=6 and .25<=recent[-1][0]-recent[0][0]<=.95 and
            all(b[0]-a[0]<.3 for a,b in zip(recent,recent[1:]))):
            apex=min(range(len(recent)),key=lambda i:recent[i][2]);launch=0
            for i in range(apex):
                if (i==0 or recent[i][2]>=recent[i-1][2]) and recent[i][2]>recent[i+1][2]:launch=i
            a=recent[launch];b=recent[apex]
            near_end=(x<left+width*.27 or x>right-width*.27)
            if (near_end and left-width*.18<=x<=right+width*.18 and 0<apex<len(recent)-1 and
                a[2]-b[2]>height*.35 and y-b[2]>height*.12 and b[2]<top-height*.25 and
                max(p[1] for p in recent)-min(p[1] for p in recent)<width*.4):
                seed=a[0]
        toss_seed=seed is not None
        zone=(-1 if x<left+width*.30 else 1 if x>right-width*.30 else 0) if left-width*.18<=x<=right+width*.18 and y>=top-height*.35 else 0
        fast=False
        if zone:
            if pivot and zone!=pivot[1]:
                dt=t-pivot[0][0]
                if 0<dt<=.65 and abs(x-pivot[0][1])>=width*.40:
                    fast=True
                    if first_fast is None:first_fast=pivot[0][0]
                    if transit and transit[2]!=zone and pivot[0][0]-transit[1]<2.5:
                        seed=transit[0] if seed is None else min(seed,transit[0])
                    transit=(pivot[0][0],t,zone)
            pivot=(point,zone)
        if active is None and seed is not None:
            if first_fast is not None and first_fast>=continuous_start and t-first_fast<3:
                prior=[p for p in flight_history if first_fast<=p[0]<seed]
                curved=prior and max(p[2] for p in prior)-min(p[2] for p in prior)>height*.3
                if not toss_seed or curved:seed=min(seed,first_fast)
            active=max(lo,seed-.12);seed_end=t;pending=None
        if active is not None:
            # A slow bounce can be followed by a quick local return BEFORE the
            # next complete cross-table transit. Cancel a pending stop on that
            # sustained displacement, not on a single noisy point. All samples
            # and elapsed time are actual source PTS, independent of nominal FPS.
            recovery=[p for p in history if t-p[0]<=.18]
            resumed=False
            if pending and len(recovery)>=4 and recovery[-1][0]-recovery[0][0]>=.08:
                a,b=recovery[0],recovery[-1]
                # Vertical acceleration alone may be a dead ball dropping to
                # the floor. Require directional horizontal recovery instead.
                displacement=abs(b[1]-a[1])
                speeds=[abs(b[1]-a[1])/(b[0]-a[0])
                        for a,b in zip(recovery,recovery[1:]) if b[0]>a[0]]
                resumed=(displacement>width*.08 and bool(speeds) and statistics.median(speeds)>width*.85)
            if fast or seed is not None or resumed:seed_end=t;pending=None
            slow=[p for p in history if t-p[0]<=.6]
            # Slow, low, central ball after actual play; above-table lobs and
            # low defensive recovery are not enough. Wait for fast recovery.
            if (pending is None and t-seed_end>.25 and len(slow)>=8 and
                slow[-1][0]-slow[0][0]>=.5 and
                all(top-height*.30<=p[2]<=bottom+height*.3 for p in slow) and
                max(p[2] for p in slow)-min(p[2] for p in slow)<height*.65 and
                max(p[1] for p in slow)-min(p[1] for p in slow)<width*.30 and
                left+width*.25<x<right-width*.20):
                speeds=[abs(b[1]-a[1])/(b[0]-a[0]) for a,b in zip(slow,slow[1:]) if b[0]>a[0]]
                if speeds and statistics.median(speeds)<width*.85:
                    pending=(slow[0][0],t+.3)
            if pending and t>=pending[1]:
                # The beginning of a slow window is NOT an observed rally end.
                # Backdating there cuts the final stroke/bounce. Keep evidence
                # through the frame which actually confirms sustained settling.
                episodes.append((active,min(t,hi),'ball_settled'))
                active=None;pending=None;history.clear();pivot=None;transit=None;first_fast=None
        last=point
    if active is not None and last:episodes.append((active,min(hi,last[0]+.12) if hi-last[0]>.8 else hi,'activity_gap' if hi-last[0]>.8 else ''))
    return [(a,b,reason) for a,b,reason in episodes if b-a>=.2]


def _perspective(segment):return segment.get('method')=='perspective-rims' and bool(segment.get('bounds'))


def frame_rule_active(tracks,segments,limit,track_size=(960,540)):
    """Whether segments without trusted geometry use the frame-space rule.

    Needs such a segment, play along the image x axis (the rule's own
    assumption) and enough ball runs to calibrate its scale.
    """
    if limit<=0 or not any(not side_view(s) for s in segments):return False
    return horizontal_view(tracks,track_size) and calibrate(tracks,track_size) is not None


def activity_intervals(tracks,segments,limit,track_size=(960,540)):
    """Return source intervals; unsupported/unknown geometry fails open.

    Per segment, strongest evidence first: trusted side-view geometry uses
    cross-table transits (rally_transits); any other segment (perspective box,
    moving camera, no geometry) uses self-calibrated frame-space strokes and
    serve tosses (rally_serves) when play runs along the image x axis. Only
    when that rule cannot run (e.g. end-on views) does a perspective box use
    the toss/reciprocal/settling evidence below; otherwise fail open. On the
    one labelled fixed perspective clip (0044) the frame rule had 5 false
    positives where this perspective rule had 11, same recall.
    """
    perspective=_perspective
    frame_view=frame_rule_active(tracks,segments,limit,track_size)
    scale=calibrate(tracks,track_size) if frame_view else None
    if not frame_view and not any(perspective(s) or side_view(s) for s in segments):
        return [(0,limit,None,None)]
    by_time={}
    if any(perspective(s) for s in segments):
        sx,sy=track_size
        for track in tracks:
            for t,x,y,score in track.points:
                if t<=limit and (t not in by_time or score>by_time[t][3]):by_time[t]=(t,x/sx,y/sy,score)
    points=sorted(by_time.values())
    out=[];span=None
    def flush():
        # One pass over consecutive frame-space segments: geometry churn
        # (drift follow / re-probe) must not split a rally.
        if span:
            for a,b,reason,first,prep in serve_episodes(tracks,span[0],span[1],track_size,scale):
                out.append((a,b,'serve_prep' if prep else 'live_ball_evidence',reason or None,first,'frame'))
    for segment in segments:
        lo,hi=segment['start'],min(segment.get('end',limit),limit)
        if hi<=lo:continue
        bounds=segment.get('bounds')
        if frame_view and not side_view(segment):
            if span and abs(span[1]-lo)<1e-6:span=(span[0],hi)
            else:
                flush();span=(lo,hi)
            continue
        flush();span=None
        if side_view(segment):
            # 5th field: first transit time (the lead before it is not evidence).
            for a,b,reason,first in transit_episodes(tracks,bounds,lo,hi,track_size):
                out.append((a,b,'live_ball_evidence',reason or None,first))
            continue
        if not perspective(segment):
            if out and out[-1][2:] == (None,None) and abs(out[-1][1]-lo)<1e-6:
                out[-1]=(out[-1][0],hi,None,None)
            else:out.append((lo,hi,None,None))
            continue
        local=[p for p in points if lo<=p[0]<hi]
        for a,b,reason in _episodes(local,bounds,lo,hi):out.append((a,b,'live_ball_evidence',reason or None))
    flush()
    return out
