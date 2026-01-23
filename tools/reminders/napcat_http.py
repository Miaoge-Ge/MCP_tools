import json
import os
import urllib.parse
import urllib.error
import urllib.request

_ENV_BOOTSTRAPPED = False


def _load_dotenv_file(file_path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for raw in f.read().splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                key = k.strip()
                if not key:
                    continue
                val = v.strip()
                if len(val) >= 2 and ((val[0] == val[-1] and val[0] in ("'", '"')) or (val[0] == "`" and val[-1] == "`")):
                    val = val[1:-1].strip()
                out[key] = val
    except Exception:
        return {}
    return out


def _bootstrap_env() -> None:
    global _ENV_BOOTSTRAPPED
    if _ENV_BOOTSTRAPPED:
        return
    _ENV_BOOTSTRAPPED = True
    explicit = str(os.environ.get("MCP_TOOLS_ENV_FILE") or "").strip()
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_file = explicit or os.path.join(root, ".env")
    if not os.path.exists(env_file):
        return
    parsed = _load_dotenv_file(env_file)
    for k, v in parsed.items():
        if k not in os.environ:
            os.environ[k] = v


def _env(name: str) -> str | None:
    _bootstrap_env()
    v = os.environ.get(name)
    if not v:
        return None
    s = str(v).strip()
    return s or None


def _http_post_json(url: str, payload: dict, headers: dict[str, str], timeout_s: float = 15.0) -> tuple[int, bytes]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return int(res.status), res.read()
    except urllib.error.HTTPError as e:
        return int(e.code), e.read()


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
    token = _env("NAPCAT_HTTP_TOKEN")
    if token:
        return token
    http_url = _env("NAPCAT_HTTP_URL") or "http://127.0.0.1:3000"
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
        self._http_url = (_env("NAPCAT_HTTP_URL") or "http://127.0.0.1:3000").rstrip("/")
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
        status, body = _http_post_json(url, params, headers, timeout_s=15.0)
        if status < 200 or status >= 300:
            raise RuntimeError(f"NapCat API {action} failed: {status} {body.decode('utf-8', 'replace')}")
