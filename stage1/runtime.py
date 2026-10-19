"""Progress and cooperative cancellation without coupling to a user interface."""
import time


class RunCancelled(Exception):
    pass


class RunControl:
    def __init__(self, progress=None, cancelled=None):
        self.progress = progress or (lambda percent, message: None)
        self.cancelled = cancelled or (lambda: False)
        self.started = time.perf_counter()
        self.timings = {}
        self.last_phase = None
        self.phase_started = self.started

    def check(self):
        if self.cancelled():
            raise RunCancelled('Run cancelled. Earlier results have been preserved.')

    def update(self, percent, message):
        self.check()
        self.progress(max(0, min(100, percent)), message)
        self.check()

    def phase(self, percent, message):
        now = time.perf_counter()
        if self.last_phase:
            self.timings[self.last_phase] = round(now - self.phase_started, 4)
        self.last_phase, self.phase_started = message, now
        self.update(percent, message)

    def finish(self):
        self.phase(100, 'Completed')
        return {'total_seconds': round(time.perf_counter() - self.started, 4), 'phases_seconds': self.timings}
