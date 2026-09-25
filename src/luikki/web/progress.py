"""How far the long buttons have got, for the progress bar.

Segmentation takes minutes on a CPU and the artist watches the bar for all of
it, so the bar must show work that has actually been done. Every tick here is
a pass that has finished — a tile extracted, a panel through one stage of the
cut — weighted by what that pass costs. Nothing is ever advanced by the clock.

Read without the session lock, deliberately: the step being reported holds
that lock for its whole run, and a read that waited for it would only ever
answer once there was nothing left to report.

The payload is codes, never a sentence (`phase`, `index`, `count`). The
browser owns the words, because the words are translated and this file is not.

A cancellable run can be stopped from outside (`cancel`, `POST /api/cancel`).
Nothing is killed: the next `tick` or `at` raises `Cancelled`, so the work
stops between two passes, and the step decides what an unfinished run leaves.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


class Cancelled(Exception):
    """The artist pressed Stop. Raised from inside the run, between passes."""


class Progress:
    """A monotonic fraction of work done, plus where the work is up to."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._running = False
        self._phase: str | None = None
        self._index = 0
        self._count = 0
        self._done = 0.0
        self._total = 1.0
        self._cancellable = False
        self._cancelled = False

    @contextmanager
    def run(self, total: float, cancellable: bool = False) -> Iterator["Progress"]:
        """One long step. Reaches 100 % only if the step finishes.

        Only a `cancellable` run can be stopped: step 5 spends a generation on
        the GPU server, and stopping it halfway would spend it for nothing.
        """
        with self._guard:
            self._running = True
            self._cancellable = cancellable
            self._cancelled = False
            self._phase = None
            self._index = 0
            self._count = 0
            self._done = 0.0
            self._total = max(float(total), 1e-9)
        try:
            yield self
            with self._guard:
                self._done = self._total
        finally:
            with self._guard:
                self._running = False
                self._cancellable = False
                self._cancelled = False

    def cancel(self) -> bool:
        """Ask the run in flight to stop. False when there is none to stop."""
        with self._guard:
            if not (self._running and self._cancellable):
                return False
            self._cancelled = True
            return True

    def _check(self) -> None:
        # Called with the guard held.
        if self._cancelled:
            raise Cancelled()

    def at(self, phase: str, index: int = 0, count: int = 0) -> None:
        """Say where the work is: `segment`, panel 3 of 7."""
        with self._guard:
            self._check()
            self._phase = phase
            self._index = index
            self._count = count

    def tick(self, units: float) -> None:
        """Add finished work. Never goes backwards and never passes the total."""
        with self._guard:
            self._check()
            self._done = min(self._total, self._done + max(0.0, float(units)))

    def snapshot(self) -> dict:
        with self._guard:
            return {
                "running": self._running,
                "cancellable": self._cancellable and not self._cancelled,
                "phase": self._phase,
                "index": self._index,
                "count": self._count,
                "percent": round(100.0 * self._done / self._total, 1),
            }
