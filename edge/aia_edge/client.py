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
