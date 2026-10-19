import httpx

from aia_edge import __version__


class ApiClient:
    def __init__(self, base_url: str, token: str, transport: httpx.BaseTransport | None = None):
        self._c = httpx.Client(
            base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=20, transport=transport
        )

    def config(self) -> list[dict]:
        r = self._c.get("/edge/config")
        r.raise_for_status()
        return r.json()["cameras"]

    def heartbeat(self, cameras: list[dict]) -> None:
        self._c.post("/edge/heartbeat", json={"agent_version": __version__, "cameras": cameras}).raise_for_status()

    def send_events(self, events: list[dict]) -> dict:
        r = self._c.post("/edge/events", json={"events": events})
        r.raise_for_status()
        return r.json()

    def pending_requests(self) -> list[dict]:
        r = self._c.get("/edge/requests")
        r.raise_for_status()
        return r.json()["requests"]

    def answer_request(self, request_id: str, snapshot_b64: str | None = None, error: str | None = None) -> None:
        body = {"snapshot_b64": snapshot_b64} if snapshot_b64 else {"error": error or "unknown error"}
        self._c.post(f"/edge/requests/{request_id}", json=body).raise_for_status()
