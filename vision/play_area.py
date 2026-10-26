"""Mark ball tracks far from where this video's play happens (display only).

Full-frame detection also finds balls lying on the floor, in a corner of the
hall or on a neighbouring court. They are real detections and stay in the
result, but they are not the ball in play, so the overlay should not draw them.

No table geometry is needed and nothing is tuned to a particular video:

- Scale comes from the video's own ball runs (physical frame units, so zoom,
  camera distance and play direction do not matter): L is the 90th percentile
  run travel (about one table length in the image), S the 75th percentile
  speed of long runs (a typical stroke).
- A stroke track has a run travelling >= 0.29 L at >= 0.37 S (the same
  relative stroke definition as rally_serves). Stroke tracks are never marked.
- The local play area is the 5-95 % extent of stroke-track points within
  +-45 s (it follows a moving camera). A non-stroke track whose median position
  lies more than 0.2 L outside it is marked off-play. Without enough stroke
  evidence nearby nothing is marked.

Rally rules do not use this mark: on all labelled footage removing these
tracks left every rally unchanged, so they keep reading every track.
"""
import bisect

VERSION='play-area-v1'

CAL_FLOOR=.05;CAL_SPAN_Q=.9;CAL_LONG=.3;CAL_SPEED_Q=.75;CAL_MIN_RUNS=40
STROKE_TRAVEL=.29;STROKE_SPEED=.37
WINDOW=45.0;AREA_Q=.05;MIN_AREA_POINTS=30
OFF_PLAY=.2


def _runs(track,track_size):
    from rally_transits import ball_runs
    sx,_=track_size
    # Both axes in frame widths: distances and speeds are physical in the image.
    points=[(p[0],p[1]/sx,p[2]/sx) for p in track.points]
    out=[]
    for run in ball_runs(points):
        if len(run)<3:continue
        elapsed=run[-1][0]-run[0][0]
        if elapsed<=0:continue
        xs=[p[1] for p in run];ys=[p[2] for p in run]
        travel=((max(xs)-min(xs))**2+(max(ys)-min(ys))**2)**.5
        out.append((travel,travel/elapsed))
    return out


def _quantile(values,q):
    values=sorted(values);return values[int(q*(len(values)-1))]


def off_play_tracks(tracks,track_size=(960,540)):
    """Set of track ids to hide from the ball overlay."""
    runs={track.id:_runs(track,track_size) for track in tracks}
    every=[run for items in runs.values() for run in items if run[0]>=CAL_FLOOR]
    if len(every)<CAL_MIN_RUNS:return set()
    span=_quantile([travel for travel,_ in every],CAL_SPAN_Q)
    speed=_quantile([v for travel,v in every if travel>=CAL_LONG*span],CAL_SPEED_Q)
    strokes={tid for tid,items in runs.items()
             if any(travel>=STROKE_TRAVEL*span and v>=STROKE_SPEED*speed for travel,v in items)}
    sx,_=track_size
    area=sorted((p[0],p[1]/sx,p[2]/sx) for track in tracks if track.id in strokes for p in track.points)
    times=[p[0] for p in area]
    marked=set()
    for track in tracks:
        if track.id in strokes or not track.points:continue
        middle=track.points[len(track.points)//2][0]
        local=area[bisect.bisect_left(times,middle-WINDOW):bisect.bisect_right(times,middle+WINDOW)]
        if len(local)<MIN_AREA_POINTS:continue
        xs=[p[1] for p in local];ys=[p[2] for p in local]
        x0,x1=_quantile(xs,AREA_Q),_quantile(xs,1-AREA_Q)
        y0,y1=_quantile(ys,AREA_Q),_quantile(ys,1-AREA_Q)
        cx=_quantile([p[1]/sx for p in track.points],.5);cy=_quantile([p[2]/sx for p in track.points],.5)
        outside=max(x0-cx,cx-x1,y0-cy,cy-y1,0.0)
        if outside>OFF_PLAY*span:marked.add(track.id)
    return marked
