"""Per-camera analytics over tracked objects. Pure logic: no I/O, no clock, fully unit-testable."""
from collections import defaultdict
from dataclasses import dataclass, field

from aia_edge.geometry import crossing
from aia_edge.types import Track


@dataclass
class Emit:
    """An event to send. `snapshot` asks the caller to attach a frame crop/JPEG."""
    kind: str
    label: str | None = None
    track_id: int | None = None
    confidence: float | None = None
    data: dict = field(default_factory=dict)
    snapshot: bool = False


class CameraAnalytics:
    def __init__(self, analytics: dict | None, grid: tuple[int, int] = (32, 18),
                 snapshot_cooldown_s: float = 10, summary_interval_s: float = 60):
        a = analytics or {}
        self.lines = a.get("lines", [])
        self.grid = grid
        self.snapshot_cooldown_s = snapshot_cooldown_s
        self.summary_interval_s = summary_interval_s
        self._last_foot: dict[int, tuple[float, float]] = {}
        self._seen: set[tuple[str, int]] = set()
        self._last_snapshot_at = float("-inf")
        self._window_start: float | None = None
        self._max_count: dict[str, int] = defaultdict(int)
        self._cells: dict[int, int] = defaultdict(int)

    def update(self, tracks: list[Track], now: float) -> list[Emit]:
        out: list[Emit] = []
        if self._window_start is None:
            self._window_start = now

        live_ids = set()
        per_label: dict[str, int] = defaultdict(int)
        for t in tracks:
            live_ids.add(t.id)
            per_label[t.label] += 1

            key = (t.label, t.id)
            if key not in self._seen:
                self._seen.add(key)
                want_snap = now - self._last_snapshot_at >= self.snapshot_cooldown_s
                if want_snap:
                    self._last_snapshot_at = now
                out.append(Emit("detection", t.label, t.id, t.conf, snapshot=want_snap))

            foot = t.foot
            prev = self._last_foot.get(t.id)
            if prev is not None:
                for line in self.lines:
                    direction = crossing(tuple(line["p1"]), tuple(line["p2"]), prev, foot)
                    if direction is None:
                        continue
                    # "in_side" names the side people are on AFTER entering.
                    entering_dir = "right_to_left" if line.get("in_side", "left") == "left" else "left_to_right"
                    out.append(Emit("line_cross", t.label, t.id, t.conf,
                                    {"line_id": line["id"], "direction": "in" if direction == entering_dir else "out"}))
            self._last_foot[t.id] = foot

            if t.label == "person":
                gx = min(int(foot[0] * self.grid[0]), self.grid[0] - 1)
                gy = min(int(foot[1] * self.grid[1]), self.grid[1] - 1)
                self._cells[max(gy, 0) * self.grid[0] + max(gx, 0)] += 1

        for label, n in per_label.items():
            self._max_count[label] = max(self._max_count[label], n)
        # Forget tracks that disappeared so the dicts don't grow forever.
        for tid in set(self._last_foot) - live_ids:
            del self._last_foot[tid]

        if now - self._window_start >= self.summary_interval_s:
            out += self.flush()
            self._window_start = now
        return out

    def flush(self) -> list[Emit]:
        out = []
        if self._max_count:
            out.append(Emit("count", data={"max": dict(self._max_count)}))
        if self._cells:
            out.append(Emit("heatmap", data={"grid": list(self.grid), "cells": {str(k): v for k, v in self._cells.items()}}))
        self._max_count.clear()
        self._cells.clear()
        self._seen = {k for k in self._seen if k[1] in self._last_foot}
        return out
