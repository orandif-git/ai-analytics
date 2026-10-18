"""RTSP URL templates per camera vendor, so customers don't hand-type URLs."""
from urllib.parse import quote


def build_rtsp_url(
    vendor: str,
    host: str,
    port: int = 554,
    channel: int = 1,
    stream: str = "sub",
    path: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> str:
    sub = 1 if stream == "sub" else 0
    if vendor == "dahua":
        route = f"/cam/realmonitor?channel={channel}&subtype={sub}"
    elif vendor == "hikvision":
        # Hikvision stream ids: <channel>01 = main, <channel>02 = sub
        route = f"/Streaming/Channels/{channel}0{2 if sub else 1}"
    elif vendor == "axis":
        route = "/axis-media/media.amp"
    elif vendor == "uniview":
        route = f"/media/video{2 if sub else 1}"
    else:
        route = path if path and path.startswith("/") else f"/{path or ''}"
    auth = ""
    if username:
        auth = quote(username, safe="")
        if password:
            auth += ":" + quote(password, safe="")
        auth += "@"
    return f"rtsp://{auth}{host}:{port}{route}"
