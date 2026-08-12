"""
llmits.run_control
==================

Thread-safe play/pause/stop primitive shared by every experiment runner
(Crafter's ExperimentRunner, the paper-folding PaperfoldRunner, ...). Nothing
in here is specific to any one experiment - it only knows about threading.
"""

from __future__ import annotations

import threading


class StopExperiment(Exception):
    """Raised internally to unwind a run loop when the user hits Stop."""


class RunControl:
    """Thread-safe play/pause/stop switch a Studio UI drives.

    The runner calls checkpoint() between units of work (turns, trials, ...);
    it blocks while paused and raises StopExperiment when stopped. `status` is
    a plain dict the UI polls.
    """

    def __init__(self):
        self._resume = threading.Event()
        self._resume.set()          # start un-paused
        self._stopped = False
        self.status: dict = {"state": "idle"}
        self.frame_png: bytes | None = None   # latest rendered frame for the UI

    def pause(self):
        self._resume.clear()
        self.status["state"] = "paused"

    def resume(self):
        self._resume.set()
        self.status["state"] = "running"

    def stop(self):
        self._stopped = True
        self._resume.set()          # unblock any pause so it can exit
        self.status["state"] = "stopping"

    @property
    def paused(self) -> bool:
        return not self._resume.is_set()

    @property
    def stopped(self) -> bool:
        """True once stop() has been called - lets long-running work (e.g. a
        model call stuck in retry backoff) poll for cancellation without
        waiting for the next checkpoint()."""
        return self._stopped

    def checkpoint(self):
        """Block while paused; raise StopExperiment if stopped."""
        self._resume.wait()
        if self._stopped:
            raise StopExperiment()

    def update(self, **kw):
        """Merge a runner's progress into `status`.

        The switch - not the runner - is the authority on whether a run is
        paused. A runner reports state="running" with every turn/trial it
        finishes, and Pause almost always lands mid-turn, so without this the
        next update would paper straight over the pause: the UI would show a
        "running" run that never advances (it's blocked at the next
        checkpoint), and anything keyed off that state - like a Start button
        that doubles as Continue - would have no way to tell it's paused.
        Progress fields still come through; only the state label is held.
        """
        if self.paused:
            kw.pop("state", None)
        self.status.update(kw)
