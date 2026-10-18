import argparse
import logging
import sys

import cv2

from aia_edge import stream
from aia_edge.agent import Agent
from aia_edge.client import ApiClient
from aia_edge.config import Config
from aia_edge.outbox import Outbox


def probe(url: str, out: str) -> int:
    """Connectivity check: open the stream, read one frame, save it. Run this on the Mac mini for each camera."""
    try:
        cap = stream.open_capture(url)
    except stream.StreamError as ex:
        print(f"FAIL: {ex}")
        return 1
    try:
        ok, frame = cap.read()
        if not ok:
            print("FAIL: stream opened but no frame arrived within the timeout")
            return 1
        h, w = frame.shape[:2]
        cv2.imwrite(out, frame)
        print(f"OK: {w}x{h} @ {cap.get(cv2.CAP_PROP_FPS):.1f} fps, snapshot saved to {out}")
        return 0
    finally:
        cap.release()


def run() -> int:
    from aia_edge.detector import YoloDetector

    cfg = Config()
    if not cfg.api_url or not cfg.token:
        print("Set AIA_EDGE_API_URL and AIA_EDGE_TOKEN")
        return 2
    agent = Agent(cfg, ApiClient(cfg.api_url, cfg.token), Outbox(cfg.outbox_path), lambda: YoloDetector(cfg.model))
    agent.run_forever()
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="aia-edge")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="run the agent")
    pr = sub.add_parser("probe", help="test one RTSP URL and save a snapshot")
    pr.add_argument("url")
    pr.add_argument("--out", default="probe.jpg")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(probe(args.url, args.out) if args.cmd == "probe" else run())
