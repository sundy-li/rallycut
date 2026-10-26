"""Render source-aligned side-by-side evidence; no network or inference required."""
import argparse
import bisect
import json
from pathlib import Path
import subprocess


def main():
    import cv2
    parser=argparse.ArgumentParser()
    parser.add_argument('--video',required=True)
    parser.add_argument('--classical',type=Path,required=True)
    parser.add_argument('--predictions',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError('output exists; refusing to overwrite')
    predictions=[json.loads(line) for line in args.predictions.read_text().splitlines() if line.strip()]
    times=[p['t'] for p in predictions]
    classical=json.loads(args.classical.read_text())
    old_points={}
    for track in classical['tracks']:
        for p in track['points']:
            old_points.setdefault(round(p['t'],6),[]).append((p['x'],p['y'],p['confidence']))
    cap=cv2.VideoCapture(args.video)
    fps=cap.get(cv2.CAP_PROP_FPS)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    command=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-f','rawvideo','-pix_fmt','bgr24','-s','1920x540','-r',f'{fps:.12g}','-i','pipe:0','-an','-c:v','h264_videotoolbox','-allow_sw','0','-b:v','8233650','-pix_fmt','yuv420p','-movflags','+faststart',str(args.output)]
    segments=[(26,36),(130,140),(350,360),(714,724),(1074,1084)]
    frames=0
    with args.output.with_suffix('.ffmpeg.log').open('wb') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=log)
        try:
            import numpy as np
            for start,end in segments:
                cap.set(cv2.CAP_PROP_POS_MSEC,start*1000)
                while True:
                    ok,frame=cap.read()
                    if not ok:
                        break
                    timestamp=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
                    if timestamp>=end:
                        break
                    if timestamp<start-.02:
                        continue
                    i=bisect.bisect_left(times,timestamp)
                    candidates=[j for j in (i-1,i) if 0<=j<len(times)]
                    nearest=min(candidates,key=lambda j:abs(times[j]-timestamp))
                    raw=predictions[nearest]['detections'] if abs(times[nearest]-timestamp)<.02 else []
                    old=old_points.get(round(timestamp,6),[])
                    small=cv2.resize(frame,(960,540),interpolation=cv2.INTER_AREA)
                    panels=[]
                    for title,points in [('CLASSICAL ACCEPTED TRACKS',old),('BLURBALL RAW HEATMAP >= 0.7',raw)]:
                        panel=small.copy()
                        cv2.rectangle(panel,(0,0),(960,57),(16,20,20),-1)
                        cv2.putText(panel,title,(12,23),cv2.FONT_HERSHEY_SIMPLEX,.65,(160,220,240),1)
                        cv2.putText(panel,f'SOURCE PTS {timestamp:.3f}s | {len(points)} detection(s)',(12,46),cv2.FONT_HERSHEY_SIMPLEX,.5,(220,220,220),1)
                        for x,y,confidence in points:
                            point=(round(x*960),round(y*540))
                            cv2.circle(panel,point,9,(0,190,255),2)
                            cv2.putText(panel,f'{confidence:.2f}',(point[0]+10,point[1]-8),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,190,255),1)
                        panels.append(panel)
                    process.stdin.write(np.hstack(panels).tobytes())
                    frames+=1
            process.stdin.close()
            if process.wait(timeout=60)!=0:
                raise RuntimeError('FFmpeg failed; see adjacent log')
        except BaseException:
            process.kill();process.wait()
            args.output.unlink(missing_ok=True)
            raise
        finally:
            cap.release()
    args.output.with_suffix('.json').write_text(json.dumps({'segments_source_seconds':segments,'frames':frames,'fps':fps,'audio':False,'left':'retained classical tracks','right':'raw pretrained detections; not equivalent postprocessing','note':'Visual review only, no ground-truth overlay or performance claims'},indent=2)+'\n')
    print(f'{frames} frames -> {args.output} (silent visual comparison)')


if __name__=='__main__':
    main()
