"""
app/main.py
FastAPI application layer for Agyx Live Dispatch OS (Pymes-Fletes Grupo 2).
Provides:
- FastAPI instance with OpenAPI documentation, CORS middleware, and lifespan event.
- Static files mounting (/static) and templates mounting (/templates: index.html, solicitar.html).
- Modular REST API routers: /api/dispatch, /api/live, /api/r4r, /api/memory, /api/fleet, /api/demo.
- Dual execution resilience: native uvicorn execution and Python stdlib HTTP fallback.
"""
import os
import sys
import json
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from app.config import (
    APP_DIR, BASE_DIR, DATA_DIR, SQLITE_DB_PATH, APP_ENV, CORS_ORIGINS,
    MAX_REQUEST_BODY_BYTES, demo_admin_actions_enabled,
)
from app.services.db_service import init_db
from app.api.dependencies import ServiceContainer, get_services

# Route controller imports (framework-agnostic)
from app.api.routes_dispatch import (
    evaluate_dispatch_controller,
    submit_live_order_controller,
    get_live_sync_controller,
)
from app.api.routes_r4r import (
    get_queue_controller,
    get_proposal_controller,
    review_proposal_controller,
    simulate_inactivity_controller,
)
from app.api.routes_memory import (
    get_memory_controller,
    reset_memory_controller,
    seed_memory_controller,
)
from app.api.routes_fleet import (
    get_fleet_controller,
    get_bases_controller,
    update_truck_status_controller,
    get_truck_controller,
    get_restrictions_controller,
    get_zone_restriction_controller,
    get_tactical_network_controller,
)
from app.api.routes_demo import (
    get_demo_cases_controller,
    run_case_controller,
    run_all_cases_controller,
    set_operating_mode_controller,
    trigger_demo_client_order_controller,
)

STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

# ---------------------------------------------------------------------------
# 1. FastAPI Application Setup (when FastAPI is installed)
# ---------------------------------------------------------------------------
try:
    from fastapi import FastAPI, Request, HTTPException, Depends
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, JSONResponse
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        """Startup and shutdown lifecycle manager."""
        init_db(SQLITE_DB_PATH)
        ServiceContainer.get_instance()
        yield

    app = FastAPI(
        title="Agyx Live Dispatch OS — Operational AI Agent (Pymes-Fletes Grupo 2)",
        description=(
            "Operational AI Agent for SME logistics in Santiago de Chile. "
            "Includes Live Client Order Portal (/solicitar), real-time 3s sync, "
            "Google Maps tactical dispatch radar, physical depot bases, strict R4R governance "
            "(auto_approved=False), and Living Memory rule distillation."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )

    allowed_origins = list(CORS_ORIGINS) or ([] if APP_ENV == "production" else ["*"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Agyx-Demo-Token", "X-Request-ID"],
    )

    @app.middleware("http")
    async def enforce_request_size_limit(request: Request, call_next):
        """Reject oversized request bodies before route parsing."""
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                if int(raw_length) > MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"error": "PAYLOAD_TOO_LARGE", "max_bytes": MAX_REQUEST_BODY_BYTES},
                    )
            except ValueError:
                return JSONResponse(status_code=400, content={"error": "INVALID_CONTENT_LENGTH"})
        return await call_next(request)

    # Mount static files and entregables
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    ENTREGABLES_DIR = BASE_DIR / "entregables"
    if ENTREGABLES_DIR.exists():
        app.mount("/entregables", StaticFiles(directory=str(ENTREGABLES_DIR), html=True), name="entregables")

    # Include modular API routers
    from app.api.routes_dispatch import router as dispatch_router
    from app.api.routes_r4r import router as r4r_router
    from app.api.routes_memory import router as memory_router
    from app.api.routes_fleet import router as fleet_router
    from app.api.routes_demo import router as demo_router

    app.include_router(dispatch_router)
    app.include_router(r4r_router)
    app.include_router(memory_router)
    app.include_router(fleet_router)
    app.include_router(demo_router)

    # Direct Live API aliases (/api/live/orders and /api/live/sync)
    @app.post("/api/live/orders")
    async def live_orders_alias(request: Request, services: ServiceContainer = Depends(get_services)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Malformed JSON body")
        status_code, data = submit_live_order_controller(body, services=services)
        if status_code >= 400:
            raise HTTPException(status_code=status_code, detail=data.get("detail", data.get("error", "Error")))
        return JSONResponse(status_code=status_code, content=data)

    @app.get("/api/live/sync")
    async def live_sync_alias(services: ServiceContainer = Depends(get_services)):
        status_code, data = get_live_sync_controller(services=services)
        return JSONResponse(status_code=status_code, content=data)

    # Supervisor Control Center (/)
    @app.get("/", response_class=HTMLResponse)
    @app.get("/index.html", response_class=HTMLResponse)
    async def serve_index(request: Request):
        index_file = TEMPLATES_DIR / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"), status_code=200)
        return HTMLResponse(
            content="<h1>Agyx Operational AI Agent</h1><p>Web UI index.html not yet generated in templates/.</p>",
            status_code=200,
        )

    # External Client Live Order Portal (/solicitar, /cliente, /pedido)
    @app.get("/solicitar", response_class=HTMLResponse)
    @app.get("/solicitar/", response_class=HTMLResponse)
    @app.get("/cliente", response_class=HTMLResponse)
    @app.get("/pedido", response_class=HTMLResponse)
    async def serve_solicitar(request: Request):
        solicitar_file = TEMPLATES_DIR / "solicitar.html"
        if solicitar_file.exists():
            return HTMLResponse(content=solicitar_file.read_text(encoding="utf-8"), status_code=200)
        return HTMLResponse(
            content="<h1>Agyx Portal de Clientes</h1><p>Template solicitar.html not found.</p>",
            status_code=200,
        )

    @app.get("/health")
    @app.get("/api/health")
    def health_check():
        return {
            "status": "OK",
            "app": "Agyx Operational AI Agent",
            "version": "2.0.0",
            "server": "FastAPI",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "engine_default": "local_zero_token",
            "environment": APP_ENV,
            "demo_admin_actions_enabled": demo_admin_actions_enabled(),
            "data_mode": "live_interactive_dispatch",
        }

    # Ensure DB is initialized on serverless cold start even if lifespan is not invoked
    init_db(SQLITE_DB_PATH)
    ServiceContainer.get_instance()
    HAS_FASTAPI = True

except ImportError:
    HAS_FASTAPI = False

    class FallbackApp:
        """Lightweight proxy object so `from app.main import app` works without FastAPI."""
        title = "Agyx Operational AI Agent (Fallback Mode)"
        version = "2.0.0"

        def __call__(self, scope, receive, send):
            pass

    app = FallbackApp()  # type: ignore


# ---------------------------------------------------------------------------
# 2. Standalone Python stdlib HTTP Server Fallback (Zero-Dependency Resilience)
# ---------------------------------------------------------------------------
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.parse


class AgyxFallbackHTTPHandler(BaseHTTPRequestHandler):
    """
    Python standard library HTTP request handler providing complete fallback routing
    when running in offline sandboxes without uvicorn or fastapi installed.
    """

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, X-Agyx-Demo-Token")

    def _send_json(self, status_code: int, data: Any):
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Health endpoints
        if path in ("/health", "/api/health"):
            self._send_json(200, {
                "status": "OK",
                "app": "Agyx Operational AI Agent",
                "version": "2.0.0",
                "server": "Python stdlib HTTP Fallback",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            })
            return

        # Supervisor Control Center (/)
        if path in ("/", "/index.html"):
            index_path = TEMPLATES_DIR / "index.html"
            if index_path.exists():
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(content)
            else:
                fallback_html = b"<html><body><h1>Agyx Operational AI Agent</h1><p>Running in stdlib mode.</p></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(fallback_html)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(fallback_html)
            return

        # External Client Live Order Portal (/solicitar, /cliente, /pedido)
        if path in ("/solicitar", "/solicitar/", "/cliente", "/pedido"):
            sol_path = TEMPLATES_DIR / "solicitar.html"
            if sol_path.exists():
                with open(sol_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(content)
            else:
                self._send_json(404, {"error": "PORTAL_TEMPLATE_NOT_FOUND"})
            return

        # Static files (/static/...)
        if path.startswith("/static/"):
            clean_rel = urllib.parse.unquote(path[len("/static/"):].lstrip("/"))
            file_path = (STATIC_DIR / clean_rel).resolve()
            static_root = STATIC_DIR.resolve()

            try:
                is_safe = file_path.is_relative_to(static_root)
            except AttributeError:
                is_safe = str(file_path).startswith(str(static_root))

            if not is_safe or not file_path.is_file():
                self._send_json(404, {"error": "STATIC_FILE_NOT_FOUND", "path": path})
                return

            mime, _ = mimetypes.guess_type(str(file_path))
            mime = mime or "application/octet-stream"
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
            return

        # Entregables files (/entregables/...)
        if path.startswith("/entregables/"):
            entregables_root = (BASE_DIR / "entregables").resolve()
            clean_rel = urllib.parse.unquote(path[len("/entregables/"):].lstrip("/"))
            file_path = (entregables_root / clean_rel).resolve()
            try:
                is_safe = file_path.is_relative_to(entregables_root)
            except AttributeError:
                is_safe = str(file_path).startswith(str(entregables_root))

            if not is_safe or not file_path.is_file():
                self._send_json(404, {"error": "DELIVERABLE_NOT_FOUND", "path": path})
                return

            mime, _ = mimetypes.guess_type(str(file_path))
            mime = (mime or "text/plain") + "; charset=utf-8"
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
            return

        # API Routes: Live Sync
        if path in ("/api/live/sync", "/api/dispatch/live-sync"):
            code, res = get_live_sync_controller()
            self._send_json(code, res)
            return

        # API Routes: R4R
        if path == "/api/r4r/queue":
            code, res = get_queue_controller()
            self._send_json(code, res)
            return
        if path.startswith("/api/r4r/"):
            case_id = path[len("/api/r4r/"):].strip()
            code, res = get_proposal_controller(case_id)
            self._send_json(code, res)
            return

        # API Routes: Memory
        if path in ("/api/memory", "/api/memory/"):
            zone = query.get("zone", [None])[0]
            code, res = get_memory_controller(zone=zone)
            self._send_json(code, res)
            return

        # API Routes: Fleet, Bases, Tactical Network & Restrictions
        if path in ("/api/tactical-network", "/api/tactical-network/"):
            hora = query.get("hora", ["14:00"])[0]
            code, res = get_tactical_network_controller(hora=hora)
            self._send_json(code, res)
            return
        if path == "/api/bases":
            code, res = get_bases_controller()
            self._send_json(code, res)
            return
        if path == "/api/fleet":
            code, res = get_fleet_controller()
            self._send_json(code, res)
            return
        if path.startswith("/api/fleet/"):
            truck_id = path[len("/api/fleet/"):].strip()
            code, res = get_truck_controller(truck_id)
            self._send_json(code, res)
            return
        if path == "/api/restrictions":
            code, res = get_restrictions_controller()
            self._send_json(code, res)
            return
        if path.startswith("/api/restrictions/"):
            zone = path[len("/api/restrictions/"):].strip()
            code, res = get_zone_restriction_controller(zone)
            self._send_json(code, res)
            return

        # API Routes: Demo
        if path == "/api/demo/cases":
            code, res = get_demo_cases_controller()
            self._send_json(code, res)
            return

        self._send_json(404, {"error": "ENDPOINT_NOT_FOUND", "path": path})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_json(400, {"error": "INVALID_CONTENT_LENGTH"})
            return
        if content_length < 0 or content_length > MAX_REQUEST_BODY_BYTES:
            self._send_json(413, {"error": "PAYLOAD_TOO_LARGE", "max_bytes": MAX_REQUEST_BODY_BYTES})
            return
        body = {}
        if content_length > 0:
            raw_body = self.rfile.read(content_length).decode("utf-8")
            try:
                body = json.loads(raw_body)
            except Exception:
                self._send_json(400, {"error": "MALFORMED_JSON", "detail": "Invalid JSON body payload"})
                return

        # API Route: Live Order Submission (/api/live/orders or /api/dispatch/live-order)
        if path in ("/api/live/orders", "/api/live/orders/", "/api/dispatch/live-order", "/api/dispatch/live-order/"):
            code, res = submit_live_order_controller(body)
            self._send_json(code, res)
            return

        # API Route: Dispatch Evaluate
        if path in ("/api/dispatch/evaluate", "/api/dispatch/evaluate/"):
            code, res = evaluate_dispatch_controller(body)
            self._send_json(code, res)
            return

        # API Route: Live Fleet Truck Status Update
        if path.startswith("/api/fleet/") and path.endswith("/status"):
            mid = path[len("/api/fleet/"):-len("/status")].strip("/")
            code, res = update_truck_status_controller(mid, body)
            self._send_json(code, res)
            return

        # API Route: R4R Review
        if path in ("/api/r4r/review", "/api/r4r/review/"):
            code, res = review_proposal_controller(body)
            self._send_json(code, res)
            return

        # API Route: R4R Simulate Inactivity
        if path in ("/api/r4r/simulate-inactivity", "/api/r4r/simulate-inactivity/"):
            code, res = simulate_inactivity_controller(body)
            self._send_json(code, res)
            return

        # API Route: Memory Reset & Seed
        if path in ("/api/memory/reset", "/api/memory/reset/"):
            code, res = reset_memory_controller(
                admin_token=self.headers.get("X-Agyx-Demo-Token")
            )
            self._send_json(code, res)
            return
        if path in ("/api/memory/seed", "/api/memory/seed/"):
            code, res = seed_memory_controller(
                body, admin_token=self.headers.get("X-Agyx-Demo-Token")
            )
            self._send_json(code, res)
            return

        # API Route: Demo Run Case & Run All & Operating Mode
        if path.startswith("/api/demo/mode/"):
            mode_name = path[len("/api/demo/mode/"):].strip("/")
            code, res = set_operating_mode_controller(mode_name)
            self._send_json(code, res)
            return
        if path in ("/api/demo/trigger-client-order", "/api/demo/trigger-client-order/"):
            code, res = trigger_demo_client_order_controller(payload=body)
            self._send_json(code, res)
            return
        if path.startswith("/api/demo/run-case/"):
            case_id = path[len("/api/demo/run-case/"):].strip()
            code, res = run_case_controller(case_id, payload=body)
            self._send_json(code, res)
            return
        if path in ("/api/demo/run-all", "/api/demo/run-all/"):
            code, res = run_all_cases_controller(
                payload=body, admin_token=self.headers.get("X-Agyx-Demo-Token")
            )
            self._send_json(code, res)
            return

        self._send_json(404, {"error": "ENDPOINT_NOT_FOUND", "path": path})

    def log_message(self, format, *args):
        sys.stderr.write(f"[AGYX HTTP] {self.address_string()} - {format % args}\n")


def run_stdlib_server(host: str = "0.0.0.0", port: int = 8000):
    """Starts the Python standard library HTTP fallback server."""
    init_db(SQLITE_DB_PATH)
    ServiceContainer.get_instance()
    server_address = (host, port)
    httpd = HTTPServer(server_address, AgyxFallbackHTTPHandler)
    print(f"[AGYX SERVER] Starting Python stdlib HTTP fallback server at http://{host}:{port}")
    print(f"[AGYX SERVER] Press Ctrl+C to terminate.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[AGYX SERVER] Shutting down server gracefully...")
        httpd.server_close()


def main():
    """Dual-resilience entry point."""
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    try:
        import uvicorn
        print(f"[AGYX SERVER] Starting with Uvicorn ASGI server on http://{host}:{port}...")
        uvicorn.run("app.main:app", host=host, port=port, reload=True)
    except ImportError:
        print(f"[AGYX NOTICE] Uvicorn is not installed in current Python environment.")
        print(f"[AGYX NOTICE] Activating lightweight Python stdlib HTTP fallback server.")
        run_stdlib_server(host=host, port=port)


if __name__ == "__main__":
    main()
