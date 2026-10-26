#!/usr/bin/env python3
"""Same-video correctness/throughput comparison against a frozen vision snapshot.

Run with project .venv Python. The local BlurBall repo is read-only and NOT an
inference dependency. Output retains per-frame predictions for audit, not labels.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

REPO=Path(__file__).resolve().parents[1]
MODES=('baseline','fp32-sequential','fp32-pipeline','fp16-pipeline')


def run(args):
    runtime=args.baseline if args.mode=='baseline' else REPO/'vision'
    sys.path.insert(0,str(runtime))
    from neural_analysis import analyze
    import cv2
    import torch
    # Warm shader caches, not inference/results. Same trained checkpoint for all.
    from pretrained import BlurBallDetector
    cap=cv2.VideoCapture(str(args.video));prepared=[]
    for _ in range(3):
        ok,frame=cap.read()
        if not ok:raise ValueError('sample needs >=3 frames')
        prepared.append(BlurBallDetector.preprocess(frame))
    cap.release()
    warm=BlurBallDetector(device='mps',**({'precision':'fp16'} if args.mode=='fp16-pipeline' else {}))
    for _ in range(2):warm.predict([prepared]*4)
    torch.mps.synchronize();del warm
    probe=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(args.video)],text=True)
    points=[]
    def record(frame,raw,roi):
        points.append({'t':round(frame['t'],6),'frame_index':frame['frame_index'],'detections':raw,
                       'roi_candidates':[(x/960,y/540,score) for x,y,score in roi]})
    options={} if args.mode=='baseline' else {'precision':'fp16' if args.mode=='fp16-pipeline' else 'fp32',
             'pipeline':args.mode!='fp32-sequential','batch_size':4}
    result=analyze(str(args.video),float(probe),lambda *_:None,frame_callback=record,device='mps',**options)
    torch.mps.synchronize()
    prefix=args.output/(args.video.stem+'-'+args.mode)
    prefix.with_suffix('.analysis.json').write_text(json.dumps(result,ensure_ascii=False))
    prefix.with_suffix('.predictions.json').write_text(json.dumps(points))
    print(json.dumps({'mode':args.mode,'video':str(args.video),'summary':result['summary'],'rallies':len(result['rallies'])},ensure_ascii=False))


def compare(reference,actual,width,height):
    if len(reference)!=len(actual):raise AssertionError('frame coverage changed')
    distances=[];score_deltas=[];mismatched=0;reference_visible=actual_visible=0
    for left,right in zip(reference,actual):
        if left['frame_index']!=right['frame_index'] or abs(left['t']-right['t'])>1e-6:
            raise AssertionError('source frame/PTS order changed')
        reference_visible+=bool(left['roi_candidates']);actual_visible+=bool(right['roi_candidates'])
        a,b=left['detections'],right['detections']
        if len(a)!=len(b):mismatched+=1;continue
        remaining=list(b)
        for point in a:
            near=min(remaining,key=lambda p:math.hypot((point[0]-p[0])*width,(point[1]-p[1])*height))
            remaining.remove(near)
            distances.append(math.hypot((point[0]-near[0])*width,(point[1]-near[1])*height))
            score_deltas.append(abs(point[2]-near[2]))
    return {'frames':len(reference),'reference_visible_frames':reference_visible,'actual_visible_frames':actual_visible,
            'changed_detection_count_frames':mismatched,'matched_points':len(distances),
            'max_coordinate_delta_pixels':max(distances,default=0),'max_heatmap_score_delta':max(score_deltas,default=0),
            'warning':'Output parity, not ground-truth accuracy. FP16 may cross detection/segmentation thresholds.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--video',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=MODES)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if args.mode:
        args.video=args.video[0];run(args);return
    reports=[]
    for video in args.video:
        rows=[]
        for mode in MODES:
            command=[sys.executable,str(Path(__file__).resolve()),'--baseline',str(args.baseline),'--video',str(video),'--output',str(args.output),'--mode',mode]
            process=subprocess.run(command,capture_output=True,text=True,timeout=300)
            if process.returncode:
                raise RuntimeError(f'benchmark mode {mode} failed (not a performance result):\n{process.stdout}\n{process.stderr}')
            record=json.loads(process.stdout);rows.append(record)
            print(json.dumps(record,ensure_ascii=False),flush=True)
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(video)]))['streams'][0]
        base_prefix=args.output/(video.stem+'-baseline')
        reference=json.loads(base_prefix.with_suffix('.predictions.json').read_text())
        baseline_result=json.loads(base_prefix.with_suffix('.analysis.json').read_text())
        for row in rows:
            prefix=args.output/(video.stem+'-'+row['mode'])
            row['comparison']=compare(reference,json.loads(prefix.with_suffix('.predictions.json').read_text()),info['width'],info['height'])
            result=json.loads(prefix.with_suffix('.analysis.json').read_text())
            row['same_rallies']=result['rallies']==baseline_result['rallies']
            row['same_tracks']=result['tracks']==baseline_result['tracks']
            row['speedup']=rows[0]['summary']['elapsed_seconds']/row['summary']['elapsed_seconds']
            row['fps']=row['summary']['decoded_frames']/row['summary']['elapsed_seconds']
        reports.extend(rows)
    report={'results':reports,'note':'Each mode uses the same checkpoint/source and RGB/.7/3-frame inputs; timing excludes audio extraction. Older snapshots may require/gate by tables while current tracking is full-frame: raw detection parity is the comparable numerical test; track/rally differences can be intended policy changes. No accuracy claim.'}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
