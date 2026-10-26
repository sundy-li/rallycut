"""Audio transients support visual evidence; never create audio-only rallies."""
import wave


def impact_times(path):
    import numpy as np
    frequencies = np.fft.rfftfreq(512, 1/16000)
    band = (frequencies > 1200) & (frequencies < 7000)
    window = np.hanning(512).astype('float32')
    chunks = []
    tail = np.empty(0, dtype='float32')
    with wave.open(str(path), 'rb') as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
            raise ValueError('audio must be mono 16-bit PCM at 16 kHz')
        while True:
            raw = wav.readframes(160*1024)
            if not raw:
                break
            samples = np.concatenate((tail, np.frombuffer(raw, '<i2').astype('float32')/32768))
            if len(samples) < 512:
                tail = samples
                continue
            frames = np.lib.stride_tricks.sliding_window_view(samples, 512)[::160]
            power = np.abs(np.fft.rfft(frames*window))**2
            chunks.append(np.mean(power[:, band], axis=1).astype('float32'))
            tail = samples[len(frames)*160:]
    if not chunks:
        return []
    energy = np.concatenate(chunks)
    size = min(101, len(energy))
    baseline = np.convolve(energy, np.ones(size)/size, mode='same')
    strength = energy / np.maximum(baseline, .00001)
    absolute = max(.01, float(np.percentile(energy, 20))*2)
    peaks = []
    for index in np.flatnonzero((strength > 3) & (energy > absolute)):
        index = int(index)
        if peaks and index-peaks[-1] < 10:
            if strength[index] > strength[peaks[-1]]:
                peaks[-1] = index
        else:
            peaks.append(index)
    return [round(index*.01, 6) for index in peaks]


def fuse_audio_visual(visual_rallies, tracks, impacts, duration, mode='legacy'):
    """Combine accepted visual rallies with impact-like sounds.

    mode='confirm' (default for analysis) only labels rallies that already exist:
    audio never creates, extends or scores one. Shared courts make adjacent-table
    hits a real source of error, so boundaries stay visual. mode='legacy' keeps
    the historical behaviour for comparison runs.
    """
    if mode == 'confirm':
        ordered = sorted(timestamp for timestamp in impacts if timestamp <= duration)
        result = [dict(rally, evidence=rally.get('evidence') or 'visual') for rally in visual_rallies]
        for rally in result:
            hits = [t for t in ordered if rally['start'] - .15 <= t <= rally['end'] + .15]
            if hits:
                # Advisory count only: shared courts make the sound ambiguous, so
                # it must not read as "audio confirmed this rally".
                rally['audio_hits'] = len(hits)
        return result
    observations = sorted(p[0] for track in tracks for p in track.points)
    if not observations:
        return []
    groups = []
    for timestamp in impacts:
        if timestamp > duration:
            break
        if not groups or timestamp-groups[-1][-1] > 1.05:
            groups.append([])
        groups[-1].append(timestamp)
    candidates = [dict(rally, evidence='visual') for rally in visual_rallies]
    for group in groups:
        if len(group) < 3 or group[-1]-group[0] < .7:
            continue
        nearby = [t for t in observations if group[0]-.7 <= t <= group[-1]+.7]
        if len(nearby) < 3:
            continue
        supported=any(r['start']<=group[-1]+.7 and r['end']>=group[0]-.7 for r in visual_rallies)
        if not supported:
            # Sparse occluded flight can corroborate audio, but three static
            # blobs / slow preparation cannot turn neighbouring-table sounds
            # into a rally. Compare motion within ONE coherent track, never
            # apparent travel between unrelated detections. No geometry needed.
            for track in tracks:
                points=[p for p in track.points if group[0]-.7<=p[0]<=group[-1]+.7]
                if len(points)<3:continue
                elapsed=points[-1][0]-points[0][0]
                if elapsed<.05:continue
                dx=(max(p[1] for p in points)-min(p[1] for p in points))/960
                dy=(max(p[2] for p in points)-min(p[2] for p in points))/540
                travel=(dx*dx+dy*dy)**.5
                if travel>.04 and travel/elapsed>.35:
                    supported=True;break
        if not supported:continue
        start, end = max(0, min(group[0], nearby[0])-.5), min(duration, max(group[-1], nearby[-1])+.6)
        candidates.append({'start': start, 'end': end, 'confidence': min(.8, .4+len(group)*.025),
                           'score': min(100, (end-start)/20*70+len(group)*2),
                           'selected': True, 'edited': False, 'evidence':'visual+audio'})
    candidates.sort(key=lambda r: r['start'])
    result = []
    for candidate in candidates:
        if result and candidate['start'] <= result[-1]['end']:
            previous = result[-1]
            previous['end'] = max(previous['end'], candidate['end'])
            previous['confidence'] = max(previous['confidence'], candidate['confidence'])
            previous['score'] = max(previous['score'], candidate['score'])
            if candidate['evidence'] == 'visual+audio':
                previous['evidence'] = 'visual+audio'
        else:
            result.append(candidate)
    for index, rally in enumerate(result):
        rally['id'] = f'visual-{index+1:05d}'
        rally['start'], rally['end'] = round(rally['start'], 6), round(rally['end'], 6)
        rally['confidence'], rally['score'] = round(rally['confidence'], 3), round(rally['score'], 1)
    return result
