from __future__ import annotations

import hmac

from starlette.types import ASGIApp, Receive, Scope, Send


class ApiTokenMiddleware:
    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.token or scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        protected = path.startswith("/api/v1/") or path.startswith("/mcp")
        if not protected or path == "/api/v1/health":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode("latin1")
        expected = f"Bearer {self.token}"
        if not hmac.compare_digest(auth, expected):
            body = b'{"detail":"unauthorized"}'
            response_headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ]
            await send({"type": "http.response.start", "status": 401, "headers": response_headers})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
