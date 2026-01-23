import json
import urllib.request
import urllib.error


def http_post_json(url: str, payload: dict, headers: dict[str, str], timeout_s: float = 15.0) -> tuple[int, bytes]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return int(res.status), res.read()
    except urllib.error.HTTPError as e:
        return int(e.code), e.read()


def http_get(url: str, headers: dict[str, str] | None = None, timeout_s: float = 15.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return int(res.status), res.read()
    except urllib.error.HTTPError as e:
        return int(e.code), e.read()

