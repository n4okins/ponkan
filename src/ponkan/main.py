from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings

from . import __version__
from .api import router
from .config import get_settings
from .db import SessionLocal
from .mcp_server import build_mcp_server
from .security import ApiTokenMiddleware
from .service import default_learner, seed_demo

settings = get_settings()
mcp = build_mcp_server()
mcp_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=settings.mcp_allowed_hosts,
    allowed_origins=settings.mcp_allowed_origins,
)
mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
    json_response=True,
    stateless_http=True,
    transport_security=mcp_security,
)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    with SessionLocal() as db:
        default_learner(db)
        db.commit()
        if settings.seed_demo:
            seed_demo(db)
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Ponkan API",
    version=__version__,
    description="Self-hosted study platform, SRS engine and MCP server",
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Last-Event-ID",
            "Mcp-Protocol-Version",
            "Mcp-Session-Id",
        ],
        expose_headers=["Mcp-Session-Id"],
    )

app.add_middleware(ApiTokenMiddleware, token=settings.api_token)
app.include_router(router, prefix="/api/v1")
app.mount("/mcp", mcp_app)

WEB_DIR = Path(os.environ.get("PONKAN_WEB_DIR", "/app/web-dist"))
if WEB_DIR.exists():
    assets = WEB_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (WEB_DIR / path).resolve()
        if path and candidate.is_file() and WEB_DIR.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(WEB_DIR / "index.html")
