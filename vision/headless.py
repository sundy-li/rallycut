#!/usr/bin/env python3
"""Portable video -> candidate JSON CLI. No Wails/Go/Node or runtime downloads."""
import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from pretrained import MODEL, WEIGHTS_SHA256, locate_weights


class Deadline:
    def __init__(self, seconds):
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('timeout must be finite and positive')
        self.end = time.monotonic()+seconds

    def remaining(self):
        seconds = self.end-time.monotonic()
        if seconds <= 0:
            raise TimeoutError('task timeout; no candidate JSON was published')
        return seconds


def binary(name):
    override = os.environ.get('RALLYCUT_'+name.upper())
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    for prefix in ('/opt/homebrew/bin', '/usr/local/bin'):
        path = Path(prefix)/name
        if path.is_file():
            return str(path)
    raise ValueError(f'missing {name}; install FFmpeg first')


def command(args, deadline):
    # Temporary logs bound memory even when a broken executable floods stderr.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors)
        try:
            stdout, _ = process.communicate(timeout=deadline.remaining())
            if process.returncode:
                errors.seek(0)
                raise ValueError(f'{Path(args[0]).name} failed: '+errors.read(8192).decode('utf-8',errors='replace'))
            return stdout
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout is not None:
                process.stdout.close()


def fingerprint(path, deadline):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(1<<20):
            deadline.remaining()
            digest.update(chunk)
    return digest.hexdigest()


def finite(value):
    return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)


def probe(path, deadline):
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError('input must be a regular local video file')
    data = json.loads(command([binary('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(path)],deadline))
    streams = data.get('streams',[])
    video = next((s for s in streams if s.get('codec_type')=='video' and not s.get('disposition',{}).get('attached_pic')),None)
    if video is None:
        raise ValueError('no video stream')
    duration = float(data.get('format',{}).get('duration') or video.get('duration') or 0)
    if not finite(duration) or duration <= 0 or video.get('width',0)<1 or video.get('height',0)<1:
        raise ValueError('invalid video duration/dimensions')
    numerator, _, denominator = video.get('avg_frame_rate','0/1').partition('/')
    fps = float(numerator)/(float(denominator or 1) or 1)
    if not finite(fps) or fps<0:
        fps=0
    rotation = int(video.get('tags',{}).get('rotate',0))
    for item in video.get('side_data_list',[]):
        rotation = int(item.get('rotation',rotation))
    return {'path':str(path),'name':path.name,'fingerprint':fingerprint(path,deadline),
            'duration':duration,'width':video['width'],'height':video['height'],'fps':fps,
            'has_audio':any(s.get('codec_type')=='audio' for s in streams),
            'codec':video.get('codec_name','unknown'),'rotation':rotation,
            'bit_rate':int(video.get('bit_rate') or 0)}


def validate_result(result, duration, require_tracks=True):
    if result.get('protocol_version')!=1 or result.get('model')!=MODEL:
        raise ValueError('expected an actual pretrained-model result, not mock/classical data')
    summary = result.get('summary')
    if not isinstance(summary,dict) or summary.get('method')!=MODEL or summary.get('weights_sha256')!=WEIGHTS_SHA256:
        raise ValueError('missing or unrecognized pretrained weight provenance')
    for key in ('processing_fps','analysis_fps'):
        if key in summary and (not finite(summary[key]) or summary[key]<0):
            raise ValueError('invalid processing FPS')
    if summary.get('hardware_decode') and summary.get('decoder')!='videotoolbox':
        raise ValueError('hardware decoder provenance mismatch')
    from rally_state import validate_net_region
    validate_net_region(summary.get('net_region'))
    budget=summary.get('calibration_jump_budget',0);samples=summary.get('calibration_jump_samples',0);windows=summary.get('calibration_jump_windows',0)
    if any(type(v) is not int for v in (budget,samples,windows)) or not 0<=samples<=budget<=384 or not 0<=windows<=128:
        raise ValueError('invalid table jump search counters')
    extent=summary.get('calibration_search_extent_seconds',0)
    if not finite(extent) or not 0<=extent<=duration+.25:raise ValueError('invalid calibration inspected extent')
    for event in summary.get('rally_events',[]):
        if event.get('type') not in ('dead_ball','restart') or not event.get('reason') or not event.get('signals'):
            raise ValueError('invalid rally state event')
        if not finite(event.get('time')) or not finite(event.get('confirmed_at')) or not 0<=event['time']<=event['confirmed_at']<=duration+.001:
            raise ValueError('invalid rally event timestamps')
        if not all(finite(event.get(k)) and 0<=event[k]<=1 for k in ('confidence','x','y')):
            raise ValueError('invalid rally event evidence')
    for key in ('decoded_frames','sampled_frames','track_count'):
        if not isinstance(summary.get(key),int) or summary[key]<0:
            raise ValueError('invalid analysis counters')
    if summary['decoded_frames']<1 or not finite(summary.get('elapsed_seconds')) or summary['elapsed_seconds']<0:
        raise ValueError('invalid analysis summary')
    def check_bounds(bounds):
        if bounds is None:return
        if not isinstance(bounds,list) or (len(bounds)!=0 and (len(bounds)!=4 or not all(finite(v) and 0<=v<=1 for v in bounds) or not (bounds[0]<bounds[2] and bounds[1]<bounds[3]))):raise ValueError('invalid table bounds')
    check_bounds(summary.get('table_bounds'))
    if summary.get('table_mode','optional') not in ('optional','off','precalibrate'):raise ValueError('invalid table-mode')
    end=-1
    for segment in summary.get('table_segments',[]):
        lo,hi=segment.get('start'),segment.get('end')
        if not finite(lo) or not finite(hi) or not 0<=lo<hi<=duration+.25 or lo<end:raise ValueError('invalid table geometry intervals')
        check_bounds(segment.get('bounds'));validate_net_region(segment.get('net_region'));end=hi
    rallies=result.get('rallies')
    if not isinstance(rallies,list) or len(rallies)>100000:
        raise ValueError('invalid rally list')
    ids=set()
    for rally in rallies:
        if not isinstance(rally,dict) or not isinstance(rally.get('id'),str) or not rally['id'] or rally['id'] in ids:
            raise ValueError('invalid/duplicate segment id')
        ids.add(rally['id'])
        if not all(isinstance(rally.get(key),bool) for key in ('selected','edited')) or rally.get('evidence','') not in ('','visual','visual+audio'):
            raise ValueError('invalid segment selection/edit/evidence flags')
        start,end=rally.get('start'),rally.get('end')
        if not finite(start) or not finite(end) or not 0<=start<end<=duration:
            raise ValueError('segment timestamp is outside source duration')
        if 'boundary_before' in rally and type(rally['boundary_before']) is not bool:
            raise ValueError('invalid boundary flag')
        if not finite(rally.get('end_event_time',0)) or not 0<=rally.get('end_event_time',0)<=duration:
            raise ValueError('invalid end evidence time')
        if not finite(rally.get('end_confidence',0)) or not 0<=rally.get('end_confidence',0)<=1:
            raise ValueError('invalid end evidence confidence')
        for key,maximum in (('confidence',1),('score',100)):
            if not finite(rally.get(key)) or not 0<=rally[key]<=maximum:
                raise ValueError('invalid segment score')
    tracks=result.get('tracks',[])
    if not isinstance(tracks,list) or summary['track_count']!=len(tracks):
        raise ValueError('invalid track count')
    if require_tracks and rallies and not tracks:
        raise ValueError('candidate results lack real visual track evidence')
    ids=set()
    for track in tracks:
        if not isinstance(track,dict) or not isinstance(track.get('id'),str) or not track['id'] or track['id'] in ids:
            raise ValueError('invalid/duplicate track id')
        ids.add(track['id'])
        if 'off_play' in track and not isinstance(track['off_play'],bool):
            raise ValueError('invalid off_play flag')
        if not isinstance(track.get('points'),list) or not 3<=len(track['points'])<=60:
            raise ValueError('invalid track point count')
        previous=-1
        for point in track['points']:
            timestamp=point.get('t')
            if not finite(timestamp) or not 0<=timestamp<=duration or timestamp<=previous:
                raise ValueError('non-monotonic track timestamps')
            previous=timestamp
            if not all(finite(point.get(k)) and 0<=point[k]<=1 for k in ('x','y','confidence')):
                raise ValueError('invalid normalized track point')
    return result


def timecode(seconds):
    millis=round(seconds*1000)
    hours,millis=divmod(millis,3600000)
    minutes,millis=divmod(millis,60000)
    seconds,millis=divmod(millis,1000)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}'


def compact(source, result, minimum=0, include_tracks=False, origin='fresh_analysis'):
    if not finite(minimum) or minimum<0:
        raise ValueError('min-duration must be finite and nonnegative')
    validate_result(result,source['duration'])
    segments=[]
    for rally in sorted(result['rallies'],key=lambda item:item['start']):
        duration=rally['end']-rally['start']
        if duration<minimum:
            continue
        segments.append({**rally,'duration':round(duration,6),'start_timecode':timecode(rally['start']),
                         'end_timecode':timecode(rally['end']),'review_required':True})
    output={'schema_version':1,'kind':'rallycut.segments','origin':origin,'source':source,
            'model':result['model'],'review_required':True,'segments':segments,
            'runtime_digest':os.environ.get('RALLYCUT_SKILL_RUNTIME_DIGEST'),
            'summary':{**result['summary'],'candidate_count':len(result['rallies']),
                       'output_count':len(segments),'min_duration':minimum}}
    if include_tracks:
        output['tracks']=result['tracks']
    return output


def output_path(path, protected):
    if path=='-':
        return None
    target=Path(path).expanduser().resolve()
    if target in {Path(p).resolve() for p in protected}:
        raise ValueError('refusing to overwrite input/source/project')
    if target.exists() or target.is_symlink():
        raise FileExistsError(f'output already exists: {target}; choose a new file')
    target.parent.mkdir(parents=True,exist_ok=True)
    return target


def publish(target, document):
    if target is None:
        print(json.dumps(document,ensure_ascii=False,allow_nan=False))
        return
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,prefix='.rallycut-',delete=False) as stream:
            temporary=Path(stream.name)
            json.dump(document,stream,ensure_ascii=False,allow_nan=False,indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary,target)  # Atomic no-clobber; never replaces another output.
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(json.dumps({'status':'completed','output':str(target),'segments':len(document['segments']),
                      'review_required':True,'origin':document['origin']},ensure_ascii=False))


def doctor():
    checks={}
    for name in ('ffmpeg','ffprobe'):
        try:
            checks[name]={'ready':True,'path':binary(name)}
        except Exception as error:
            checks[name]={'ready':False,'error':str(error)}
    for name in ('numpy','cv2','torch'):
        try:
            module=importlib.import_module(name)
            checks[name]={'ready':True,'version':module.__version__}
        except Exception as error:
            checks[name]={'ready':False,'error':str(error)}
    try:
        path=locate_weights()
        if path.stat().st_size!=6156034 or hashlib.sha256(path.read_bytes()).hexdigest()!=WEIGHTS_SHA256:
            raise ValueError('weight checksum mismatch')
        checks['model']={'ready':True,'path':str(path),'sha256':WEIGHTS_SHA256}
    except Exception as error:
        checks['model']={'ready':False,'error':str(error)}
    mps=False
    if checks['torch']['ready']:
        import torch
        mps=torch.backends.mps.is_available()
    ready=all(item['ready'] for item in checks.values())
    print(json.dumps({'ready':ready,'checks':checks,'device':'mps' if mps else 'cpu',
                      'weight_redistribution_license':'unconfirmed'},ensure_ascii=False))
    return 0 if ready else 1


def analyze(args):
    deadline=Deadline(args.timeout)
    source=probe(args.input,deadline)
    target=output_path(args.output,[source['path']])
    from neural_analysis import analyze as run_analysis
    recorder=None
    if getattr(args,'dump_l0',None):
        from detection_cache import Recorder
        if Path(args.dump_l0).exists():raise ValueError(f'L0 缓存已存在，拒绝覆盖: {args.dump_l0}')
        recorder=Recorder()
    latest_performance=None
    def on_performance(metrics):
        nonlocal latest_performance
        latest_performance=metrics
    def progress(fraction,message):
        deadline.remaining()
        extra={'performance':latest_performance} if latest_performance is not None else {}
        print(json.dumps({'type':'progress','progress':fraction,'message':message,**extra},ensure_ascii=False),file=sys.stderr,flush=True)
    with tempfile.TemporaryDirectory(prefix='rallycut-audio-') as directory:
        audio=None
        if source['has_audio']:
            audio=str(Path(directory)/'mono.wav')
            progress(0,'extracting local audio')
            command([binary('ffmpeg'),'-v','error','-nostdin','-y','-i',source['path'],
                     '-map','0:a:0','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',audio],deadline)
        result=run_analysis(source['path'],source['duration'],progress,audio_path=audio,device=args.device,calibration_seconds=args.calibration_seconds,
                            precision=args.precision,batch_size=args.batch_size,pipeline=args.pipeline,performance_callback=on_performance,decoder=args.decoder,
                            net_region=args.net_region,calibration_jump_samples=args.calibration_jump_samples,table_mode=args.table_mode,
                            l0_recorder=recorder)
    deadline.remaining()
    if fingerprint(source['path'],deadline)!=source['fingerprint']:
        raise ValueError('source changed during analysis; refusing to publish stale results')
    document=compact(source,result,args.min_duration,args.include_tracks)
    deadline.remaining()
    publish(target,document)
    if recorder is not None:
        recorder.document['source']={'name':Path(source['path']).name,'fingerprint':source['fingerprint'],'duration':source['duration']}
        recorder.save(args.dump_l0)


def from_project(args):
    deadline=Deadline(args.timeout)
    path=Path(args.project).expanduser().resolve(strict=True)
    if path.stat().st_size>32<<20:
        raise ValueError('project exceeds 32 MiB bound')
    with path.open(encoding='utf-8') as stream:
        project=json.load(stream)
    if project.get('schema_version')!=1:
        raise ValueError('unsupported project schema')
    video=project.get('video',{})
    source=probe(video.get('path',''),deadline)
    if source['fingerprint']!=video.get('fingerprint'):
        raise ValueError('source fingerprint mismatch; not reusing saved results')
    target=output_path(args.output,[path,source['path']])
    result={'protocol_version':1,'model':project.get('model'),'summary':project.get('analysis'),
            'rallies':project.get('rallies'),'tracks':project.get('tracks',[])}
    document=compact(source,result,args.min_duration,args.include_tracks,origin='saved_project_timeline')
    document['summary']['manual_timeline']=bool(project.get('manual_timeline'))
    deadline.remaining()
    publish(target,document)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Local table-tennis video -> candidate JSON; no desktop dependencies')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('doctor',help='check FFmpeg/Python/model without downloads')
    for name in ('analyze','from-project'):
        sub=commands.add_parser(name)
        if name=='analyze':
            sub.add_argument('--input',required=True)
            sub.add_argument('--table-mode',choices=['optional','off','precalibrate'],default='optional',help='optional: full-frame detection plus nonblocking geometry; off: no geometry; precalibrate: explicit old search, not required for detection')
            sub.add_argument('--net-region',type=float,nargs=6,metavar=('LX','LT','LB','RX','RT','RB'),help='optional confirmed side-view net endpoints, normalized 0-1; do not guess table midpoint')
            sub.add_argument('--device',choices=['auto','mps','cpu'],default='auto')
            sub.add_argument('--decoder',choices=['opencv','videotoolbox'],default='opencv',help='experimental macOS hardware decode requires optional PyAV; may change color/threshold results')
            sub.add_argument('--precision',choices=['fp32','fp16'],default='fp32',help='FP32 default; FP16 is explicit MPS-only speed mode')
            sub.add_argument('--batch-size',type=int,default=4,help='1-8 three-frame windows per GPU batch; default 4')
            sub.add_argument('--no-pipeline',dest='pipeline',action='store_false',help='disable overlap for sequential diagnosis')
            sub.add_argument('--calibration-seconds',type=float,default=600,help='only with --table-mode precalibrate: initial search horizon (default 600, max 3600)')
            sub.add_argument('--dump-l0',help='also write the L0 detection cache (gzip JSON) for fast rule replay; refuses to overwrite')
            sub.add_argument('--calibration-jump-samples',type=int,default=96,help='extra bounded late-video seek budget (default 96, max 384); 0 disables late search')
        else:
            sub.add_argument('--project',required=True)
        sub.add_argument('--output',required=True,help='new JSON path, or - for stdout')
        sub.add_argument('--min-duration',type=float,default=0)
        sub.add_argument('--include-tracks',action='store_true')
        sub.add_argument('--timeout',type=float,default=1800)
    args=parser.parse_args(argv)
    def interrupted(signum,frame):
        raise InterruptedError(f'cancelled by signal {signum}')
    old={}
    for sig in (signal.SIGINT,signal.SIGTERM):
        old[sig]=signal.signal(sig,interrupted)
    alarm_handler=None
    try:
        if args.command=='doctor':
            return doctor()
        if not finite(args.min_duration) or args.min_duration<0:
            raise ValueError('min-duration must be finite and nonnegative')
        if args.command=='analyze':
            from rally_state import validate_net_region
            validate_net_region(args.net_region)
            from table_jump import validate_jump_budget
            validate_jump_budget(args.calibration_jump_samples)
        if args.command=='analyze' and not 1<=args.batch_size<=8:
            raise ValueError('batch-size must be in 1-8')
        if args.command=='analyze' and args.device=='cpu' and args.precision=='fp16':
            raise ValueError('FP16 requires MPS; use fp32 on CPU')
        if args.command=='analyze' and (not finite(args.calibration_seconds) or not 0<args.calibration_seconds<=3600):
            raise ValueError('calibration-seconds must be finite, positive and <= 3600')
        if not finite(args.timeout) or args.timeout<=0:
            raise ValueError('timeout must be finite and positive')
        if hasattr(signal,'setitimer'):
            def timed_out(signum,frame):
                raise TimeoutError('task timeout; no incomplete candidate JSON was published')
            alarm_handler=signal.signal(signal.SIGALRM,timed_out)
            signal.setitimer(signal.ITIMER_REAL,args.timeout)
        (analyze if args.command=='analyze' else from_project)(args)
        return 0
    except (KeyboardInterrupt,InterruptedError) as error:
        print(json.dumps({'status':'cancelled','error':str(error)}),file=sys.stderr)
        return 130
    except Exception as error:
        print(json.dumps({'status':'failed','error':str(error)},ensure_ascii=False),file=sys.stderr)
        return 1
    finally:
        if alarm_handler is not None:
            signal.setitimer(signal.ITIMER_REAL,0)
            signal.signal(signal.SIGALRM,alarm_handler)
        for sig,previous in old.items():
            signal.signal(sig,previous)


if __name__=='__main__':
    sys.exit(main())
