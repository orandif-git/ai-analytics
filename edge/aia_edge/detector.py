from typing import Protocol

import numpy as np

from aia_edge.types import LABELS, Track

# COCO ids: person, bicycle, car, motorcycle, bus, truck
COCO_CLASSES = [0, 1, 2, 3, 5, 7]


class Detector(Protocol):
    def track(self, frame: np.ndarray) -> list[Track]: ...


class YoloDetector:
    """Ultralytics YOLO with its built-in ByteTrack. One instance PER CAMERA: tracker state lives in the model object."""

    def __init__(self, weights: str = "yolo11n.pt", conf: float = 0.35, imgsz: int = 640, device: str | None = None):
        from ultralytics import YOLO  # imported lazily: heavy, and not needed for tests

        self.model = YOLO(weights)
        self.conf, self.imgsz = conf, imgsz
        self.device = device or self._default_device()

    @staticmethod
    def _default_device() -> str:
        import torch

        if torch.backends.mps.is_available():  # Apple silicon GPU
            return "mps"
        return "cuda" if torch.cuda.is_available() else "cpu"

    def track(self, frame: np.ndarray) -> list[Track]:
        h, w = frame.shape[:2]
        res = self.model.track(
            frame, persist=True, tracker="bytetrack.yaml", classes=COCO_CLASSES,
            conf=self.conf, imgsz=self.imgsz, device=self.device, verbose=False,
        )[0]
        if res.boxes is None or res.boxes.id is None:
            return []
        out = []
        for box, tid, cls, conf in zip(res.boxes.xyxy.tolist(), res.boxes.id.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
            label = LABELS.get(res.names[int(cls)])
            if label:
                x1, y1, x2, y2 = box
                out.append(Track(int(tid), label, float(conf), (x1 / w, y1 / h, x2 / w, y2 / h)))
        return out
