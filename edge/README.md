# Edge agent (Mac mini)

Pulls each camera's RTSP **substream**, detects and tracks people and vehicles, evaluates counting lines and a floor heatmap, and posts events to the API. Outbound HTTPS only. Events queue in a local SQLite outbox, so an API outage or restart loses nothing.

## Install (Mac mini)
```
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[yolo]"      # yolo extra pulls ultralytics + torch
```

## 1. Test each camera first
```
aia-edge probe "rtsp://user:pass@PUBLIC_IP:554/cam/realmonitor?channel=1&subtype=1" --out probe.jpg
```
Prints resolution/fps and saves a frame, or says why it failed. Always test with the **sub stream** (`subtype=1` on Dahua).

## 2. Run
Create a device in the API (superadmin: `POST /admin/edge-devices`, the token is shown once), then:
```
export AIA_EDGE_API_URL=https://analytics.example.com/api
export AIA_EDGE_TOKEN=aia_...
aia-edge run
```
Optional: `AIA_EDGE_FPS` (default 5), `AIA_EDGE_MODEL` (default `yolo11n.pt`), `AIA_EDGE_OUTBOX`.
The agent fetches cameras (and their lines/zones) from `/edge/config` every 60 s and starts or stops workers as cameras change. One Mac mini serves all tenants; each event's tenant comes from its camera.

## Events
| kind | meaning |
|---|---|
| `detection` | a new tracked person/vehicle appeared (with a snapshot, at most one per 10 s per camera) |
| `line_cross` | a tracked object crossed a counting line: `data.direction` is `in` or `out` |
| `count` | per-minute maximum simultaneous objects per label |
| `heatmap` | per-minute sparse grid of where people stood (feet position) |

Line geometry uses normalised 0-1 coordinates. `in_side` names the side of the line people are on **after** entering, seen on screen relative to the p1 -> p2 direction.

## Tests
```
pip install -e ".[dev]" && pytest
```
Covers geometry, analytics, outbox, real video decoding, the HTTP client against a mocked API and retry after an outage. The YOLO detector is not exercised by the tests (it needs torch and weights); see the benchmark step in `docs/architecture.md`.
