#!/usr/bin/env python3
"""VideoToolbox A/B experiment, never silently installed/selected at runtime.

Requires optional av==16.1.0. Validates hardware use, compares actual source PTS,
pixels and trained-model outputs. No resize/conversion shortcuts for hardware.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'vision'))
sys.path.insert(0,str(REPO/'scripts'))


def run_mode(args):
    import av
    import cv2
    import numpy as np
    import torch
    from av.codec.hwaccel import HWAccel
    import neural_analysis
    from table_locator import calibrate
    from pretrained import BlurBallDetector
    native_capture=cv2.VideoCapture
    decoder_state=[]
    class AVCapture:
        def __init__(self,path,*_):
            kwargs={'hwaccel':HWAccel('videotoolbox',allow_software_fallback=False)} if args.mode=='videotoolbox' else {}
            self.container=av.open(str(path),**kwargs)
            self.stream=self.container.streams.video[0]
            self.frames=iter(self.container.decode(self.stream));self.frame=None
            self.origin=self.stream.start_time or 0
        def isOpened(self):return True
        def grab(self):
            try:self.frame=next(self.frames)
            except StopIteration:return False
            if not decoder_state:
                active=bool(self.stream.codec_context.is_hwaccel)
                if args.mode=='videotoolbox' and not active:raise ValueError('hardware decode not active')
                decoder_state.append({'hardware_active':active,'surface_format':self.stream.codec_context.format.name,
                                      'frame_format':self.frame.format.name})
            return True
        def retrieve(self):return True,self.frame.to_ndarray(format='bgr24')
        def get(self,prop):
            if prop!=cv2.CAP_PROP_POS_MSEC:raise ValueError('unexpected capture property')
            if self.frame.pts is None:raise ValueError('missing source PTS')
            return float((self.frame.pts-self.origin)*self.frame.time_base)*1000
        def release(self):self.container.close()
    capture=native_capture if args.mode=='opencv' else AVCapture
    cv2.setNumThreads(1)
    cap=capture(str(args.video),cv2.CAP_FFMPEG)
    start=time.perf_counter();n=0;times=[]
    while cap.grab():
        ok,_=cap.retrieve()
        if not ok:raise ValueError('decode failed')
        times.append(cap.get(cv2.CAP_PROP_POS_MSEC)/1000);n+=1
    elapsed=time.perf_counter()-start;cap.release()
    # Record every 30th decoded source frame for color/conversion parity, outside
    # the timing pass. Independent readers preserve presentation order.
    cap=capture(str(args.video),cv2.CAP_FFMPEG);images=[];index=0
    while cap.grab():
        ok,image=cap.retrieve()
        if not ok:raise ValueError('decode failed')
        if index%30==0:images.append(image)
        index+=1
    cap.release()
    stem=args.video.stem+'-'+args.mode
    np.savez_compressed(args.output/(stem+'.pixels.npz'),frames=np.stack(images),pts=np.array(times))
    duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(args.video)],text=True))
    calibration=calibrate(str(args.video),duration,lambda *_:None)
    warm=BlurBallDetector(device='mps');one=warm.prepare_frame(images[0])
    for _ in range(2):warm.predict([[one]*3]*4)
    torch.mps.synchronize();del warm
    predictions=[]
    def record(frame,raw,roi):predictions.append({'t':round(frame['t'],6),'frame_index':frame['frame_index'],
          'detections':raw,'roi_candidates':[(x/960,y/540,s) for x,y,s in roi]})
    with patch('table_locator.calibrate',return_value=calibration),patch.object(cv2,'VideoCapture',capture):
        result=neural_analysis.analyze(str(args.video),duration,lambda *_:None,device='mps',frame_callback=record,table_mode='precalibrate',
                decoder='videotoolbox' if args.mode=='videotoolbox' else 'opencv')
    result['summary']['decoder']=args.mode
    result['summary']['hardware_decode']=args.mode=='videotoolbox'
    (args.output/(stem+'.predictions.json')).write_text(json.dumps(predictions))
    (args.output/(stem+'.analysis.json')).write_text(json.dumps(result,ensure_ascii=False))
    print(json.dumps({'video':str(args.video),'mode':args.mode,'decode_frames':n,'decode_seconds':elapsed,
        'decode_fps':n/elapsed,'decoder':decoder_state[0] if decoder_state else {'hardware_active':False},
        'summary':result['summary'],'rallies':len(result['rallies']),
        'calibration_reused':True,'timing_scope':'stream wall_seconds is the fair comparison; summary elapsed excludes reused calibration and audio extraction'},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--video',action='append',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=['opencv','pyav-software','videotoolbox'])
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if args.mode:
        args.video=args.video[0];run_mode(args);return
    import numpy as np
    from benchmark_mps import compare
    rows=[]
    for video in args.video:
        current=[]
        for mode in ('opencv','pyav-software','videotoolbox'):
            command=[sys.executable,str(Path(__file__).resolve()),'--video',str(video),'--output',str(args.output),'--mode',mode]
            run=subprocess.run(command,capture_output=True,text=True,timeout=300)
            if run.returncode:raise RuntimeError(f'{mode} failed, not a performance result:\n{run.stdout}\n{run.stderr}')
            row=json.loads(run.stdout);current.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
        reference=np.load(args.output/(video.stem+'-opencv.pixels.npz'))
        points=json.loads((args.output/(video.stem+'-opencv.predictions.json')).read_text())
        baseline=json.loads((args.output/(video.stem+'-opencv.analysis.json')).read_text())
        for row in current:
            prefix=video.stem+'-'+row['mode']
            actual=np.load(args.output/(prefix+'.pixels.npz'))
            if reference['pts'].shape!=actual['pts'].shape:raise ValueError('frame coverage changed')
            row['pts_max_delta_seconds']=float(np.max(np.abs(reference['pts']-actual['pts'])))
            delta=np.abs(reference['frames'].astype('int16')-actual['frames'].astype('int16'))
            row['pixel_max_delta']=int(delta.max());row['pixel_mean_abs_delta']=float(delta.mean())
            height,width=reference['frames'].shape[1:3]
            row['comparison']=compare(points,json.loads((args.output/(prefix+'.predictions.json')).read_text()),width,height)
            result=json.loads((args.output/(prefix+'.analysis.json')).read_text())
            row['same_tracks']=result['tracks']==baseline['tracks'];row['same_rallies']=result['rallies']==baseline['rallies']
        rows.extend(current)
    report={'results':rows,'limitations':'Short local samples, calibration reused outside inference timing, excludes audio extraction; PyAV uses its own bundled FFmpeg. Decoder+RGB conversion differences must not be presented as bit-exact optimization.'}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
