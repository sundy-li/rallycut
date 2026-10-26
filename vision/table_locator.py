"""Conservative table calibration: rim geometry + surface color + temporal vote.

A blue floor and blue barriers are not tables. No whole-frame fallback, no
selection of a small background table merely because it has the right hue.
"""
import math
import statistics
import time
from table_jump import DEFAULT_JUMP_SAMPLES,validate_jump_budget,search_later,JumpSearchExhausted


def intersection(first, second):
    x1,y1,x2,y2=first
    x3,y3,x4,y4=second
    denominator=(x1-x2)*(y3-y4)-(y1-y2)*(x3-x4)
    if abs(denominator)<1e-6:
        return None
    a=x1*y2-y1*x2
    b=x3*y4-y3*x4
    return ((a*(x3-x4)-(x1-x2)*b)/denominator,
            (a*(y3-y4)-(y1-y2)*b)/denominator)


def iou(a,b):
    common=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    total=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-common
    return common/total if total else 0


def candidates(frame):
    import cv2
    import numpy as np
    from visual import find_table
    height,width=frame.shape[:2]
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    white=((hsv[:,:,1]<100)&(hsv[:,:,2]>145)).astype('uint8')*255
    white[:int(height*.28)]=0
    white[int(height*.74):]=0
    lines=cv2.HoughLinesP(cv2.Canny(white,50,120),1,np.pi/180,threshold=40,
                          minLineLength=int(width*.095),maxLineGap=16)
    rims=[]
    if lines is not None:
        for values in lines[:,0]:
            x1,y1,x2,y2=map(int,values)
            if x1>x2:
                x1,y1,x2,y2=x2,y2,x1,y1
            if x2-x1<width*.09 or abs(y2-y1)>(x2-x1)*.65:
                continue
            rims.append((x1,y1,x2,y2))
    output=[]
    # Preserve the validated long side-view route, but reject narrow background
    # candidates and require a long bright rim near the front of the surface.
    side=find_table(frame)
    if side and side[2]-side[0]>width*.45:
        left,top,right,bottom=side
        rim_support=any(min(right,x2)-max(left,x1)>(right-left)*.20 and
                        abs(max(y1,y2)-bottom)<height*.035 for x1,y1,x2,y2 in rims)
        if rim_support:
            output.append({'bounds':side,'score':(right-left)*(bottom-top),'method':'side-color-rim'})
    positive=[line for line in rims if .045<(line[3]-line[1])/(line[2]-line[0])<.65]
    negative=[line for line in rims if -.65<(line[3]-line[1])/(line[2]-line[0])<-.045]
    for first in positive:
        for second in negative:
            vertex=intersection(first,second)
            if vertex is None:
                continue
            vx,vy=vertex
            # The two front white rims must actually meet: a net and a random
            # barrier edge somewhere else cannot define a fictitious table.
            if math.hypot(vx-first[2],vy-first[3])>width*.035 or math.hypot(vx-second[0],vy-second[1])>width*.035:
                continue
            left=np.array(first[:2],dtype='float32')
            right=np.array(second[2:],dtype='float32')
            front=np.array(vertex,dtype='float32')
            span=right[0]-left[0]
            if not width*.27<span<width*.93 or not height*.30<vy<height*.72:
                continue
            midpoint=(left+right)/2
            if not height*.025<vy-midpoint[1]<height*.20:
                continue
            # A perspective-compressed far corner; only a coarse surface ROI is
            # needed, not an assertion that four precise court corners are known.
            back=midpoint+(midpoint-front)*.65
            polygon=np.array([left,front,right,back],dtype='int32')
            if not cv2.isContourConvex(polygon):
                continue
            x,y,bw,bh=cv2.boundingRect(polygon)
            if x<0 or y<height*.25 or x+bw>width or y+bh>height*.76 or not 2.5<bw/bh<15:
                continue
            mask=np.zeros((height,width),dtype='uint8')
            cv2.fillConvexPoly(mask,polygon,1)
            mask=cv2.erode(mask,np.ones((5,5),dtype='uint8'))
            pixels=hsv[mask>0]
            if len(pixels)<width*height*.008:
                continue
            blue=((pixels[:,0]>=95)&(pixels[:,0]<=150)&(pixels[:,1]>=35)).mean()
            if blue<.56:
                continue
            area=cv2.contourArea(polygon)
            output.append({'bounds':(x,y,x+bw,y+bh),'score':float(area)*(1+vy/height)*float(blue),
                           'method':'perspective-rims'})
    # One surface often produces several near-identical line pairs.
    unique=[]
    for item in sorted(output,key=lambda item:-item['score']):
        if not any(iou(item['bounds'],previous['bounds'])>.65 for previous in unique):
            unique.append(item)
    return unique[:5]


def stable_table(samples, minimum_observations=3, minimum_span=2.0):
    """Require evidence at distinct sampled moments; select the best main surface."""
    groups=[]
    for timestamp,items in samples:
        used=set()
        for item in sorted(items,key=lambda candidate:-candidate['score']):
            matches=[(iou(item['bounds'],group[-1][1]['bounds']),index) for index,group in enumerate(groups)
                     if index not in used and group[-1][0]!=timestamp]
            score,index=max(matches,default=(0,-1))
            if score>=.60:
                groups[index].append((timestamp,item));used.add(index)
            else:
                groups.append([(timestamp,item)]);used.add(len(groups)-1)
    eligible=[group for group in groups if len(group)>=minimum_observations and group[-1][0]-group[0][0]>=minimum_span]
    if not eligible:
        return None
    eligible.sort(key=lambda group:-(statistics.median(item['score'] for _,item in group)*min(len(group),8)))
    best=eligible[0]
    bounds=tuple(round(statistics.median(item['bounds'][index] for _,item in best)) for index in range(4))
    if len(eligible)>1:
        other=eligible[1]
        a=statistics.median(item['score'] for _,item in best)
        b=statistics.median(item['score'] for _,item in other)
        if b>a*.85 and iou(bounds,other[-1][1]['bounds'])<.25:
            return None  # Ambiguous multi-table scene: do not silently pick one.
    return {'bounds':bounds,'method':best[-1][1]['method'],'observations':len(best),
            'first_evidence':best[0][0],'last_evidence':best[-1][0]}


DEFAULT_SEARCH_SECONDS=600.0
MAX_SEARCH_SECONDS=3600.0


def sampling_schedule(horizon, duration):
    """Dense opening, sparse extended search; positions are video seconds."""
    if not math.isfinite(horizon) or horizon<=0 or horizon>MAX_SEARCH_SECONDS:
        raise ValueError('球桌校准窗口必须大于 0 且不超过 3600 秒')
    interval=min(1.0,max(.1,duration/6))
    dense=min(horizon,30.0)
    positions=[round(index*interval,6) for index in range(int(dense/interval)+1)]
    position=35.0
    while position<=horizon:
        positions.append(position)
        position+=5
    if horizon-positions[-1]>.05:
        positions.append(horizon)
    return positions


class SeekUnavailable(Exception):
    pass


def seek_samples(cap, positions):
    import cv2
    previous=-1.0
    for target in positions:
        if not cap.set(cv2.CAP_PROP_POS_MSEC,target*1000):
            raise SeekUnavailable('解码器不支持按时间 seek')
        ok,frame=cap.read()
        if not ok:
            # Seeking to exact container EOF may be one frame beyond video EOF.
            # The final position is only optional coverage, not a hidden retry.
            if target==positions[-1] and previous>=target-.25:
                return
            raise SeekUnavailable(f'无法读取 seek 位置 {target:.2f} 秒')
        timestamp=float(cap.get(cv2.CAP_PROP_POS_MSEC))/1000
        if not math.isfinite(timestamp) or timestamp<=previous or abs(timestamp-target)>.25:
            raise SeekUnavailable('seek 时间戳不可靠')
        previous=timestamp
        yield timestamp,frame


def sequential_samples(cap, positions):
    import cv2
    previous=-1.0
    index=0
    while index<len(positions) and cap.grab():
        ok,frame=cap.retrieve()
        if not ok:
            raise ValueError('球桌校准时视频解码失败')
        timestamp=float(cap.get(cv2.CAP_PROP_POS_MSEC))/1000
        if not math.isfinite(timestamp) or timestamp<=previous:
            raise ValueError('球桌校准缺少单调视频时间戳')
        previous=timestamp
        if timestamp>positions[-1]+.05:
            break
        if timestamp+.001<positions[index]:
            continue
        yield timestamp,frame
        while index<len(positions) and positions[index]<=timestamp+.001:
            index+=1


def calibrate(video_path, duration, progress, search_seconds=DEFAULT_SEARCH_SECONDS,jump_samples=DEFAULT_JUMP_SAMPLES):
    import cv2
    if not math.isfinite(search_seconds) or not 0<search_seconds<=MAX_SEARCH_SECONDS:
        raise ValueError('球桌校准窗口必须大于 0 且不超过 3600 秒')
    if not math.isfinite(duration) or duration<=0:
        raise ValueError('无效视频时长')
    validate_jump_budget(jump_samples)
    started=time.monotonic()
    inspected=0;extent=0.0
    horizon=min(duration,search_seconds)
    positions=sampling_schedule(horizon,duration)
    minimum_span=min(2.0,max(.1,duration*.4))
    from net_geometry import side_net_region
    for strategy in ('seek_sparse','sequential_fallback'):
        cap=cv2.VideoCapture(str(video_path),cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            raise ValueError('无法打开比赛视频进行球桌校准')
        samples=[];net_samples=[]
        try:
            frames=seek_samples(cap,positions) if strategy=='seek_sparse' else sequential_samples(cap,positions)
            for timestamp,frame in frames:
                resized=cv2.resize(frame,(960,540),interpolation=cv2.INTER_AREA)
                items=candidates(resized)
                samples.append((timestamp,items))
                inspected+=1;extent=max(extent,timestamp)
                if items:
                    net=side_net_region(resized,items[0]['bounds'],items[0]['method'])
                    if net:net_samples.append(net)
                progress(0,f'球桌抽帧校准 {timestamp:.0f} / {horizon:.0f} 视频秒 · 已检查 {len(samples)} 帧')
                if timestamp<min(8,horizon*.8):
                    continue
                found=stable_table(samples,minimum_span=minimum_span)
                if found:
                    break
            else:
                found=stable_table(samples,minimum_span=minimum_span)
            if found:
                found.update(jump_samples=0,jump_windows=0,jump_budget=jump_samples,search_extent_seconds=extent)
                return complete_calibration(found,net_samples,horizon,inspected,strategy,started,progress)
            break  # The initial reliable pass failed: try bounded late windows.
        except SeekUnavailable as error:
            if strategy!='seek_sparse':
                raise
            progress(0,f'快速抽帧不可用，重新顺序校准（可能更慢）：{error}')
            # Discard seek observations and reopen at 0, never trust stale PTS.
        finally:
            cap.release()

    if jump_samples==0 or duration-horizon<2.5:
        suffix='后段跳搜已关闭' if jump_samples==0 else '视频已无后续可搜索时段'
        raise ValueError(f'前 {horizon:.0f} 秒未找到稳定主球桌；{suffix}；未退回整幅画面分析')
    progress(0,f'前 {horizon:.0f} 秒无稳定主桌，开始后段分层跳搜 · 额外预算 {jump_samples} 帧')
    cap=cv2.VideoCapture(str(video_path),cv2.CAP_FFMPEG)
    try:
        if not cap.isOpened():raise ValueError('无法打开视频进行后段跳搜')
        def inspect_at(target):
            try:timestamp,frame=next(seek_samples(cap,[target]))
            except StopIteration:raise SeekUnavailable('跳搜位置没有可读取画面')
            if timestamp<=horizon:raise SeekUnavailable('后段 seek 返回了开头的旧画面')
            resized=cv2.resize(frame,(960,540),interpolation=cv2.INTER_AREA)
            items=candidates(resized)
            net=side_net_region(resized,items[0]['bounds'],items[0]['method']) if items else []
            return timestamp,items,net
        try:
            found,nets=search_later(horizon,duration,jump_samples,inspect_at,
                lambda local:stable_table(local,minimum_span=minimum_span),progress)
        except SeekUnavailable as error:
            raise ValueError(f'前 {horizon:.0f} 秒未找到稳定主桌，后段无法可靠跳转：{error}；已停止，不顺扫整片') from error
        except JumpSearchExhausted as error:
            raise ValueError(f'前 {horizon:.0f} 秒未找到稳定主桌；{error}；需更清晰机位或人工标定，未退回整幅画面') from error
        found['search_extent_seconds']=max(extent,found['search_extent_seconds'])
        return complete_calibration(found,nets,horizon,inspected+found['jump_samples'],strategy+'_then_jump',started,progress)
    finally:
        cap.release()


def complete_calibration(found,net_samples,horizon,inspected,strategy,started,progress):
    # Net evidence must come from the chosen phase/window, never combine posts
    # from unrelated minutes. The same three-observation gate remains in force.
    stable_nets=[n for n in net_samples if sum(max(abs(a-b) for a,b in zip(n,other))<.025 for other in net_samples)>=3]
    found['net_region']=[round(statistics.median(n[i] for n in stable_nets),6) for i in range(6)] if stable_nets else []
    found.update(search_seconds=horizon,sampled_frames=inspected,strategy=strategy,
                 elapsed_seconds=round(time.monotonic()-started,3))
    progress(0,f"主球桌已校准 · 检查 {inspected} 帧 / {found['elapsed_seconds']:.2f} 秒 · 从原片开头推理")
    return found
