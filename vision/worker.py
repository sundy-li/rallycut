#!/usr/bin/env python3
"""Versioned JSONL worker. Production accepts only real video analysis.

Missing dependencies/unsupported input fail explicitly; never fall back to mocks.
"""
import json
import math
import sys
from pretrained import MODEL
from visual import MODEL as CLASSICAL_MODEL

PROTOCOL_VERSION = 1


def emit(job_id: str, event_type: str, **kwargs) -> None:
    print(json.dumps({'protocol_version': PROTOCOL_VERSION, 'job_id': job_id,
                      'type': event_type, **kwargs}, allow_nan=False, separators=(',', ':')), flush=True)


def main() -> int:
    job_id = 'unknown'
    try:
        line = sys.stdin.buffer.readline(65537)
        if len(line) > 65536:
            raise ValueError('request exceeds 64 KiB')
        request = json.loads(line)
        job_id = request.get('job_id', 'unknown')
        if request.get('protocol_version') != PROTOCOL_VERSION:
            raise ValueError('unsupported protocol_version')
        if request.get('type') != 'analyze' or not isinstance(job_id, str) or not job_id:
            raise ValueError('invalid request')
        detector = request.get('config', {}).get('detector')
        if detector == MODEL:
            from neural_analysis import analyze
        elif detector == CLASSICAL_MODEL:
            from visual import analyze
        else:
            raise ValueError(f'unsupported detector; use {MODEL} or explicit {CLASSICAL_MODEL}, not mock-v1')
        duration = float(request['duration'])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('duration must be finite and positive')
        config=request.get('config',{})
        options={'table_mode':config.get('table_mode','optional'),'calibration_seconds':config.get('calibration_seconds',600),
                 'calibration_jump_samples':config.get('calibration_jump_samples',96),
                 'precision':config.get('precision','fp32'),'batch_size':config.get('batch_size',4),
                 'pipeline':config.get('pipeline',True),'decoder':config.get('decoder','opencv'),
                 'net_region':config.get('net_region')} if detector==MODEL else {}
        latest_performance=None
        def on_performance(metrics):
            nonlocal latest_performance
            latest_performance=metrics
        def on_progress(value,message):
            extra={'performance':latest_performance} if latest_performance is not None else {}
            emit(job_id,'progress',progress=value,message=message,**extra)
        def on_candidates(rallies,processed_seconds,tracks,table_bounds):
            emit(job_id,'candidates',processed_seconds=processed_seconds,rallies=rallies,
                 tracks=tracks,table_bounds=table_bounds)
        if detector==MODEL:
            options['performance_callback']=on_performance
            options['candidates_callback']=on_candidates
        result = analyze(request['video_path'], duration,
                         on_progress,
                         audio_path=request.get('audio_path'), **options)
        emit(job_id, 'result', result=result)
        return 0
    except Exception as exc:
        emit(job_id, 'error', message=str(exc))
        return 1


if __name__ == '__main__':
    sys.exit(main())
