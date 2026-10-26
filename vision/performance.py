"""Count completed analysis frames, not source nominal FPS or GPU-only peaks."""
import time


class ProcessingRate:
    def __init__(self, clock=time.perf_counter):
        self.clock=clock
        self.started=clock()
        self.previous_time=self.started
        self.previous_frames=0
        self.frames=0

    def add(self, count=1):
        self.frames+=count

    def snapshot(self):
        now=self.clock()
        elapsed=max(0,now-self.started)
        interval=max(0,now-self.previous_time)
        recent=(self.frames-self.previous_frames)/interval if interval>0 else 0
        average=self.frames/elapsed if elapsed>0 else 0
        self.previous_time,self.previous_frames=now,self.frames
        return {'stage':'inference','processed_frames':self.frames,'elapsed_seconds':round(elapsed,6),
                'recent_fps':round(recent,2),'average_fps':round(average,2)}
