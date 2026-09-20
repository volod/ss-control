"""Stand-in for ss-video UI, Frigate, ChirpStack, and fusion-rt during local bring-up."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os

BIND = os.environ.get("STUB_BIND", "0.0.0.0")
PORT = int(os.environ.get("STUB_PORT", "8080"))


def _header(handler: BaseHTTPRequestHandler, name: str) -> str:
    return handler.headers.get(name, "") or handler.headers.get(name.lower(), "")


def _authed(handler: BaseHTTPRequestHandler) -> bool:
    user = (
        _header(handler, "Remote-User")
        or _header(handler, "X-Auth-Request-User")
        or _header(handler, "X-Forwarded-User")
    )
    auth = _header(handler, "Authorization")
    return bool(user) or auth.lower().startswith("bearer ")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        sys_stdout = __import__("sys").stdout
        sys_stdout.write("stub " + (fmt % args) + "\n")
        sys_stdout.flush()

    def _send(self, code: int, body: bytes, content_type: str = "text/plain") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in {"/healthz", "/health"}:
            self._send(200, b"ok")
            return
        host = _header(self, "Host").split(":", 1)[0]
        if not _authed(self):
            self._send(401, b"unauthorized")
            return
        html = (
            f"<html><body>ok host={host} user={_header(self, 'Remote-User')}</body></html>"
        )
        self._send(200, html.encode("utf-8"), "text/html")

    def do_POST(self) -> None:  # noqa: N802
        self.do_GET()


def main() -> None:
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"stub listening on {BIND}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
