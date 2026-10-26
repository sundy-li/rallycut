"""Cheap shot detection and OPTIONAL geometry; neither gates ball inference.

The decode thread returns an immutable snapshot with each source frame. The
consumer never observes producer-ahead mutable Shot objects. Geometry is sampled
on live frames, fails open, and is cleared immediately on camera cuts.
"""
from dataclasses import dataclass
import math

THUMB_SIZE=(32,18)
MAD_CUT=9.0
MAD_STRONG=18.0
HIST_CUT=.10
# A real cut changes (almost) the whole picture. Someone walking right past a
# fixed camera also moves MAD/histogram past the cut limits, but leaves part of
# the static hall unchanged: on five fixed-camera clips (0041-0045) every such
# candidate changed <=67% of a 3x4 grid (cell MAD >= 9); broadcast hard cuts
# changed 100%.
COVER_GRID=(3,4)
COVER_MAD=9.0
COVER_FRACTION=.8
# Camera motion is not a cut. The strided probe aliases a hand-held / panning
# camera's few-pixel shift into cut-sized differences (spectator clip: 467
# "cuts" in 52 min, median 1.4 s apart). A candidate must still differ after
# compensating global translation on an anti-aliased 128x72 image. On 1200 s of
# Olympic broadcast the 143 single-frame hard cuts keep >=18.1 (median 42.8);
# hand-held shake on the spectator clip: median 9.6, 90th percentile 16.6.
ALIGN_SIZE=(128,72)
ALIGNED_CUT=15.0
# Geometry that survives camera motion must not go stale: once the picture has
# shifted >3% from where the table was found (two checks 1 s apart), move the
# table / net by the same global shift; if that would leave the frame or the
# shift is beyond reliable alignment, clear it and probe again. Neither is a
# cut: tracks and model windows continue.
DRIFT_CHECK_SECONDS=1.0
DRIFT_FRACTION=.03
DRIFT_CONFIRM=2
MIN_SHOT_SECONDS=1.0
MIN_SAMPLES=3
MIN_SAMPLE_SPAN=2.0
MAX_SAMPLE_SECONDS=9.0
RETRY_SECONDS=30.0


def thumbnail(frame):
    import cv2
    # AREA-resizing a 4K frame down to 32x18 cost ~1.7ms/frame (measured in the
    # 0043 profile). A strided subsample keeps the same cut statistics for ~10x
    # less time; the final 32x18 AREA pass only touches a 64x36 buffer.
    height,width=frame.shape[:2]
    step_y=max(1,height//36)
    step_x=max(1,width//64)
    small=frame[::step_y,::step_x]
    if small.shape[0]<18 or small.shape[1]<32:
        small=cv2.resize(small,THUMB_SIZE,interpolation=cv2.INTER_AREA)
    grey=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
    grey=cv2.resize(grey,THUMB_SIZE,interpolation=cv2.INTER_AREA)
    hist=cv2.calcHist([grey],[0],None,[32],[0,256]);cv2.normalize(hist,hist)
    return grey.astype('float32'),hist


def is_cut(previous,current):
    import cv2
    import numpy as np
    if previous is None or current is None:return False
    mad=float(np.mean(np.abs(current[0]-previous[0])))
    if not math.isfinite(mad) or mad<MAD_CUT:return False
    distance=float(cv2.compareHist(previous[1],current[1],cv2.HISTCMP_BHATTACHARYYA))
    if distance<HIST_CUT and mad<MAD_STRONG:return False
    rows,cols=COVER_GRID
    height,width=current[0].shape
    cells=np.abs(current[0]-previous[0]).reshape(rows,height//rows,cols,width//cols).mean(axis=(1,3))
    return float(np.mean(cells>=COVER_MAD))>=COVER_FRACTION


_WINDOW=[]


def motion_probe(frame):
    """Anti-aliased grey image for global-motion estimates (only on demand)."""
    import cv2
    grey=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY) if frame.ndim==3 else frame
    return cv2.resize(grey,ALIGN_SIZE,interpolation=cv2.INTER_AREA).astype('float32')


def global_shift(previous,current):
    """(dx, dy) moving `previous` onto `current`, in ALIGN_SIZE pixels."""
    import cv2
    if not _WINDOW:_WINDOW.append(cv2.createHanningWindow(ALIGN_SIZE,cv2.CV_32F))
    # OpenCV 4.11 phaseCorrelate windows its inputs in place; never hand it
    # cached probes (the previous frame / the geometry anchor are reused).
    (dx,dy),_=cv2.phaseCorrelate(previous.copy(),current.copy(),_WINDOW[0])
    return dx,dy


def aligned_difference(previous,current):
    """Mean grey difference left after compensating global translation."""
    import cv2
    import numpy as np
    dx,dy=global_shift(previous,current)
    width,height=ALIGN_SIZE
    if not (math.isfinite(dx) and math.isfinite(dy)) or abs(dx)>=width/4 or abs(dy)>=height/4:
        return math.inf  # no trustworthy overlap: keep the cut
    moved=cv2.warpAffine(previous,np.float32([[1,0,dx],[0,1,dy]]),ALIGN_SIZE,
                         flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    mx=max(4,math.ceil(abs(dx))+2);my=max(4,math.ceil(abs(dy))+2)
    return float(np.mean(np.abs(moved-current)[my:height-my,mx:width-mx]))


def _follow(state,fx,fy):
    """Geometry moved by a global shift (fractions of the frame), or None."""
    if not (math.isfinite(fx) and math.isfinite(fy)) or abs(fx)>=.25 or abs(fy)>=.25:return None
    left,top,right,bottom=state.bounds
    bounds=(left+fx*960,top+fy*540,right+fx*960,bottom+fy*540)
    if bounds[0]<0 or bounds[1]<0 or bounds[2]>960 or bounds[3]>540:return None
    net=()
    if len(state.net)==6:
        net=tuple(round(v+(fx if i%3==0 else fy),6) for i,v in enumerate(state.net))
        if not all(0<=v<=1 for v in net):net=()
    return ShotSnapshot(state.shot_id,state.shot_start,tuple(round(v,3) for v in bounds),net,state.method)


@dataclass(frozen=True)
class ShotSnapshot:
    shot_id:int
    shot_start:float
    bounds:tuple=()
    net:tuple=()
    method:str='unavailable'


class ShotMonitor:
    def __init__(self,geometry=True,initial=None):
        self.previous=None
        self.cuts=[]
        self.last_cut=0.0
        self.state=ShotSnapshot(0,0.0)
        self.geometry=geometry;self.warnings=[]
        self.samples=[];self.net_samples=[]
        self.probe_start=0.0;self.next_probe=0.0
        self.events=[(0.0,self.state)]
        # Camera-motion bookkeeping (frames are only referenced, never copied).
        self.previous_frame=None;self.previous_motion=None
        self.motion_vetoes=0;self.drift_follows=0;self.drift_resets=0
        self.anchor=None;self.next_drift=0.0;self.drift_hits=0
        if initial:
            self.state=ShotSnapshot(0,0.0,tuple(initial['bounds']),tuple(initial.get('net_region',[])),initial['method'])
            self.events=[(0.0,self.state)]

    def _restart_probe(self,timestamp):
        self.samples=[];self.net_samples=[]
        self.probe_start=timestamp;self.next_probe=timestamp
        self.anchor=None;self.drift_hits=0

    def push(self,timestamp,frame):
        probe=thumbnail(frame);motion=None
        if timestamp-self.last_cut>=MIN_SHOT_SECONDS and is_cut(self.previous,probe):
            before=self.previous_motion
            if before is None and self.previous_frame is not None:before=motion_probe(self.previous_frame)
            motion=motion_probe(frame)
            if before is not None and aligned_difference(before,motion)<ALIGNED_CUT:
                self.motion_vetoes+=1
            else:
                self.last_cut=timestamp;self.cuts.append(timestamp)
                self.state=ShotSnapshot(self.state.shot_id+1,timestamp)
                self.events.append((timestamp,self.state))
                self._restart_probe(timestamp)
        self.previous=probe;self.previous_frame=frame;self.previous_motion=motion
        if self.state.bounds and timestamp>=self.next_drift:
            self.next_drift=timestamp+DRIFT_CHECK_SECONDS
            current=motion if motion is not None else motion_probe(frame)
            if self.anchor is None:self.anchor=current
            else:
                dx,dy=global_shift(self.anchor,current)
                width,height=ALIGN_SIZE
                moved=not (abs(dx)<=DRIFT_FRACTION*width and abs(dy)<=DRIFT_FRACTION*height)
                self.drift_hits=self.drift_hits+1 if moved else 0
                if self.drift_hits>=DRIFT_CONFIRM:
                    # Same shot, geometry no longer where it was found.
                    followed=_follow(self.state,dx/width,dy/height)
                    if followed:
                        self.state=followed;self.anchor=current;self.drift_hits=0
                        self.drift_follows+=1
                    else:
                        self.state=ShotSnapshot(self.state.shot_id,self.state.shot_start)
                        self.drift_resets+=1;self._restart_probe(timestamp)
                    self.events.append((timestamp,self.state))
        if not self.geometry or self.state.bounds or timestamp<self.next_probe:return self.state
        import cv2
        from table_locator import candidates,stable_table
        from net_geometry import side_net_region
        try:
            resized=cv2.resize(frame,(960,540),interpolation=cv2.INTER_AREA)
            items=candidates(resized)
            self.samples.append((timestamp,items))
            net=side_net_region(resized,items[0]['bounds'],items[0]['method']) if items else []
            if net:self.net_samples.append(net)
            found=stable_table(self.samples,minimum_observations=MIN_SAMPLES,minimum_span=MIN_SAMPLE_SPAN)
        except (cv2.error,ValueError,ArithmeticError) as error:
            if len(self.warnings)<8:self.warnings.append('可选桌面几何失败，球检测继续：'+str(error)[:160])
            self.samples=[];self.net_samples=[]
            self.probe_start=timestamp+RETRY_SECONDS;self.next_probe=self.probe_start
            return self.state
        if found:
            import statistics
            stable=[n for n in self.net_samples if sum(max(abs(a-b) for a,b in zip(n,other))<.025 for other in self.net_samples)>=3]
            net=tuple(round(statistics.median(n[i] for n in stable),6) for i in range(6)) if stable else ()
            self.state=ShotSnapshot(self.state.shot_id,self.state.shot_start,tuple(found['bounds']),net,found['method'])
            self.events.append((timestamp,self.state))
            self.samples=[];self.net_samples=[]
        elif timestamp-self.probe_start>=MAX_SAMPLE_SECONDS:
            self.samples=[];self.net_samples=[]
            self.probe_start=timestamp+RETRY_SECONDS;self.next_probe=self.probe_start
        else:self.next_probe=timestamp+1.0
        return self.state

    def segments(self,duration):
        output=[]
        for index,(start,state) in enumerate(self.events):
            end=self.events[index+1][0] if index+1<len(self.events) else duration
            if end<=start:continue
            bounds=state.bounds
            output.append({'start':round(start,6),'end':round(end,6),
                           'bounds':[round(bounds[0]/960,6),round(bounds[1]/540,6),round(bounds[2]/960,6),round(bounds[3]/540,6)] if bounds else [],
                           'net_region':list(state.net),'method':state.method})
        return output
