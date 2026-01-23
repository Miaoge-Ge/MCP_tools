import json
import os
import urllib.parse

from mcp_tools_core.env import env
from mcp_tools_core.http import http_post_json


def _parse_port_from_url(url: str) -> int | None:
    try:
        u = urllib.parse.urlparse(url)
        if u.port:
            return int(u.port)
        if u.scheme in ("http", "ws"):
            return 80
        if u.scheme in ("https", "wss"):
            return 443
        return None
    except Exception:
        return None


def _maybe_load_napcat_http_token() -> str | None:
    token = env("NAPCAT_HTTP_TOKEN")
    if token:
        return token
    http_url = env("NAPCAT_HTTP_URL") or "http://127.0.0.1:3000"
    http_port = _parse_port_from_url(http_url)
    candidates = ["/opt/napcat-home/Napcat/opt/QQ/resources/app/app_launcher/napcat/config/onebot11.json"]
    for p in candidates:
        try:
            if not os.path.exists(p):
                continue
            raw = open(p, "r", encoding="utf-8").read()
            parsed = json.loads(raw)
            servers = (((parsed or {}).get("network") or {}).get("httpServers") or []) if isinstance(parsed, dict) else []
            enabled = [s for s in servers if isinstance(s, dict) and s.get("enable", True) is not False]
            matched = None
            if http_port:
                for s in enabled:
                    if int(s.get("port") or 0) == http_port:
                        matched = s
                        break
            src = matched or (enabled[0] if enabled else None)
            t = str((src or {}).get("token") or "").strip()
            if t:
                return t
        except Exception:
            continue
    return None


class NapCatHttpSender:
    def __init__(self) -> None:
        self._http_url = (env("NAPCAT_HTTP_URL") or "http://127.0.0.1:3000").rstrip("/")
        self._http_token = _maybe_load_napcat_http_token()

    def send(self, target: dict, text: str) -> None:
        if str(target.get("chatType") or "") == "private":
            self._call_api("send_private_msg", {"user_id": str(target.get("userId") or ""), "message": text})
            return
        self._call_api("send_group_msg", {"group_id": str(target.get("groupId") or ""), "message": text})

    def _call_api(self, action: str, params: dict) -> None:
        url = f"{self._http_url}/{action}"
        headers = {"Content-Type": "application/json"}
        if self._http_token:
            headers["Authorization"] = f"Bearer {self._http_token}"
        status, body = http_post_json(url, params, headers, timeout_s=15.0)
        if status < 200 or status >= 300:
            raise RuntimeError(f"NapCat API {action} failed: {status} {body.decode('utf-8', 'replace')}")
