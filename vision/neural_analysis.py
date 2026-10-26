"""BlurBall inference on a table-centred 16:9 crop (full frame without geometry).

Default: no calibration prepass, no table-related failure, every model detection
enters tracking. Live geometry only assists overlays/ball-validity rules. The
old calibration/search is explicit via table_mode='precalibrate'.
"""
import math
import os
import time
from pretrained import MODEL,BlurBallDetector
from visual import update_tracks
from shot_boundary import ShotMonitor
from inference_pipeline import run_batches
from performance import ProcessingRate
from video_decode import open_capture
from audio_features import impact_times
from rally_transits import side_view
from rally_state import BallValidity,resegment,validate_net_region,VERSION as RALLY_VERSION

TABLE_MODES=('optional','off','precalibrate')


def serialize_tracks(tracks,off_play=frozenset()):
    out=[]
    for track in tracks:
        item={'id':str(track.id),'points':[{'t':round(p[0],6),'x':round(p[1]/960,6),
              'y':round(p[2]/540,6),'confidence':round(p[3],6)} for p in track.points]}
        # Display hint only (play_area): kept in the result, not drawn as the ball.
        if track.id in off_play:item['off_play']=True
        out.append(item)
    return out


def accepted_neural_track(track):
    points=track.points
    if len(points)<3 or points[-1][0]-points[0][0]<.05:return False
    xs,ys=[p[1] for p in points],[p[2] for p in points]
    return max(max(xs)-min(xs),max(ys)-min(ys))>=960*.008


def normalized(bounds):
    return [round(bounds[0]/960,6),round(bounds[1]/540,6),round(bounds[2]/960,6),round(bounds[3]/540,6)] if bounds else []


class TrackingStage:
    """Everything after the detector: per-frame model points -> tracks -> rallies.

    Fresh analysis and the L0 replay (detection_cache) feed exactly this class
    with the same (timestamp, shot snapshot, raw points) sequence, so a replay
    of a cached detection run reproduces the fresh result.
    """
    def __init__(self,duration,impacts=(),net_region=None):
        self.duration=duration;self.impacts=list(impacts);self.net_region=net_region
        self.validity=BallValidity()
        self.active=[];self.accepted=[];self.next_id=1
        self.current_shot=None;self.current_geometry=None;self.table_bounds=[];self.net=[]
        self.cuts=[];self.geometry_events=[];self.detection_frames=0

    def rallies(self,horizon=None):
        # Consumer-owned geometry only: never read producer-ahead mutable events.
        segments=[]
        for i,(start,shot) in enumerate(self.geometry_events):
            end=self.geometry_events[i+1][0] if i+1<len(self.geometry_events) else self.duration
            segments.append({'start':start,'end':end,'bounds':normalized(shot.bounds),'method':shot.method})
        return resegment(self.accepted,self.impacts,self.duration,self.validity,finalize=horizon is None,horizon=horizon,
                         cuts=self.cuts,geometry_segments=segments,track_size=(960,540))

    def observe(self,timestamp,shot,raw):
        validity=self.validity
        if self.current_shot!=shot.shot_id:
            self.accepted.extend(t for t in self.active if accepted_neural_track(t));self.active=[]
            if self.current_shot is not None:self.cuts.append(shot.shot_start)
            validity.rebind(timestamp=shot.shot_start)
            self.current_shot=shot.shot_id;self.current_geometry=None;self.table_bounds=[];self.net=[]
        if self.current_geometry!=shot:
            self.geometry_events.append((timestamp if self.geometry_events else 0.0,shot))
            self.table_bounds=normalized(shot.bounds)
            self.net=list(self.net_region if self.net_region is not None and shot.shot_id==0 else shot.net)
            validity.rebind(self.table_bounds or None,self.net,shot.method)
            self.current_geometry=shot
        # No ROI gate: every model point, including outside any optional
        # geometry, reaches tracking and the frame callback.
        candidates=[(x*960,y*540,score) for x,y,score in raw]
        self.detection_frames+=bool(candidates)
        table_bounds=self.table_bounds
        if table_bounds:
            # Geometry-based rules may use the main playing corridor;
            # this never removes detections/tracks from the result.
            rule_points=[(x,y,s) for x,y,s in raw if y<=table_bounds[3]+.07 and
                         table_bounds[0]-.2<=x<=table_bounds[2]+.2]
            validity.observe(timestamp,rule_points)
        self.active,done,self.next_id=update_tracks(self.active,candidates,timestamp,self.next_id,960)
        self.accepted.extend(t for t in done if accepted_neural_track(t))
        return candidates

    def finish(self,state,cuts):
        """Close with the detector's final shot state; returns (rallies, tracks)."""
        if state.shot_id!=self.current_shot:self.validity.rebind(timestamp=state.shot_start)
        self.cuts[:]=cuts
        self.table_bounds=normalized(state.bounds)
        self.net=list(self.net_region if self.net_region is not None and state.shot_id==0 and self.table_bounds else state.net)
        self.accepted.extend(t for t in self.active if accepted_neural_track(t));self.accepted.sort(key=lambda t:t.points[0][0])
        from play_area import off_play_tracks
        rallies=self.rallies()
        return rallies,serialize_tracks(self.accepted,off_play_tracks(self.accepted))


class DetectionRun:
    """L0: decode, shot / optional geometry monitor and the ball model.

    Its output per scored frame is (record, raw points); everything downstream
    lives in TrackingStage. The L0 cache digest covers this class's source.
    """
    def __init__(self,video_path,duration,progress,device='auto',calibration_seconds=600,precision='fp32',batch_size=4,
                 pipeline=True,decoder='opencv',calibration_jump_samples=96,table_mode='optional'):
        import cv2
        self.video_path=video_path;self.duration=duration;self.batch_size=batch_size;self.pipeline=pipeline
        self.decoder=decoder;self.precision=precision;self.table_mode=table_mode
        self.calibration_seconds=calibration_seconds;self.calibration_jump_samples=calibration_jump_samples
        cv2.setNumThreads(1)
        self.started=time.monotonic()
        self.detector=BlurBallDetector(device=device,precision=precision)
        self.calibration=None;self.calibration_error=None
        if table_mode=='precalibrate':
            from table_locator import calibrate
            try:self.calibration=calibrate(video_path,duration,progress,search_seconds=calibration_seconds,jump_samples=calibration_jump_samples)
            except ValueError as error:
                self.calibration_error=str(error)
                progress(0,'可选预校准未成功，继续整帧球检测')
        else:progress(0,'整帧球检测：无需前置球桌标定')
        self.monitor=ShotMonitor(geometry=table_mode!='off',initial=self.calibration)
        self.decoded=self.unique=self.duplicates=0
        self.decode_state={};self.rates=None;self.stages=None

    def run(self,on_record):
        import cv2
        import numpy as np
        detector,monitor,duration,batch_size=self.detector,self.monitor,self.duration,self.batch_size
        previous_t=-1.0

        def consume(batch,heatmaps):
            windows=[[p['input'] for p in item] for item in batch]
            predictions=detector.postprocess(windows,heatmaps)
            if len(predictions)!=len(batch) or any(len(window)!=3 for window in predictions):
                raise ValueError('detector output window count mismatch')
            for item,windows_result in zip(batch,predictions):
                for record,raw in zip(item,windows_result):
                    self.rates.add()
                    on_record(record,raw)

        def batches():
            nonlocal previous_t
            window,batch=[],[];last_tensor=None;last_shot=None
            cap=open_capture(self.video_path,self.decoder,self.decode_state)
            try:
                if not cap.isOpened():raise ValueError('无法打开比赛视频')
                while cap.grab():
                    self.decoded+=1
                    ok,frame=cap.retrieve()
                    if not ok:raise ValueError(f'视频解码失败: frame {self.decoded}')
                    timestamp=float(cap.get(cv2.CAP_PROP_POS_MSEC))/1000
                    if not math.isfinite(timestamp) or timestamp<=previous_t:raise ValueError('解码器未提供单调时间戳')
                    previous_t=timestamp
                    if timestamp>duration:break
                    shot=monitor.push(timestamp,frame)
                    if last_shot!=shot.shot_id:
                        # Never let one three-frame neural input straddle a cut.
                        window=[];last_tensor=None;last_shot=shot.shot_id
                    pair=detector.prepare_frame(frame)
                    if last_tensor is not None and np.array_equal(pair[0],last_tensor):
                        self.duplicates+=1;continue
                    last_tensor=pair[0];self.unique+=1
                    window.append({'input':pair,'t':timestamp,'frame_index':self.decoded-1,'shot':shot})
                    if len(window)==3:batch.append(window);window=[]
                    if len(batch)==batch_size:yield batch;batch=[]
                if batch:yield batch
                if self.decoded<3 or previous_t<duration-max(1.0,duration*.002):
                    raise ValueError('视频过短或提前结束，不保存不完整结果')
            finally:cap.release()

        self.rates=ProcessingRate()
        self.stages=run_batches(batches(),lambda batch:detector.predict_heatmaps(
            [[p['input'] for p in item] for item in batch]),consume,pipelined=self.pipeline)
        return self.stages


def analyze(video_path,duration,progress,audio_path=None,device='auto',frame_callback=None,calibration_seconds=600,
            precision='fp32',batch_size=4,pipeline=True,performance_callback=None,decoder='opencv',
            candidates_callback=None,net_region=None,calibration_jump_samples=96,
            table_mode='optional',l0_recorder=None):
    if table_mode not in TABLE_MODES:raise ValueError('table-mode must be optional, off or precalibrate')
    validate_net_region(net_region)
    if type(batch_size) is not int or not 1<=batch_size<=8:raise ValueError('batch-size must be an integer in 1-8')
    decoder=os.environ.get('RALLYCUT_DECODER',decoder)
    if decoder not in ('opencv','videotoolbox','auto'):raise ValueError('decoder must be opencv, videotoolbox or auto')
    if not isinstance(pipeline,bool):raise ValueError('pipeline must be a boolean')
    run=DetectionRun(video_path,duration,progress,device=device,calibration_seconds=calibration_seconds,precision=precision,
                     batch_size=batch_size,pipeline=pipeline,decoder=decoder,calibration_jump_samples=calibration_jump_samples,
                     table_mode=table_mode)
    detector,monitor=run.detector,run.monitor
    impacts=impact_times(audio_path) if audio_path else []
    stage=TrackingStage(duration,impacts,net_region)
    if l0_recorder is not None:l0_recorder.start(run,impacts,bool(audio_path))
    state={'last_report':-2.0,'last_candidates':None,'last_table':None,'emitted':0}

    def on_record(record,raw):
        timestamp=record['t']
        candidates=stage.observe(timestamp,record['shot'],raw)
        if l0_recorder is not None:l0_recorder.frame(timestamp,record['shot'],raw)
        if frame_callback:frame_callback(record,raw,candidates)
        table_bounds=stage.table_bounds
        due=timestamp-state['last_report']>=2
        if candidates_callback and (due or table_bounds!=state['last_table']):
            partial=stage.rallies(timestamp)
            signature=tuple((r['start'],r['end'],r.get('boundary_before',False),r.get('end_reason','')) for r in partial)
            fresh=serialize_tracks(stage.accepted[state['emitted']:])
            changed=bool(partial) and signature!=state['last_candidates']
            if fresh or changed or table_bounds!=state['last_table']:
                if partial:state['last_candidates']=signature
                state['last_table']=list(table_bounds);state['emitted']=len(stage.accepted)
                candidates_callback(partial,timestamp,fresh,table_bounds)
        if due:
            if performance_callback:performance_callback(run.rates.snapshot())
            progress(min(.94,timestamp/duration*.94),
                     f'整帧模型 / {detector.device} / {precision} · {timestamp:.0f} / {duration:.0f} 秒 · {len(stage.accepted)} 条轨迹')
            state['last_report']=timestamp

    stages=run.run(on_record)
    rates=run.rates
    if performance_callback:
        final_rate=rates.snapshot();final_rate['stage']='finalizing';performance_callback(final_rate)
        progress(.95,'画面分析完成，正在融合声音与轨迹')
    rallies,tracks=stage.finish(monitor.state,monitor.cuts)
    if l0_recorder is not None:l0_recorder.finish(run,duration)
    accepted,validity,table_bounds,net=stage.accepted,stage.validity,stage.table_bounds,stage.net
    segments=monitor.segments(duration)
    decoded,unique,duplicates,detection_frames,decode_state=run.decoded,run.unique,run.duplicates,stage.detection_frames,run.decode_state
    calibration,calibration_error,started=run.calibration,run.calibration_error,run.started
    geometry_available=any(segment['bounds'] for segment in segments)
    warnings=['整帧检测与跟踪；球桌只用于可选显示与回合规则，不过滤检出点。',
              '声音只作弱佐证，不新建、不延长、不评分分（邻场击球声会误触发）。',
              '球检测分数不是校准后的准确率；回合切分仍是需复核的轨迹/声音规则。',
              '官方权重独立再分发许可待确认，不随应用或 skill 打包。']
    warnings.extend(monitor.warnings)
    if not geometry_available:
        warnings.append('没有可信球桌几何：未判定触网/出界等几何死球，不用全画面矩形冒充球桌。')
    elif any(not segment['bounds'] for segment in segments):
        warnings.append('部分时段无可信球桌几何：这些时段的触网/出界判断已降级，球检测正常继续。')
    from rally_activity import frame_rule_active
    if frame_rule_active(accepted,segments,duration,(960,540)):
        warnings.append('球沿画面横向往返：非侧视几何的时段（含斜视框）按画面坐标的抛球发球与击球分段（不依赖球桌框，阈值按本视频球速 / 幅度自校准）；看到发球前颠球时回合从颠球开始；击球中断不代表已判定触网或出界。')
    elif any(s['method']=='perspective-rims' for s in segments):
        warnings.append('斜视分使用发球/往返与活动停止证据；活动分界不代表已判定触网或出界。')
    if any(side_view(s) for s in segments):
        warnings.append('侧视分按快速低位过台分段，慢速/高抛回送不连成回合；过台中断不代表已判定触网或出界。')
    if not net:warnings.append('当前镜头无可信网面，不猜测触网。')
    if monitor.cuts:warnings.append(f'检测到 {len(monitor.cuts)} 次切镜，已断开跨镜头轨迹与分；旧几何不跨镜头沿用。')
    if monitor.motion_vetoes:warnings.append(f'{monitor.motion_vetoes} 帧画面整体平移（手持晃动/摇镜）未判为切镜，轨迹与回合不因此断开。')
    if monitor.drift_follows:warnings.append(f'镜头移动后 {monitor.drift_follows} 次按整体平移跟随球桌几何（不含缩放 / 旋转）。')
    if monitor.drift_resets:warnings.append(f'镜头移动过大 {monitor.drift_resets} 次，清除并重新获取球桌几何，期间相应规则降级。')
    if calibration_error:warnings.append('可选预校准失败但球检测已继续：'+calibration_error)
    if calibration and calibration.get('jump_samples',0):warnings.append('显式预校准来自后段跳搜，机位变化需人工复核。')
    if precision=='fp16':warnings.append('FP16 为显式速度模式，阈值附近候选可能变化。')
    if decode_state.get('hardware_decode'):warnings.append('VideoToolbox 硬解已核验启用；颜色转换与 OpenCV 不同，阈值附近结果可能略有差异。')
    if decode_state.get('decode_fallback'):warnings.append('硬解不可用，已回退 OpenCV：'+decode_state['decode_fallback'])
    summary={'method':MODEL,'decoded_frames':decoded,'sampled_frames':rates.frames,'track_count':len(tracks),
             'elapsed_seconds':round(time.monotonic()-started,3),'table_mode':table_mode,'geometry_available':geometry_available,
             'table_bounds':table_bounds,'table_segments':segments,'camera_cuts':len(monitor.cuts),'scene_changes':len(monitor.cuts),
             'rally_state_version':RALLY_VERSION,'rally_events':validity.events,
             'net_region':net,'net_region_source':('manual' if net_region is not None and monitor.state.shot_id==0 else 'live_optional') if net else 'unavailable',
             'audio_impacts':len(impacts),'weights_sha256':detector.sha256,'decoder':decoder,
             'hardware_decode':decode_state.get('hardware_decode',False),'decode_format':decode_state.get('decode_format',''),
             'device':detector.device,'precision':getattr(detector,'precision',precision),'batch_size':batch_size,'pipeline':pipeline,
             'pipeline_timings':{key:round(value,6) if isinstance(value,float) else value for key,value in stages.items()},
             'duplicate_frames':duplicates,'detection_frames':detection_frames,
             'processing_fps':round(rates.frames/stages['wall_seconds'],2) if stages['wall_seconds']>0 else 0,
             'analysis_fps':round(rates.frames/(time.monotonic()-started),2),'unscored_frames':unique-rates.frames,
             'implementation':'full-frame-v17','play_area_version':'play-area-v1','activity_rule_version':'side-transit-v4+frame-serve-v8+perspective-activity-v2','warnings':warnings,'calibration_strategy':'search_failed' if calibration_error else 'not_required'}
    if calibration:
        summary.update(calibration_method=calibration['method'],calibration_samples=calibration['observations'],
                       calibration_first_timestamp=calibration.get('first_evidence',0),calibration_last_timestamp=calibration['last_evidence'],
                       calibration_search_seconds=calibration['search_seconds'],calibration_sampled_frames=calibration['sampled_frames'],
                       calibration_elapsed_seconds=calibration['elapsed_seconds'],calibration_strategy=calibration['strategy'],
                       calibration_jump_samples=calibration.get('jump_samples',0),calibration_jump_windows=calibration.get('jump_windows',0),
                       calibration_jump_budget=calibration.get('jump_budget',0),
                       calibration_search_extent_seconds=calibration.get('search_extent_seconds',calibration['last_evidence']))
    return {'protocol_version':1,'model':MODEL,'rallies':rallies,'tracks':tracks,'summary':summary}
