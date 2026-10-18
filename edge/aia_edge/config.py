import os
from dataclasses import dataclass, field


@dataclass
class Config:
    api_url: str = field(default_factory=lambda: os.environ.get("AIA_EDGE_API_URL", "").rstrip("/"))
    token: str = field(default_factory=lambda: os.environ.get("AIA_EDGE_TOKEN", ""))
    fps: float = field(default_factory=lambda: float(os.environ.get("AIA_EDGE_FPS", "5")))
    model: str = field(default_factory=lambda: os.environ.get("AIA_EDGE_MODEL", "yolo11n.pt"))
    outbox_path: str = field(default_factory=lambda: os.environ.get("AIA_EDGE_OUTBOX", "outbox.sqlite3"))
    config_refresh_s: float = 60
    heartbeat_s: float = 30
    flush_s: float = 5
    # Minimum seconds between two snapshot-carrying detection events for the same camera.
    snapshot_cooldown_s: float = 10
    heatmap_grid: tuple[int, int] = (32, 18)
    summary_interval_s: float = 60
