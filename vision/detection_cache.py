"""L0 detection cache: record the slow model stage once, replay the rest fast.

A fresh analysis can write every scored frame's (PTS, shot snapshot, raw model
points) plus the detector's final shot state, cuts, geometry segments and audio
impacts.  `replay` feeds the same sequence through neural_analysis.TrackingStage
(tracking -> rally rules -> play area), so the replay of an unchanged pipeline
equals the fresh result; only tracking / rule changes need no new inference.

The cache is keyed by `detection_digest`: model, weights, the source of every
stage that runs before TrackingStage, and the inference parameters.  A cache
whose digest differs from the current code must not be replayed as evidence.
"""
import gzip
import hashlib
import inspect
import json
import os
from pathlib import Path

FORMAT='rallycut-l0'
VERSION=1
_HERE=Path(__file__).resolve().parent
# Everything that runs before TrackingStage (decode, shot / geometry monitor,
# model, audio impacts).  rally_*, play_area, visual.update_tracks are L1/L2.
L0_SOURCES=('pretrained.py','backends.py','video_decode.py','shot_boundary.py','table_locator.py','table_jump.py',
            'net_geometry.py','audio_features.py','inference_pipeline.py','vendor/blurball/network.py',
            'vendor/blurball/config.json')


def source_digest():
    import neural_analysis
    import visual
    h=hashlib.sha256()
    for name in L0_SOURCES:
        h.update(name.encode()+b'\0'+(_HERE/name).read_bytes()+b'\0')
    for obj in (neural_analysis.DetectionRun,visual.find_table):
        h.update(obj.__qualname__.encode()+b'\0'+inspect.getsource(obj).encode()+b'\0')
    return h.hexdigest()


def detection_key(model,weights_sha256,device,precision,batch_size,decoder,table_mode,
                  calibration_seconds=None,calibration_jump_samples=None,audio=True):
    key={'format':FORMAT,'version':VERSION,'model':model,'weights_sha256':weights_sha256,'device':device,
         'precision':precision,'batch_size':batch_size,'decoder':decoder,'table_mode':table_mode,
         'audio':bool(audio),'sources':source_digest()}
    if table_mode=='precalibrate':
        key.update(calibration_seconds=calibration_seconds,calibration_jump_samples=calibration_jump_samples)
    return key


def digest(key):
    return hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()


def _shot(snapshot):
    return [snapshot.shot_id,snapshot.shot_start,list(snapshot.bounds),list(snapshot.net),snapshot.method]


class Recorder:
    """Collect L0 during a fresh run; `save` after the analysis succeeded."""
    def __init__(self):
        self.frames_t=[];self.frames_shot=[];self.frames_raw=[]
        self.shots=[];self._index={}
        self.document=None

    def start(self,run,impacts,audio):
        self.impacts=[float(t) for t in impacts];self.audio=bool(audio)

    def _shot_index(self,snapshot):
        index=self._index.get(snapshot)
        if index is None:
            index=self._index[snapshot]=len(self.shots);self.shots.append(_shot(snapshot))
        return index

    def frame(self,timestamp,snapshot,raw):
        self.frames_t.append(timestamp);self.frames_shot.append(self._shot_index(snapshot))
        self.frames_raw.append([[float(x),float(y),float(s)] for x,y,s in raw])

    def finish(self,run,duration):
        monitor,detector=run.monitor,run.detector
        key=detection_key(_model(),detector.sha256,detector.device,getattr(detector,'precision',run.precision),
                          run.batch_size,run.decoder,run.table_mode,run.calibration_seconds,run.calibration_jump_samples,
                          audio=self.audio)
        self.document={'format':FORMAT,'version':VERSION,'key':key,'digest':digest(key),'duration':duration,
                       'impacts':self.impacts,'shots':self.shots,
                       'frames':{'t':self.frames_t,'shot':self.frames_shot,'raw':self.frames_raw},
                       'final':{'state':_shot(monitor.state),'cuts':list(monitor.cuts),'segments':monitor.segments(duration),
                                'warnings':list(monitor.warnings),'motion_vetoes':monitor.motion_vetoes,
                                'drift_follows':monitor.drift_follows,'drift_resets':monitor.drift_resets},
                       'stats':{'decoded_frames':run.decoded,'sampled_frames':run.rates.frames,'duplicate_frames':run.duplicates,
                                'unscored_frames':run.unique-run.rates.frames,'hardware_decode':run.decode_state.get('hardware_decode',False)}}

    def save(self,path):
        if self.document is None:raise ValueError('L0 recorder has no finished run')
        target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_name(target.name+f'.{os.getpid()}.tmp')
        with gzip.open(temporary,'wt',encoding='utf-8') as stream:
            json.dump(self.document,stream,separators=(',',':'),allow_nan=False)
        os.replace(temporary,target)
        return target


def _model():
    from pretrained import MODEL
    return MODEL


def load(path):
    with gzip.open(path,'rt',encoding='utf-8') as stream:document=json.load(stream)
    if document.get('format')!=FORMAT or document.get('version')!=VERSION:raise ValueError(f'{path}: not a RallyCut L0 cache')
    frames=document['frames']
    if not len(frames['t'])==len(frames['shot'])==len(frames['raw']):raise ValueError(f'{path}: broken frame arrays')
    return document


def stale_reason(document):
    """None when the cache matches the current L0 code, else why not."""
    key=dict(document['key']);current=source_digest()
    if key.get('sources')!=current:return 'L0 源码已变化（解码 / 切镜 / 几何 / 模型 / 声音），需要新鲜推理'
    if digest(key)!=document.get('digest'):return 'L0 缓存摘要不一致'
    return None


def replay(document,net_region=None):
    """Run tracking + rally rules on a cached detection; returns rallies/tracks/summary subset."""
    from shot_boundary import ShotSnapshot
    from neural_analysis import TrackingStage
    shots=[ShotSnapshot(int(i),float(t),tuple(b),tuple(n),m) for i,t,b,n,m in document['shots']]
    stage=TrackingStage(document['duration'],document['impacts'],net_region)
    frames=document['frames']
    for timestamp,index,raw in zip(frames['t'],frames['shot'],frames['raw']):
        stage.observe(timestamp,shots[index],[tuple(p) for p in raw])
    i,t,b,n,m=document['final']['state']
    rallies,tracks=stage.finish(ShotSnapshot(int(i),float(t),tuple(b),tuple(n),m),list(document['final']['cuts']))
    return {'rallies':rallies,'tracks':tracks,
            'summary':{'rally_events':stage.validity.events,'table_segments':document['final']['segments'],
                       'camera_cuts':len(document['final']['cuts']),'track_count':len(tracks)}}
