from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import config

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def serving_spa() -> bool:
    return config.SERVE_SPA and (FRONTEND_DIST / "index.html").is_file()


def create_app() -> FastAPI:
    from .api import (
        authors,
        backup,
        bookmarks,
        books,
        categories,
        library,
        progress,
        reader,
        roots,
        sync,
    )

    app = FastAPI(title="My Library Reader")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (
        roots,
        sync,
        library,
        books,
        reader,
        progress,
        bookmarks,
        categories,
        authors,
        backup,
    ):
        app.include_router(module.router, prefix="/api")

    # Single-server mode (`npm start` / MLR_SERVE_SPA=1): serve the built SPA
    # so the whole app runs from one process on one port. In dev (`npm run dev`)
    # this is skipped and Vite serves the SPA with hot reload.
    if serving_spa():
        app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_DIST / "assets"),
            name="assets",
        )

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            # API 404s are handled by the routers above; everything else falls
            # through to the SPA entry point for client-side routing.
            candidate = FRONTEND_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")
    else:
        # Dev mode: this port serves the API only — Vite serves the UI. Make the
        # root a friendly signpost instead of a bare 404 if someone opens it.
        @app.get("/", response_class=HTMLResponse)
        def dev_root():
            return (
                "<h2>My Library Reader — API server</h2>"
                "<p>This port serves the API only. Open the app here:</p>"
                f'<p><a href="{config.FRONTEND_URL}">{config.FRONTEND_URL}</a> '
                "(run <code>npm run dev</code> if it isn't up yet)</p>"
                "<p>Or run <code>npm start</code> for the single-port build.</p>"
            )

    return app
