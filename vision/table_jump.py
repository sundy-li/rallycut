"""Bounded breadth-first temporal probing after the initial calibration window.

Planner is deterministic, covers coarse gaps before fine ones, and never votes
across unrelated minutes. All actual observations still come from decoder PTS.
"""
from collections import deque
import math
import time

DEFAULT_JUMP_SAMPLES=96
MAX_JUMP_SAMPLES=384
DEFAULT_JUMP_WINDOWS=32
MAX_JUMP_WINDOWS=128
JUMP_WALL_SECONDS=60.0


def validate_jump_budget(budget):
    if type(budget) is not int or not 0<=budget<=MAX_JUMP_SAMPLES:
        raise ValueError('calibration-jump-samples must be an integer in 0-384')


def anchors(start,duration,limit=DEFAULT_JUMP_WINDOWS):
    """Near frontier, midpoint, tail, then dyadic BFS; O(limit) memory/work."""
    if not math.isfinite(start) or not math.isfinite(duration) or start<0:return
    end=duration-.25
    if end<=start or limit<=0:return
    seen=set();count=0
    queue=deque([(start,end)])
    midpoint=start+(end-start)/2
    candidates=[min(start+2,midpoint),midpoint,end]
    while count<limit:
        if candidates:
            point=candidates.pop(0)
        elif queue:
            left,right=queue.popleft()
            if right-left<2:continue
            point=left+(right-left)/2
            if not left<point<right:continue
            queue.append((left,point));queue.append((point,right))
        else:return
        if not start<point<=end:continue
        key=round(point,4)
        if key in seen:continue
        seen.add(key);count+=1
        yield point


def neighbors(anchor,start,duration,refine=False):
    offsets=(-2,2) if refine else (-1,0,1)
    lower=start+.25;end=duration-.25
    if end-lower<2:return []
    center=max(lower+1,min(end-1,anchor))
    return sorted({round(max(lower,min(end,center+offset)),6) for offset in offsets})


def search_later(start,duration,budget,read_one,consensus,progress,clock=time.monotonic):
    """read_one(target)->(actual_pts, items, net), or raises on unreliable seek.

    read_one owns decoder checks. Cache requests, deduplicate actual PTS, and
    confirm each anchor in its own +/-2s neighborhood. Results include explicit
    coverage/budget metadata; max inspected PTS is not continuous coverage.
    """
    validate_jump_budget(budget)
    began=clock();cache={};samples_used=0;windows=0;extent=start;reason='exhausted'
    def collect(targets):
        nonlocal samples_used,extent,reason
        values=[]
        for target in targets:
            if target not in cache:
                if samples_used>=budget:
                    reason='sample_budget';break
                if clock()-began>=JUMP_WALL_SECONDS:
                    reason='time_budget';break
                samples_used+=1
                timestamp,items,net=read_one(target)
                cache[target]=(timestamp,items,net)
                extent=max(extent,timestamp)
            values.append(cache[target])
        if reason!='time_budget' and clock()-began>=JUMP_WALL_SECONDS:reason='time_budget'
        return [] if reason=='time_budget' else values
    window_limit=min(MAX_JUMP_WINDOWS,max(1,(budget+2)//3))
    if budget:
        for anchor in anchors(start,duration,limit=window_limit):
            windows+=1
            local=collect(neighbors(anchor,start,duration))
            if len(local)<3:break
            # Actual timestamps, never target locations, establish consistency.
            def unique(records):
                by_time={round(value[0],6):value for value in records}
                return sorted(by_time.values(),key=lambda value:value[0])
            local=unique(local)
            found=consensus([(t,items) for t,items,_ in local]) if len(local)>=3 else None
            if found is None and any(items for _,items,_ in local):
                local=unique(local+collect(neighbors(anchor,start,duration,refine=True)))
                found=consensus([(t,items) for t,items,_ in local]) if len(local)>=3 else None
            progress(0,f'后段跳搜 · 窗口 {windows}/{window_limit} · 视频 {anchor:.1f}s · 新采样 {samples_used}/{budget}')
            if found:
                found.update(jump_samples=samples_used,jump_windows=windows,jump_budget=budget,
                             jump_elapsed_seconds=round(clock()-began,3),search_extent_seconds=extent)
                return found,[net for _,_,net in local if net]
            if samples_used>=budget:reason='sample_budget'
            if reason in ('sample_budget','time_budget'):break
    raise JumpSearchExhausted(samples_used,windows,extent,reason)


class JumpSearchExhausted(ValueError):
    def __init__(self,samples,windows,extent,reason):
        self.samples,self.windows,self.extent,self.reason=samples,windows,extent,reason
        super().__init__(f'后段跳搜未找到稳定主球桌：{windows} 个窗口 / {samples} 张新采样帧；最远检查 {extent:.1f}s，停止原因 {reason}；不是连续覆盖')
