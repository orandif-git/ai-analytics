import base64
import json

import cv2
import httpx
import numpy as np
import pytest

from aia_edge import stream
from aia_edge.agent import Agent, CameraWorker
from aia_edge.client import ApiClient
from aia_edge.config import Config
from aia_edge.outbox import Outbox
from aia_edge.types import Track

W, H = 320, 240


class SquareDetector:
    """Stand-in for YOLO: finds the white square in a synthetic frame and reports it as one tracked person."""

    def track(self, frame):
        mask = (frame[:, :, 0] > 200) & (frame[:, :, 1] > 200) & (frame[:, :, 2] > 200)
        ys, xs = np.nonzero(mask)
        if len(xs) < 50:
            return []
        return [Track(1, "person", 0.9, (xs.min() / W, ys.min() / H, (xs.max() + 1) / W, (ys.max() + 1) / H))]


def make_video(path, ys):
    """White 30x60 'person' at x=160 whose feet are at each y in ys (pixels), 25 fps."""
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25, (W, H))
    assert w.isOpened(), "OpenCV cannot write mp4 here"
    for y in ys:
        f = np.zeros((H, W, 3), np.uint8)
        cv2.rectangle(f, (145, y - 60), (175, y), (255, 255, 255), -1)
        w.write(f)
    w.release()


def cfg(tmp_path):
    return Config(api_url="http://api", token="t", fps=25, outbox_path=str(tmp_path / "o.db"), snapshot_cooldown_s=0, summary_interval_s=3600)


def run_worker(tmp_path, video, analytics):
    outbox = Outbox(str(tmp_path / "o.db"))
    cam = {"id": "11111111-1111-1111-1111-111111111111", "name": "t", "rtsp_url": str(video), "analytics": analytics}
    CameraWorker(cam, cfg(tmp_path), outbox, SquareDetector).process_stream(SquareDetector())
    return outbox, cam


def test_probe_style_open_failure_is_reported():
    with pytest.raises(stream.StreamError):
        next(stream.frames("/definitely/not/a/video.mp4", 5))


def test_walk_up_through_line_is_counted_in_and_events_reach_api(tmp_path):
    video = tmp_path / "walk.mp4"
    make_video(video, list(range(200, 60, -4)))  # feet move up from y=200 to y=60, crossing y=0.5*240=120
    line = {"id": "door", "p1": [0, 0.5], "p2": [1, 0.5]}  # in_side defaults to 'left' = up on screen
    outbox, cam = run_worker(tmp_path, video, {"lines": [line]})

    got = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        got.extend(body["events"])
        return httpx.Response(200, json={"accepted": len(body["events"]), "rejected": 0})

    client = ApiClient("http://api", "t", transport=httpx.MockTransport(handler))
    agent = Agent(cfg(tmp_path), client, outbox, SquareDetector)
    assert agent.flush_outbox() > 0
    assert outbox.size() == 0

    kinds = [e["kind"] for e in got]
    assert kinds.count("detection") == 1
    crosses = [e for e in got if e["kind"] == "line_cross"]
    assert [c["data"] for c in crosses] == [{"line_id": "door", "direction": "in"}]
    assert any(e["kind"] == "heatmap" for e in got) and any(e["kind"] == "count" for e in got)
    snap = base64.b64decode(next(e for e in got if e["kind"] == "detection")["snapshot_b64"])
    assert snap.startswith(b"\xff\xd8\xff") and cv2.imdecode(np.frombuffer(snap, np.uint8), 1).shape[1] == W
    assert len({e["client_id"] for e in got}) == len(got)  # unique idempotency keys


def test_walk_down_is_counted_out(tmp_path):
    video = tmp_path / "walk2.mp4"
    make_video(video, list(range(60, 200, 4)))
    outbox, _ = run_worker(tmp_path, video, {"lines": [{"id": "door", "p1": [0, 0.5], "p2": [1, 0.5]}]})
    dirs = [e["data"]["direction"] for _, e in outbox.batch(100) if e["kind"] == "line_cross"]
    assert dirs == ["out"]


def test_events_stay_in_outbox_when_api_is_down_then_retry_succeeds(tmp_path):
    video = tmp_path / "walk3.mp4"
    make_video(video, list(range(200, 60, -4)))
    outbox, _ = run_worker(tmp_path, video, {})
    n = outbox.size()
    assert n > 0
    down = ApiClient("http://api", "t", transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    agent = Agent(cfg(tmp_path), down, outbox, SquareDetector)
    with pytest.raises(httpx.HTTPStatusError):
        agent.flush_outbox()
    assert outbox.size() == n                      # nothing lost
    agent.client = ApiClient("http://api", "t", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"accepted": len(json.loads(r.content)["events"]), "rejected": 0})))
    agent.flush_outbox()
    assert outbox.size() == 0


def test_sync_cameras_starts_and_stops_workers(tmp_path):
    cams = [{"id": "a" * 8 + "-0000-0000-0000-000000000000", "tenant_id": "x", "name": "c", "rtsp_url": "/nonexistent.mp4", "analytics": {}}]
    state = {"cams": cams}
    client = ApiClient("http://api", "t", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"cameras": state["cams"]})))
    agent = Agent(cfg(tmp_path), client, Outbox(str(tmp_path / "o.db")), SquareDetector)
    agent.sync_cameras()
    assert list(agent.workers) == [cams[0]["id"]]
    w = agent.workers[cams[0]["id"]]
    state["cams"] = []
    agent.sync_cameras()
    assert agent.workers == {} and w.stop_event.is_set()
