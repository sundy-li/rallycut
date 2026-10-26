"""Conservative ball-validity FSM; not an umpire or trained action recognizer.

IN_PLAY -> WAIT_SERVE on corroborated out/net/held-ball evidence. A return toss
is not a serve: the restart needs an own-half bounce toward the net, or sustained
reciprocal play if that bounce is occluded. Confirmed exclusions fence ALL later
visual/audio padding and merging. Coordinates are normalized to the video.
"""
from collections import deque
from bisect import bisect_right
import math
import os
from visual import SERVE_BOUNDARY_LEAD,Track,segment_rallies
from audio_features import fuse_audio_visual

VERSION='dead-ball-v1'


def validate_net_region(region):
    if region is None or region==[]:return
    if len(region)!=6 or not all(isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=1 for v in region):
        raise ValueError('net-region requires six normalized finite coordinates')
    if not region[0]<region[3] or not region[1]<region[2] or not region[4]<region[5]:
        raise ValueError('invalid net-region geometry')


class BallValidity:
    def __init__(self,table=None,net_line=None,geometry_method='side-color-rim'):
        self.left=self.top=self.right=self.bottom=self.width=self.height=self.mid=None
        self.side_view=False;self.net=None
        if table:
            self.left,self.top,self.right,self.bottom=table
            self.width=self.right-self.left;self.height=self.bottom-self.top
            self.side_view=geometry_method=='side-color-rim' and self.height>0 and self.width/self.height>4
            self.net=net_line if net_line and len(net_line) in (3,6) else None
            self.mid=(self.left+self.right)/2
        self.state='IN_PLAY'
        self.history=deque(maxlen=180);self.context=deque(maxlen=240)
        self.events=[];self.dead_intervals=[];self.pending=None;self.current_dead=None
        self.side=None;self.crossings=0;self.cross_time=None;self.target_seen_surface=False
        self.target_bounced=False;self.direction=0;self.last_point=None;self.last_end=-10

    def rebind(self,table=None,net_line=None,geometry_method='unavailable',timestamp=None):
        """Geometry loss/camera change is not a dead-ball or serve event."""
        previous_dead=self.current_dead if timestamp is None else None
        if self.current_dead is not None and timestamp is not None:
            self.current_dead['end']=max(self.current_dead['start'],timestamp)
            self.current_dead['resume_reason']='camera_cut'
        self.state='WAIT_SERVE' if previous_dead is not None else 'IN_PLAY'
        self.left=self.top=self.right=self.bottom=self.width=self.height=self.mid=None
        self.side_view=False;self.net=None
        if table:
            self.left,self.top,self.right,self.bottom=table
            self.width=self.right-self.left;self.height=self.bottom-self.top
            self.side_view=geometry_method=='side-color-rim' and self.height>0 and self.width/self.height>4
            self.net=net_line if net_line and len(net_line) in (3,6) else None
            self.mid=(self.left+self.right)/2
        self._reset_flight()
        self.target_bounced=False;self.last_point=None
        self.pending=None;self.current_dead=previous_dead
        self.history.clear();self.context.clear()

    def half(self,x):
        band=self.width*.025
        return -1 if x<self.mid-band else 1 if x>self.mid+band else 0

    def _net_at(self,x):
        if not self.net:return None
        if len(self.net)==3:
            return (self.net[1],self.net[2]) if abs(x-self.net[0])<=self.width*.07 else None
        left,lt,lb,right,rt,rb=self.net
        if not left<=x<=right:return None
        ratio=(x-left)/(right-left)
        return lt+(rt-lt)*ratio,lb+(rb-lb)*ratio

    def _reset_flight(self):
        self.side=None;self.crossings=0;self.cross_time=None
        self.target_seen_surface=False;self.target_bounced=False;self.direction=0

    def _event(self,kind,t,confirmed,reason,point,signals,confidence):
        result={'type':kind,'time':round(t,6),'confirmed_at':round(max(t,confirmed),6),
                'reason':reason,'confidence':confidence,'signals':signals,
                'x':round(point[1],6),'y':round(point[2],6)}
        self.events.append(result)
        return result

    def _dead(self,pending,now):
        end=pending['end']
        if self.state!='IN_PLAY' or end-self.last_end<.35:return
        event=self._event('dead_ball',end,now,pending['reason'],pending['point'],pending['signals'],pending['confidence'])
        self.state='WAIT_SERVE';self.last_end=end
        self.current_dead={'start':end,'end':None,'event':event}
        self.dead_intervals.append(self.current_dead)
        self.pending=None;self.history.clear();self.context.clear();self.last_point=None;self._reset_flight()

    def _restart(self,start,now,point,reason):
        if self.current_dead is None:return
        start=max(self.current_dead['start'],start)
        self.current_dead['end']=start
        self._event('restart',start,now,reason,point,['new_live_ball_evidence','dead_return_not_reused'],.72)
        self.current_dead=None
        self.state='IN_PLAY';self.pending=None
        self._reset_flight()

    def _has_active_flight(self,points):
        if len(points)<3:return False
        return max(p[1] for p in points)-min(p[1] for p in points)>self.width*.07

    def observe(self,timestamp,candidates):
        if self.width is None:return  # No fictitious full-frame table.
        if self.pending and self.pending['reason']=='net_drop_same_side':
            origin=self.pending['origin']
            if any((p[0]-self.pending['contact_x'])*(-origin)>self.width*.06 and p[2]>=.7 for p in candidates):self.pending=None
        if self.pending and self.pending['reason']=='held_after_flight':
            anchor=self.pending['point']
            if any(abs(p[0]-anchor[1])>self.width*.04 or abs(p[1]-anchor[2])>self.height*.14 for p in candidates if p[2]>=.7):self.pending=None
        if self.pending and self.pending['reason']=='below_table_stopped':
            if any(p[2]>=.7 and (p[1]<self.bottom-self.height*.04 or
                   (self.last_point and timestamp-self.last_point[0]<.15 and abs(p[0]-self.last_point[1])>self.width*.08)) for p in candidates):self.pending=None
        if self.pending and timestamp>=self.pending['confirm_after']:
            self._dead(self.pending,timestamp)
        if not candidates:return
        options=[p for p in candidates if len(p)==3 and p[2]>=.7 and all(math.isfinite(v) for v in p)]
        if not options:return
        # Multiple simultaneous strong blobs are ambiguous; use temporal proximity
        # but never declare a boundary from a fresh unsupported teleport.
        if self.last_point and timestamp-self.last_point[0]<.15:
            previous=self.last_point
            x,y,confidence=min(options,key=lambda p:math.hypot((p[0]-previous[1])/self.width,(p[1]-previous[2])/self.width)-p[2]*.02)
        else:x,y,confidence=max(options,key=lambda p:p[2])
        point=(timestamp,x,y,confidence)
        old=self.last_point
        contiguous=old is not None and 0<timestamp-old[0]<.15
        if not contiguous:
            self.history.clear();self._reset_flight()
        self.history.append(point);self.context.append(point);self.last_point=point
        while self.context and timestamp-self.context[0][0]>2.2:self.context.popleft()
        while self.history and timestamp-self.history[0][0]>2.2:self.history.popleft()
        points=list(self.history)
        half=self.half(x)
        old_side=self.side
        if half:
            if old_side is not None and half!=old_side:
                self.crossings+=1;self.cross_time=timestamp
                self.target_seen_surface=False;self.target_bounced=False
            self.side=half
        if self.cross_time is not None and self.top+self.height*.02<=y<=self.bottom-self.height*.08:
            self.target_seen_surface=True
        bounced=False;bounce=None;dx=0
        if contiguous:
            dx=x-old[1]
            direction=1 if dx>self.width*.003 else -1 if dx<-self.width*.003 else 0
            # Racket reversals occur near players, not at a net/central bounce.
            if direction and self.direction and direction!=self.direction and abs(x-self.mid)>self.width*.35:
                self.cross_time=None;self.target_seen_surface=False;self.target_bounced=False
            if direction:self.direction=direction
        if len(points)>=3:
            a,b,c=points[-3:]
            if b[0]-a[0]<.15 and c[0]-b[0]<.15:
                falling=b[2]-a[2];rising=b[2]-c[2]
                bounced=(falling>self.height*.025 and rising>self.height*.025 and
                         self.left+self.width*.02<b[1]<self.right-self.width*.02 and
                         self.top+self.height*.08<b[2]<self.bottom-self.height*.08)
                if bounced:bounce=b;self.target_bounced=True
        if bounced:
            side=self.half(bounce[1]);toward=(side==-1 and dx>0) or (side==1 and dx<0)
            own_bounce=toward and self.crossings==0
            if own_bounce and self.state=='WAIT_SERVE':
                context=list(self.context)
                # Exclude the preceding fast ball-return motion, but keep a
                # small upward serve toss on the same side.
                cutoff=max((b[0] for a,b in zip(context,context[1:]) if b[0]<bounce[0]-.05 and
                            b[0]-a[0]<.15 and (b[1]-a[1])*side>self.width*.04),default=-1)
                beginning=[p for p in context if p[0]>=bounce[0]-1.15 and p[0]>cutoff and self.half(p[1])==side]
                start=beginning[0][0] if beginning else bounce[0]
                self._restart(start,timestamp,point,'serve_own_half_bounce')
                return
        if self.state=='WAIT_SERVE':
            # Resume an occluded serve only after reciprocal play, not a single
            # cross-table ball return. This is explicitly weaker evidence.
            if self.crossings>=2 and self.target_bounced and self._has_active_flight(points):
                self._restart(points[0][0],timestamp,point,'reciprocal_play_after_occlusion')
            return
        if not self.side_view or len(points)<3:return
        hold=[p for p in points if timestamp-p[0]<=.35]
        earlier=[p for p in self.context if timestamp-1.0<=p[0]<timestamp-.35]
        if self.pending is None and len(hold)>=5 and hold[-1][0]-hold[0][0]>=.28 and earlier:
            xspan=max(p[1] for p in hold)-min(p[1] for p in hold)
            yspan=max(p[2] for p in hold)-min(p[2] for p in hold)
            player=abs(x-self.mid)>self.width*.40
            approach=(x-earlier[0][1])*(1 if x>self.mid else -1)>self.width*.10
            if player and approach and xspan<self.width*.025 and yspan<self.height*.08:
                self.pending={'end':hold[0][0],'confirm_after':timestamp+.22,'point':point,
                              'reason':'held_after_flight','confidence':.70,
                              'signals':['fast_incoming_flight','player_end_zone','sustained_low_motion']}
        # A second end pattern: ball drops BELOW the table and slows at the
        # receiver, even if it had a possible table contact before going out.
        # Require a real descending approach and a sustained low band. A quick
        # low defensive return cancels this pending end above.
        low=[p for p in points if timestamp-p[0]<=.6 and p[2]>self.bottom+self.height*.18]
        if self.pending is None and y>self.bottom+self.height*.18 and len(low)>=3 and low[-1][0]-low[0][0]>=.18:
            before=[p for p in points if low[0][0]-.65<=p[0]<low[0][0] and p[2]<=self.bottom+self.height*.18]
            approach=before[-2:]
            descending=(len(approach)==2 and low[0][0]-approach[-1][0]<.2 and
                        approach[-1][2]-approach[0][2]>self.height*.05)
            stopped=(max(p[2] for p in low)-min(p[2] for p in low)<self.height*.12 and
                     max(p[1] for p in low)-min(p[1] for p in low)<self.width*.08)
            if descending and stopped and self._has_active_flight(before):
                self.pending={'end':low[0][0]+.04,'confirm_after':timestamp+.2,'point':point,
                              'reason':'below_table_stopped','confidence':.76,
                              'signals':['descending_from_table','below_table_plane','sustained_low_band','slowed_after_flight','no_fast_recovery']}
        recent=[p for p in points if timestamp-p[0]<=.35]
        if not self._has_active_flight(recent):return
        # Strong miss: cross the opponent end ABOVE the playing surface without
        # even a possible landing. A legal wide return after a table bounce must
        # NOT be ended just because it moves beyond the table's image rectangle.
        end_side=1 if x>self.right+self.width*.025 else -1 if x<self.left-self.width*.025 else 0
        if end_side and self.cross_time is not None and not self.target_seen_surface and not self.target_bounced:
            previous_outside=old and ((end_side==1 and old[1]>self.right) or (end_side==-1 and old[1]<self.left))
            outgoing=contiguous and dx*end_side>self.width*.006
            high=y<self.top-self.height*.04
            if self.pending is None and previous_outside and outgoing and high:
                self.pending={'end':timestamp+.04,'confirm_after':timestamp+.24,'point':point,
                              'reason':'out_without_table_bounce','confidence':.83,
                              'signals':['crossed_table_midline','beyond_target_end','above_table','no_target_table_contact']}
        # Only calibrated side-view net evidence enables this rule. Merely being
        # close to x_mid is not enough: ball must stall/reverse and drop on the
        # same side, with no subsequent through-net crossing.
        net_here=self._net_at(x)
        if net_here:
            approach=[p for p in points if timestamp-p[0]<=.45]
            if len(approach)>=5:
                entered=[p for p in approach if self._net_at(p[1]) and self._net_at(p[1])[0]<=p[2]<=self._net_at(p[1])[1]+self.height*.2]
                contact=entered[0] if entered else None
                incoming=(contact[1]-approach[0][1]) if contact else 0
                origin=-1 if incoming>self.width*.02 else 1 if incoming<-self.width*.02 else 0
                if origin and entered:
                    contact=entered[0]
                    after=[p for p in entered if p[0]>=contact[0]+.12]
                    same=all((p[1]-contact[1])*(-origin)<=self.width*.025 for p in approach if p[0]>=contact[0])
                    dropping=after and y-contact[2]>self.height*.12
                    slowed=abs(x-contact[1])<self.width*.04
                    returned=(x-contact[1])*origin>self.width*.005
                    fallen=y>net_here[1]+self.height*.05
                    if self.pending is None and same and dropping and slowed and (returned or fallen):
                        self.pending={'end':timestamp,'confirm_after':timestamp+.18,'point':point,
                                      'reason':'net_drop_same_side','confidence':.72,'origin':origin,'contact_x':contact[1],
                                      'signals':['calibrated_net_band','same_side_drop','horizontal_stall','no_through_crossing']}

    def finish(self,duration):
        if self.pending and duration>=self.pending['confirm_after']:
            self._dead(self.pending,min(duration,self.pending['confirm_after']))
        for interval in self.dead_intervals:
            if interval['end'] is None:interval['end']=duration
        return self.dead_intervals


BRIDGE_GAP_SECONDS=0.0  # disabled by default; opt in via RALLYCUT_BRIDGE_GAP


def resegment(tracks,impacts,duration,validity,finalize=True,horizon=None,cuts=(),geometry_segments=(),track_size=None):
    limit=duration if horizon is None else min(duration,horizon)
    exclusions=(validity.finish(duration) if finalize else [dict(item,end=item['end'] if item['end'] is not None else limit) for item in validity.dead_intervals])
    intervals=[];start=0;start_reason='activity'
    for dead in exclusions:
        if dead['start']>start:
            intervals.append((start,dead['start'],start_reason,dead))
        start=dead['end'];start_reason=dead.get('resume_reason','serve_restart')
    if start<limit:intervals.append((start,limit,start_reason,None))
    frame_view=False;frame_spans=[]
    if geometry_segments:
        from rally_activity import activity_intervals,frame_rule_active
        size=tuple(track_size) if track_size and len(track_size)==2 else (960,540)
        activity=activity_intervals(tracks,geometry_segments,limit,size)
        frame_view=frame_rule_active(tracks,geometry_segments,limit,size)
        clipped=[];frame_spans=[]
        for lo,hi,reason,dead in intervals:
            for a,b,begin,end_reason,*evidence in activity:
                left,right=max(lo,a),min(hi,b)
                if right<=left:continue
                # A piece cut off by a dead-ball start before the episode's
                # first live-ball evidence is only its serve-preparation lead.
                if dead and right<=(evidence[0] if evidence else a):continue
                stop=dead if hi<=b else None
                if end_reason and b<=hi and stop is None:
                    stop={'start':b,'event':{'type':'activity','reason':end_reason,'time':b,'confidence':.6}}
                clipped.append((left,right,begin if begin and a>=lo else reason,stop))
                if len(evidence)>1 and evidence[1]=='frame':frame_spans.append((left,right))
        intervals=clipped
    # A camera cut is a source boundary, not invented dead-ball evidence. Keep
    # visual/audio grouping on each side even when no table geometry is known.
    divided=[]
    for lo,hi,reason,dead in intervals:
        positions=[lo]+sorted({t for t in cuts if lo<t<hi})+[hi]
        # An activity-clipped interval may begin exactly at a cut; keep that
        # source boundary protected rather than a plain activity start.
        if reason=='activity' and any(abs(lo-t)<1e-6 for t in cuts):reason='camera_cut'
        for i,(left,right) in enumerate(zip(positions,positions[1:])):
            stop=dead if i==len(positions)-2 else {'start':right,'event':{'type':'camera_cut','reason':'camera_cut','time':right,'confidence':0}}
            divided.append((left,right,reason if i==0 else 'camera_cut',stop))
    intervals=divided
    # Assign each observation once. Streaming updates must not rescan every
    # frame for every past rally (quadratic over an entire long match).
    starts=[item[0] for item in intervals]
    buckets=[{} for _ in intervals];hit_buckets=[[] for _ in intervals]
    for track in tracks:
        for point in track.points:
            index=bisect_right(starts,point[0])-1
            if index>=0 and point[0]<intervals[index][1]:
                buckets[index].setdefault(track.id,[]).append(point)
    for timestamp in impacts:
        index=bisect_right(starts,timestamp)-1
        if index>=0 and timestamp<intervals[index][1]:hit_buckets[index].append(timestamp)
    output=[]
    boundary_floor=0.0
    for index,(lo,hi,reason,dead) in enumerate(intervals):
        sliced=[Track(f'{identifier}@{lo:.6f}',points) for identifier,points in buckets[index].items()]
        bounds=None
        for segment in reversed(geometry_segments):
            if segment.get('start',0)<=lo<segment.get('end',limit):
                candidate_bounds=segment.get('bounds')
                # Frame-rule episodes (any non-side segment when that rule
                # runs) were chosen without the table box; trimming them by
                # a perspective box would drop real rallies (0044 03:31).
                if frame_view and segment.get('method')!='side-color-rim':candidate_bounds=None
                if candidate_bounds and len(candidate_bounds)==4:
                    if track_size and len(track_size)==2:
                        width,height=track_size
                        candidate_bounds=[candidate_bounds[0]*width,candidate_bounds[1]*height,
                                          candidate_bounds[2]*width,candidate_bounds[3]*height]
                    bounds=candidate_bounds
                break
        short=bool(dead)
        visual=segment_rallies(sliced,duration,first_min_duration=.35,first_min_observations=4,first_min_bins=2,
                               start_lead=SERVE_BOUNDARY_LEAD,table_bounds=bounds)
        if short:
            brief=segment_rallies(sliced,duration,min_duration=.2,min_observations=3,min_bins=2,
                                  start_lead=SERVE_BOUNDARY_LEAD,table_bounds=bounds)
            visual.extend(r for r in brief if r['end']>=hi-.7 and min(hi,r['end'])-max(lo,r['start'])<1 and not any(v['start']<=r['start'] and v['end']>=r['end'] for v in visual))
        candidates=fuse_audio_visual(visual,sliced,hit_buckets[index],duration,'confirm')
        kept=[]
        floor=max(boundary_floor,lo)
        if reason=='serve_restart':
            floor=max(boundary_floor,lo-SERVE_BOUNDARY_LEAD)
        previous_end=floor
        for rally in candidates:
            rally['start']=round(max(floor,previous_end,rally['start']),6)
            rally['end']=round(min(hi,rally['end']),6)
            if rally['end']-rally['start']>=.04:
                kept.append(rally)
                previous_end=rally['end']
        if kept and any(a-1e-6<=lo and hi<=b+1e-6 for a,b in frame_spans):
            # A frame-rule episode is one rally whose last stroke the rule
            # saw at hi - TAIL. The visual tail trim (uncalibrated pixel
            # speeds, meant for pickup motion) must not end it before that
            # stroke: a slow piece mid-rally would drop the rest of the play.
            from rally_serves import TAIL
            main=dict(max(kept,key=lambda r:r['end']-r['start']));main['start']=kept[0]['start']
            main['end']=max(r['end'] for r in kept)
            if main['end']<hi-TAIL-1e-6:main['end']=round(hi,6)
            kept=[main]
        if reason=='serve_prep' and len(kept)>1:
            # One frame-rule episode is one rally: the serve preparation
            # (bounces, then a pause) and the strokes after it stay together.
            main=dict(kept[-1]);main['start']=kept[0]['start'];kept=[main]
        if kept:
            if reason in ('serve_restart','camera_cut','live_ball_evidence','serve_prep'):kept[0]['boundary_before']=True;kept[0]['start_reason']=reason
            if dead and kept[-1]['end']>=dead['start']-.9:
                kept[-1]['end_reason']=dead['event']['reason']
                kept[-1]['end_event_time']=dead['event']['time']
                kept[-1]['end_confidence']=dead['event']['confidence']
            output.extend(kept)
            boundary_floor=max(boundary_floor,kept[-1]['end'])
    # Bridge detection dropouts: two fragments separated by a short gap with no
    # dead-ball evidence and no camera cut are one rally (TTcut's
    # fragment_bridge). Never bridge across real dead-ball events.
    gap_limit=float(os.environ.get('RALLYCUT_BRIDGE_GAP', str(BRIDGE_GAP_SECONDS)))
    bridged=[];dead_spans=[(d['start'],d['end'] if d['end'] is not None else limit) for d in exclusions]
    for rally in output:
        if bridged:
            previous=bridged[-1]
            gap=rally['start']-previous['end']
            blocked=bool(previous.get('end_reason')) or rally.get('start_reason')=='camera_cut'
            if not blocked:
                blocked=any(lo<rally['start'] and hi>previous['end'] for lo,hi in dead_spans)
            if not blocked:
                blocked=any(previous['end']<timestamp<rally['start'] for timestamp in cuts)
            if not blocked and 0<=gap<=gap_limit:
                previous['end']=rally['end']
                previous['score']=max(previous.get('score',0),rally.get('score',0))
                previous['confidence']=max(previous.get('confidence',0),rally.get('confidence',0))
                previous['audio_hits']=previous.get('audio_hits',0)+rally.get('audio_hits',0)
                previous['bridged']=True
                if rally.get('end_reason'):
                    previous['end_reason']=rally['end_reason']
                    previous['end_event_time']=rally.get('end_event_time')
                    previous['end_confidence']=rally.get('end_confidence')
                continue
        bridged.append(rally)
    output=bridged
    for index,rally in enumerate(output):rally['id']=f'visual-{index+1:05d}'
    return output
