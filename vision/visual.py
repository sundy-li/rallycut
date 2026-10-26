"""Original OpenCV baseline: moving-ball candidates + short tracks + rally FSM.

No downloaded weights, no synthetic rallies, no assumed constant frame rate.
Scores are heuristic evidence strength, NOT calibrated detection probabilities.
"""
from dataclasses import dataclass, field
import math
import time

MODEL = "classical-av-v1"

# A serve begins before the first reliable ball observation. This is a
# recognition-boundary lead, separate from export pre-roll. It also lets a
# restart candidate recover the toss that precedes the first tracked point.
SERVE_BOUNDARY_LEAD = 1.6
_TAIL_IDLE_SECONDS = 0.8
_TAIL_WINDOW_SECONDS = 0.35


@dataclass
class Track:
    id: int
    points: list = field(default_factory=list)
    missed: int = 0


def find_table(frame):
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Blue/purple tables only. Green floors must not become a full-frame ROI.
    mask = cv2.inRange(hsv, np.array([113, 43, 35]), np.array([150, 255, 255]))
    mask[:int(h * .30)] = 0
    mask[int(h * .80):] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 17), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    choices = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if w * .32 < bw < w * .95 and bw / max(bh, 1) > 3.5 and bh < h*.22 and area > w * h * .008:
            choices.append((area, (x, y, x + bw, y + bh)))
    return max(choices)[1] if choices else None


def ball_candidates(frame, previous_gray, table, background=None):
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if previous_gray is None:
        return [], gray, 0.0
    diff = cv2.absdiff(gray, previous_gray)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    top_hat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, np.ones((13, 13), np.uint8))
    # Bright, locally isolated, actually moving small objects; large shirt/arm
    # regions are rejected by connected-component geometry below.
    foreground = np.ones_like(gray, dtype=bool) if background is None else gray.astype('float32') > background + 24
    mask = ((diff > 16) & foreground & (top_hat > 13) & (gray > 110) & (hsv[:, :, 1] < 72)).astype('uint8') * 255
    left, top, right, bottom = table
    upper = max(0, int(top - h * .24))
    lower = min(h, int(bottom + h * .025))
    mask[:upper] = 0
    mask[lower:] = 0
    margin = int(w * .08)
    mask[:, :max(0, left-margin)] = 0
    mask[:, min(w, right+margin):] = 0
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
    candidates = []
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if not (2 <= area <= 85 and bw <= 25 and bh <= 18 and bw / max(bh, 1) <= 5):
            continue
        cx, cy = centers[i]
        # Reject component fragments embedded in a much larger moving object.
        pad = 4
        patch = diff[max(0, y-pad):min(h, y+bh+pad), max(0, x-pad):min(w, x+bw+pad)]
        surround = float((patch > 18).mean())
        if surround > .66:
            continue
        quality = min(1.0, float(top_hat[y:y+bh, x:x+bw].max()) / 55) * (1 - surround * .6)
        candidates.append((float(cx), float(cy), quality))
    # Global scene movement invalidates tracking; never turn camera motion into
    # a long rally. The counter also provides a diagnostic in the result.
    motion = float((diff > 20).mean())
    return sorted(candidates, key=lambda c: -c[2])[:60], gray, motion


def update_tracks(active, candidates, timestamp, next_id, width):
    available = set(range(len(candidates)))
    edges = []
    for ti, track in enumerate(active):
        t, x, y, _ = track.points[-1]
        dt = timestamp - t
        if dt <= 0 or dt > .24:
            continue
        px, py = x, y
        if len(track.points) >= 2:
            pt, ox, oy, _ = track.points[-2]
            previous_dt = t - pt
            if previous_dt > 0:
                px += (x - ox) / previous_dt * dt
                py += (y - oy) / previous_dt * dt
        for ci, (cx, cy, quality) in enumerate(candidates):
            distance = math.hypot(cx - x, cy - y)
            residual = math.hypot(cx - px, cy - py)
            limit = width * (.045 + 1.6 * dt)
            if distance <= limit and residual <= limit:
                edges.append((residual + distance * .2 - quality * 5, ti, ci))
    assigned = set()
    for _, ti, ci in sorted(edges):
        if ti in assigned or ci not in available:
            continue
        track = active[ti]
        track.points.append((timestamp, *candidates[ci]))
        track.missed = 0
        assigned.add(ti)
        available.remove(ci)
    done = []
    remaining = []
    for ti, track in enumerate(active):
        if ti not in assigned:
            track.missed += 1
        if timestamp - track.points[-1][0] > .20 or len(track.points) >= 60:
            done.append(track)
        else:
            remaining.append(track)
    for ci in sorted(available):
        remaining.append(Track(next_id, [(timestamp, *candidates[ci])]))
        next_id += 1
    # A pathological scene cannot grow memory without bound.
    remaining.sort(key=lambda t: (-len(t.points), -t.points[-1][3], t.id))
    return remaining[:100], done, next_id


def accepted_track(track, table, width):
    points = track.points
    if len(points) < 3 or points[-1][0] - points[0][0] < .06:
        return False
    xs = [p[1] for p in points]
    ys = [p[2] for p in points]
    if max(xs) - min(xs) < width * .050:
        return False
    left, top, right, bottom = table
    # At least one observation must pass through the central playing corridor.
    # This rejects most isolated hand/shirt motion outside the table.
    core_left = left + (right-left) * .30
    core_right = right - (right-left) * .25
    if not any(core_left <= p[1] <= core_right and top-width*.15 <= p[2] <= bottom for p in points):
        return False
    # Random edge associations can move fast too. Require a coherent short
    # flight rather than accepting arbitrary points merely because they moved.
    import numpy as np
    times = np.array([p[0]-points[0][0] for p in points])
    fit_x = np.polyval(np.polyfit(times, xs, 1), times)
    fit_y = np.polyval(np.polyfit(times, ys, 2), times)
    error = float(np.sqrt(np.mean((fit_x-xs)**2+(fit_y-ys)**2)))
    return error < width*.012


def _valid_table_bounds(table_bounds):
    if not table_bounds or len(table_bounds) != 4:
        return None
    left, top, right, bottom = table_bounds
    if not (right > left and bottom > top):
        return None
    return table_bounds


def _active_flight(group, index, table_bounds):
    """Whether a local observation belongs to a plausible ball flight.

    Excludes below-table pickup motion and implausible detector jumps. The
    window is centered so the final real hit is not lost merely because the
    replay ends or the ball becomes occluded afterwards.
    """
    center = group[index][0]
    bounds = _valid_table_bounds(table_bounds)
    bottom = bounds[3] if bounds else None
    width = bounds[2] - bounds[0] if bounds else None
    height = bounds[3] - bounds[1] if bounds else None
    relevant = [p for p in group if abs(p[0] - center) <= _TAIL_WINDOW_SECONDS / 2]
    if bounds:
        relevant = [p for p in relevant if p[2] <= bottom + height * .05]
    if len(relevant) < 3:
        return False
    elapsed = relevant[-1][0] - relevant[0][0]
    if elapsed < .1:
        return False
    max_step = max(.13, width * .2) if bounds else .18
    path = 0.0
    for previous, point in zip(relevant, relevant[1:]):
        dt = point[0] - previous[0]
        distance = math.hypot(point[1] - previous[1], point[2] - previous[2])
        if 0 < dt <= .16 and distance <= max_step:
            path += distance
    # A real cross-table flight is much faster than a rolling/pickup tail. The
    # higher geometry-scaled threshold avoids treating slow ball drift as play.
    min_speed = max(.32, width * .6) if bounds else .35
    return path / elapsed >= min_speed


def _trim_inactive_tail(group, table_bounds=None):
    """Drop pickup/return-ball motion after a sustained inactive tail."""
    if len(group) < 3:
        return group
    active = [_active_flight(group, index, table_bounds) for index in range(len(group))]
    last_active = -1
    index = 0
    while index < len(group):
        if active[index]:
            last_active = index
            index += 1
            continue
        start = group[index][0]
        end = index
        while end + 1 < len(group) and group[end + 1][0] < start + _TAIL_IDLE_SECONDS:
            end += 1
        if group[end][0] - start >= _TAIL_IDLE_SECONDS * .75 and not any(active[index:end + 1]):
            if last_active >= 0:
                return group[:last_active + 1]
        index += 1
    return group


def segment_rallies(tracks, duration, gap=1.15, min_duration=1.0, min_observations=8, min_bins=4,
                    first_min_duration=None, first_min_observations=None, first_min_bins=None,
                    start_lead=.45, table_bounds=None):
    """Event-time FSM; no fixed windows, no maximum-duration chopping."""
    observations = sorted(p for track in tracks for p in track.points)
    if not observations:
        return []
    groups = []
    group = [observations[0]]
    for point in observations[1:]:
        if point[0] - group[-1][0] > gap:
            groups.append(group)
            group = []
        group.append(point)
    groups.append(group)
    rallies = []
    for index, group in enumerate(groups):
        # Slow/ below-table pickup motion is not part of the rally, and a later
        # return toss must not rejoin it after a sustained inactive gap.
        group = _trim_inactive_tail(group, table_bounds)
        first, last = group[0][0], group[-1][0]
        # A serve starts the point: keep the first flight even when it faults
        # immediately, and let the user delete it later.
        min_length = first_min_duration if index == 0 and first_min_duration is not None else min_duration
        min_points = first_min_observations if index == 0 and first_min_observations is not None else min_observations
        min_moments = first_min_bins if index == 0 and first_min_bins is not None else min_bins
        if last-first < min_length or len(group) < min_points:
            continue
        # Evidence must occupy several distinct moments, not one noisy burst.
        bins = len({int(p[0] * 5) for p in group})
        if bins < min_moments:
            continue
        start, end = max(0, first-start_lead), min(duration, last+.55)
        evidence = min(.85, .30 + min(.35, bins/max(1, (last-first)*5)*.35) + min(.2, len(group)/100))
        length = end-start
        rallies.append({'id': f'visual-{len(rallies)+1:05d}', 'start': round(start, 6),
                        'end': round(end, 6), 'confidence': round(evidence, 3),
                        'score': round(min(100, length/20*70 + min(30, bins)), 1),
                        'selected': True, 'edited': False})
    return rallies


def analyze(video_path, duration, progress, max_seconds=None, audio_path=None):
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError('缺少视觉依赖，请在项目目录运行 just setup；或设置 RALLYCUT_PYTHON3 为已安装 OpenCV / NumPy 的 Python') from exc
    cv2.setNumThreads(1)
    cap = cv2.VideoCapture(str(video_path), cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise ValueError('无法打开视频，未生成任何模拟结果')
    started = time.monotonic()
    active, accepted = [], []
    previous_gray = None
    background = None
    table = None
    next_id = 1
    decoded = sampled = scene_changes = 0
    previous_t = -1.0
    last_report = -1.0
    target = min(duration, max_seconds) if max_seconds else duration
    analysis_width, analysis_height = 960, 540
    try:
        while cap.grab():
            decoded += 1
            # Fast balls can cross the table in a handful of frames. Decode
            # every source frame; timestamp comes from the decoder, not / 30.
            ok, frame = cap.retrieve()
            if not ok:
                raise ValueError(f'视频解码失败，已解码 {decoded} 帧')
            timestamp = float(cap.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            if not math.isfinite(timestamp) or timestamp <= previous_t:
                raise ValueError('解码器未提供单调视频时间戳，拒绝使用固定帧率伪造时间轴')
            previous_t = timestamp
            if timestamp >= target:
                break
            h, w = frame.shape[:2]
            frame = cv2.resize(frame, (960, max(1, round(h*960/w))), interpolation=cv2.INTER_AREA)
            analysis_height, analysis_width = frame.shape[:2]
            if table is None:
                table = find_table(frame)
                if table is None:
                    if timestamp > 10:
                        raise ValueError('前 10 秒未找到蓝色/紫色球桌；当前基线仅支持固定机位蓝/紫球桌，不会退回模拟结果')
                    continue
            candidates, gray, motion = ball_candidates(frame, previous_gray, table, background)
            if background is None:
                background = gray.astype('float32')
            else:
                cv2.accumulateWeighted(gray, background, .025)
            previous_gray = gray
            sampled += 1
            if motion > .45:
                scene_changes += 1
                active = []
                continue
            active, done, next_id = update_tracks(active, candidates, timestamp, next_id, 960)
            accepted.extend(t for t in done if accepted_track(t, table, 960))
            if timestamp-last_report >= 2:
                progress(min(.94, timestamp/target*.94), f'真实画面分析 {timestamp:.0f} / {target:.0f} 秒 · 已提取 {len(accepted)} 条候选短轨迹')
                last_report = timestamp
        if decoded < 1:
            raise ValueError('视频没有可解码画面')
        if previous_t < target - max(2.0, target*.002):
            raise ValueError(f'视频提前结束：只读取到 {previous_t:.2f} / {target:.2f} 秒，不保存不完整分析')
        if table is None:
            raise ValueError('未找到支持的蓝/紫球桌，不生成占位回合')
        accepted.extend(t for t in active if accepted_track(t, table, 960))
        accepted.sort(key=lambda t: t.points[0][0])
        rallies = segment_rallies(accepted, target)
        from audio_features import impact_times, fuse_audio_visual
        impacts = impact_times(audio_path) if audio_path else []
        rallies = fuse_audio_visual(rallies, accepted, impacts, target, mode='legacy')
        h, w = analysis_height, analysis_width
        tracks = [{'id': str(t.id), 'points': [{'t': round(p[0], 6), 'x': round(p[1]/w, 6),
                   'y': round(p[2]/h, 6), 'confidence': round(p[3], 3)} for p in t.points]} for t in accepted]
        warnings = ['传统视觉实验基线；置信度是启发式证据强度，不是识别准确率。',
                    '仅支持固定机位蓝/紫球桌；遮挡、白衣和背景球可能误检。',
                    '击球声仅辅助视觉分段；脚步、说话和邻桌声音可能干扰，不是已验收的识别模型。']
        if not rallies:
            warnings.append('没有发现足够的连续球轨迹，不生成占位回合。可手动标记或更换检测路线。')
        return {'protocol_version': 1, 'model': MODEL, 'rallies': rallies, 'tracks': tracks,
                'summary': {'method': MODEL, 'decoded_frames': decoded, 'sampled_frames': sampled,
                            'track_count': len(tracks), 'elapsed_seconds': round(time.monotonic()-started, 3),
                            'table_bounds': [round(table[0]/w, 6), round(table[1]/h, 6), round(table[2]/w, 6), round(table[3]/h, 6)] if table else [],
                            'scene_changes': scene_changes, 'audio_impacts':len(impacts), 'warnings': warnings}}
    finally:
        cap.release()
