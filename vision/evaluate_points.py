"""Reproducible tiny-sample point evaluation. No proxy-labeling by detector score."""
import argparse
import bisect
import json
import math
from pathlib import Path


def evaluate(labels, predictions):
    width, height = labels['source_dimensions']
    times = [p['t'] for p in predictions]
    tolerance = labels['tolerance_pixels']
    tp = fp = fn = tn = excluded = 0
    details = []
    for sample in labels['samples']:
        if sample['visibility'] == 'uncertain':
            excluded += 1
            continue
        index = bisect.bisect_left(times,sample['t'])
        options=[i for i in (index-1,index) if 0<=i<len(times)]
        index=min(options,key=lambda i:abs(times[i]-sample['t'])) if options else None
        if index is None or abs(times[index]-sample['t'])>.02:
            raise ValueError(f"no prediction record at PTS {sample['t']}")
        points = predictions[index]['detections']
        gt=sample['xy']
        errors=[math.hypot(x*width-gt[0],y*height-gt[1]) for x,y,_ in points] if gt else []
        matched=bool(errors and min(errors)<=tolerance)
        if gt:
            tp+=matched;fn+=not matched;fp+=len(points)-int(matched)
        else:
            fp+=len(points);tn+=not bool(points)
        details.append({**sample,'predictions':points,'nearest_error_pixels':round(min(errors),3) if errors else None,'matched':matched})
    return {'tp':tp,'fp':fp,'fn':fn,'true_negative_frames':tn,'excluded_uncertain_frames':excluded,
            'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
            'tolerance_pixels':tolerance,'details':details,
            'limitations':'Tiny single-video assistant-reviewed sample, not user-confirmed/independent ground truth. NOT full-match accuracy or rally recall.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--labels',type=Path,required=True)
    parser.add_argument('--predictions',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    labels=json.loads(args.labels.read_text())
    predictions=[json.loads(line) for line in args.predictions.read_text().splitlines() if line.strip()]
    predictions.sort(key=lambda p:p['t'])
    report=evaluate(labels,predictions)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='details'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
