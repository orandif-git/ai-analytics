import os
from collections.abc import Iterator

import cv2
import numpy as np

# TCP is far more reliable than UDP over the internet; the timeout (microseconds) stops dead cameras hanging us.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|timeout;10000000")


class StreamError(Exception):
    pass


def open_capture(url: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise StreamError("cannot open stream (wrong URL/credentials, camera offline, or port not reachable)")
    return cap


def frames(url: str, target_fps: float) -> Iterator[np.ndarray]:
    """Yield BGR frames at roughly target_fps. Every frame is grabbed (so a live buffer never backs up),
    but only every Nth is decoded. Ends when a file finishes; raises StreamError when a live stream drops."""
    cap = open_capture(url)
    try:
        src_fps = cap.get(cv2.CAP_PROP_FPS)
        step = max(1, round((src_fps if src_fps and src_fps < 120 else 25) / target_fps))
        i = 0
        while True:
            if not cap.grab():
                if url.startswith("rtsp") or url.startswith("rtmp"):
                    raise StreamError("stream ended or dropped")
                return
            if i % step == 0:
                ok, frame = cap.retrieve()
                if ok:
                    yield frame
            i += 1
    finally:
        cap.release()


def grab_frame(url: str) -> np.ndarray:
    """Open the stream, read one frame, close. Used for portal preview requests."""
    cap = open_capture(url)
    try:
        for _ in range(5):  # first frames of some cameras are grey/partial
            ok, frame = cap.read()
        if not ok or frame is None:
            raise StreamError("stream opened but no frame arrived")
        return frame
    finally:
        cap.release()
