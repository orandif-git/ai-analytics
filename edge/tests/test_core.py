from aia_edge.analytics import CameraAnalytics
from aia_edge.geometry import crossing, point_in_polygon
from aia_edge.outbox import Outbox
from aia_edge.types import Track


def person(tid, x, y, w=0.05, h=0.2, conf=0.9):
    """Box whose bottom-centre ('foot') is at (x, y)."""
    return Track(tid, "person", conf, (x - w / 2, y - h, x + w / 2, y))


HLINE = {"id": "door", "p1": [0.0, 0.5], "p2": [1.0, 0.5]}  # left-to-right line, y=0.5


def test_crossing_direction_and_segment_extent():
    # p1->p2 points right, so on screen its LEFT side is UP (smaller y) and its RIGHT side is DOWN.
    assert crossing((0, .5), (1, .5), (.5, .6), (.5, .4)) == "right_to_left"  # moving up: down(right) -> up(left)
    assert crossing((0, .5), (1, .5), (.5, .4), (.5, .6)) == "left_to_right"  # moving down
    assert crossing((0, .5), (1, .5), (.5, .4), (.5, .45)) is None            # same side
    assert crossing((0.4, .5), (0.6, .5), (.9, .6), (.9, .4)) is None          # crosses the extension, not the segment


def test_point_in_polygon():
    sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert point_in_polygon((.5, .5), sq) and not point_in_polygon((1.5, .5), sq)


def test_detection_once_per_track_with_snapshot_cooldown():
    a = CameraAnalytics({}, snapshot_cooldown_s=10)
    e1 = a.update([person(1, .5, .8)], now=0)
    assert [(e.kind, e.snapshot) for e in e1] == [("detection", True)]
    assert a.update([person(1, .5, .8)], now=1) == []                 # same track: no new detection
    e2 = a.update([person(1, .5, .8), person(2, .2, .8)], now=2)
    assert [(e.kind, e.track_id, e.snapshot) for e in e2] == [("detection", 2, False)]  # inside cooldown: no snapshot
    e3 = a.update([person(3, .7, .8)], now=20)
    assert e3[0].snapshot is True


def test_line_cross_in_and_out_and_in_side():
    # in_side default 'left' of p1->p2 = up (smaller y). Moving up = entering.
    a = CameraAnalytics({"lines": [HLINE]})
    a.update([person(1, .5, .6)], now=0)
    up = a.update([person(1, .5, .4)], now=1)
    assert [(e.kind, e.data["direction"]) for e in up if e.kind == "line_cross"] == [("line_cross", "in")]
    down = a.update([person(1, .5, .6)], now=2)
    assert [e.data["direction"] for e in down if e.kind == "line_cross"] == ["out"]

    b = CameraAnalytics({"lines": [{**HLINE, "in_side": "right"}]})
    b.update([person(1, .5, .6)], now=0)
    moved_up = b.update([person(1, .5, .4)], now=1)
    assert [e.data["direction"] for e in moved_up if e.kind == "line_cross"] == ["out"]


def test_no_crossing_event_for_first_sighting_or_after_track_lost():
    a = CameraAnalytics({"lines": [HLINE]})
    assert not [e for e in a.update([person(1, .5, .4)], now=0) if e.kind == "line_cross"]
    a.update([], now=1)                                              # track 1 lost: its history is forgotten
    assert not [e for e in a.update([person(1, .5, .6)], now=2) if e.kind == "line_cross"]


def test_summary_emits_max_counts_and_sparse_heatmap_then_resets():
    a = CameraAnalytics({}, grid=(4, 4), summary_interval_s=60)
    a.update([person(1, .1, .9), person(2, .1, .9)], now=0)          # both land in cell (0,3) -> index 12
    a.update([person(1, .1, .9)], now=1)
    out = a.update([person(1, .1, .9)], now=61)
    kinds = {e.kind: e for e in out}
    assert kinds["count"].data == {"max": {"person": 2}}
    assert kinds["heatmap"].data == {"grid": [4, 4], "cells": {"12": 4}}
    assert a.flush() == []                                            # window reset


def test_outbox_survives_reopen_and_is_bounded(tmp_path):
    path = str(tmp_path / "o.sqlite3")
    o = Outbox(path, max_rows=3)
    for i in range(5):
        o.put({"n": i})
    assert o.size() == 3
    o2 = Outbox(path, max_rows=3)                                     # "restart"
    rows = o2.batch(10)
    assert [e["n"] for _, e in rows] == [2, 3, 4]                     # oldest dropped
    o2.delete([i for i, _ in rows])
    assert o2.size() == 0
