import json
import sys
import threading


_write_lock = threading.Lock()


def read_message() -> dict | None:
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    line = line.rstrip(b"\r\n")
    if not line:
        return {}
    return json.loads(line.decode("utf-8"))


def write_message(payload: dict) -> None:
    out = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    with _write_lock:
        sys.stdout.buffer.write(out)
        sys.stdout.buffer.flush()


def jsonrpc_result(id_: int | str, result: dict) -> None:
    write_message({"jsonrpc": "2.0", "id": id_, "result": result})


def jsonrpc_error(id_: int | str | None, code: int, message: str, data: object | None = None) -> None:
    err: dict = {"code": int(code), "message": str(message)}
    if data is not None:
        err["data"] = data
    payload: dict = {"jsonrpc": "2.0", "error": err}
    if id_ is not None:
        payload["id"] = id_
    write_message(payload)

