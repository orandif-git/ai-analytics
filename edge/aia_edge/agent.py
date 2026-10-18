import base64
import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

import cv2
import httpx

from aia_edge import stream
from aia_edge.analytics import CameraAnalytics, Emit
from aia_edge.client import ApiClient
from aia_edge.config import Config
from aia_edge.detector import Detector
from aia_edge.outbox import Outbox

log = logging.getLogger("aia.edge")


def jpeg_b64(frame, max_width: int = 960, quality: int = 70) -> str:
    h, w = frame.shape[:2]
    if w > max_width:
        frame = cv2.resize(frame, (max_width, int(h * max_width / w)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return base64.b64encode(buf.tobytes()).decode()


def build_event(camera_id: str, e: Emit, frame=None) -> dict:
    ev = {
        "client_id": str(uuid.uuid4()),
        "camera_id": camera_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": e.kind, "label": e.label, "track_id": e.track_id,
        "confidence": None if e.confidence is None else min(max(e.confidence, 0.0), 1.0),
        "data": e.data,
    }
    if e.snapshot and frame is not None:
        ev["snapshot_b64"] = jpeg_b64(frame)
    return ev


class CameraWorker(threading.Thread):
    def __init__(self, cam: dict, cfg: Config, outbox: Outbox, detector_factory: Callable[[], Detector]):
        super().__init__(daemon=True, name=f"cam-{cam['id'][:8]}")
        self.cam, self.cfg, self.outbox = cam, cfg, outbox
        self.detector_factory = detector_factory
        self.stop_event = threading.Event()
        self.status, self.fps = "offline", 0.0

    def process_stream(self, detector: Detector) -> None:
        """Run one connection to completion (end of file, or StreamError when a live stream drops)."""
        analytics = CameraAnalytics(
            self.cam.get("analytics"), self.cfg.heatmap_grid, self.cfg.snapshot_cooldown_s, self.cfg.summary_interval_s
        )
        n, t0, last = 0, time.monotonic(), None
        for frame in stream.frames(self.cam["rtsp_url"], self.cfg.fps):
            if self.stop_event.is_set():
                break
            last = frame
            self.status = "online"
            for e in analytics.update(detector.track(frame), time.monotonic()):
                self.outbox.put(build_event(self.cam["id"], e, frame))
            n += 1
            self.fps = n / max(time.monotonic() - t0, 1e-6)
        for e in analytics.flush():
            self.outbox.put(build_event(self.cam["id"], e, last))

    def run(self) -> None:
        backoff = 2.0
        detector = self.detector_factory()
        while not self.stop_event.is_set():
            try:
                self.process_stream(detector)
                backoff = 2.0
            except Exception as ex:  # keep the worker alive whatever the camera does
                self.status = "offline" if isinstance(ex, stream.StreamError) else "error"
                log.warning("camera %s: %s (retry in %.0fs)", self.cam["name"], ex, backoff)
            self.stop_event.wait(backoff)
            backoff = min(backoff * 2, 60)


class Agent:
    def __init__(self, cfg: Config, client: ApiClient, outbox: Outbox, detector_factory: Callable[[], Detector]):
        self.cfg, self.client, self.outbox, self.detector_factory = cfg, client, outbox, detector_factory
        self.workers: dict[str, CameraWorker] = {}
        self._stop = threading.Event()

    def sync_cameras(self) -> None:
        cams = {c["id"]: c for c in self.client.config()}
        for cid in list(self.workers):
            w = self.workers[cid]
            if cid not in cams or (w.cam["rtsp_url"], w.cam["analytics"]) != (cams[cid]["rtsp_url"], cams[cid]["analytics"]):
                w.stop_event.set()
                del self.workers[cid]
        for cid, cam in cams.items():
            if cid not in self.workers:
                w = CameraWorker(cam, self.cfg, self.outbox, self.detector_factory)
                self.workers[cid] = w
                w.start()

    def send_heartbeat(self) -> None:
        self.client.heartbeat([{"camera_id": cid, "status": w.status, "fps": round(w.fps, 2)} for cid, w in self.workers.items()])

    def flush_outbox(self) -> int:
        sent = 0
        while True:
            rows = self.outbox.batch(100)
            if not rows:
                return sent
            res = self.client.send_events([e for _, e in rows])
            # Even rejected events (deleted camera, bad snapshot) are dropped, or they would block the queue forever.
            self.outbox.delete([i for i, _ in rows])
            sent += res.get("accepted", 0)

    def _loop(self, fn: Callable[[], object], every: float, name: str) -> None:
        while not self._stop.is_set():
            try:
                fn()
            except httpx.HTTPError as ex:
                log.warning("%s failed: %s", name, ex)
            except Exception:
                log.exception("%s crashed", name)
            self._stop.wait(every)

    def run_forever(self) -> None:
        threads = [
            threading.Thread(target=self._loop, args=(self.sync_cameras, self.cfg.config_refresh_s, "config"), daemon=True),
            threading.Thread(target=self._loop, args=(self.send_heartbeat, self.cfg.heartbeat_s, "heartbeat"), daemon=True),
            threading.Thread(target=self._loop, args=(self.flush_outbox, self.cfg.flush_s, "flush"), daemon=True),
        ]
        for t in threads:
            t.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self._stop.set()
            for w in self.workers.values():
                w.stop_event.set()
