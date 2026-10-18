from dataclasses import dataclass

# COCO class names we care about, mapped to a coarse label used by rules and the portal.
LABELS = {
    "person": "person",
    "bicycle": "vehicle", "car": "vehicle", "motorcycle": "vehicle", "bus": "vehicle", "truck": "vehicle",
}


@dataclass(frozen=True)
class Track:
    id: int
    label: str          # coarse label: "person" or "vehicle"
    conf: float
    # Normalised bounding box (x1, y1, x2, y2), each 0-1.
    box: tuple[float, float, float, float]

    @property
    def foot(self) -> tuple[float, float]:
        """Bottom-centre of the box: where the object touches the floor. Best point for lines and heatmaps."""
        return ((self.box[0] + self.box[2]) / 2, self.box[3])
