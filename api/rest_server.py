"""AetherOS API   REST Server Framework.

Provides a lightweight REST API server for external integrations
and remote system management.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("api.rest")


@dataclass
class APIResponse:
    status_code: int = 200
    body: Any = None
    headers: Dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "status": self.status_code,
            "data": self.body,
            "timestamp": datetime.utcnow().isoformat(),
        })


@dataclass
class APIRoute:
    method: str  # GET, POST, PUT, DELETE
    path: str
    handler: Callable
    auth_required: bool = True
    description: str = ""


class AetherRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for AetherOS API."""

    server_instance: Optional["APIServer"] = None

    def do_GET(self):
        self._handle_request("GET")

    def do_POST(self):
        self._handle_request("POST")

    def do_PUT(self):
        self._handle_request("PUT")

    def do_DELETE(self):
        self._handle_request("DELETE")

    def _handle_request(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if not self.server_instance:
            self._send_error(500, "Server not configured")
            return

        route = self.server_instance.find_route(method, path)
        if not route:
            self._send_error(404, f"Route not found: {method} {path}")
            return

        try:
            body = None
            if method in ("POST", "PUT"):
                content_len = int(self.headers.get("Content-Length", 0))
                if content_len > 0:
                    raw = self.rfile.read(content_len)
                    body = json.loads(raw.decode("utf-8"))

            response = route.handler(path=path, query=query, body=body)
            if not isinstance(response, APIResponse):
                response = APIResponse(body=response)

            self._send_response(response)

        except Exception as e:
            logger.error(f"API error on {method} {path}: {e}")
            self._send_error(500, str(e))

    def _send_response(self, response: APIResponse):
        self.send_response(response.status_code)
        self.send_header("Content-Type", "application/json")
        for key, val in response.headers.items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(response.to_json().encode())

    def _send_error(self, code: int, message: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())

    def log_message(self, format, *args):
        logger.debug(f"API: {format % args}")


class APIServer:
    """REST API server for AetherOS."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self._routes: List[APIRoute] = []
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False
        self._register_default_routes()

    def _register_default_routes(self):
        self.add_route(APIRoute("GET", "/api/v1/status", self._handle_status, auth_required=False))
        self.add_route(APIRoute("GET", "/api/v1/health", self._handle_health, auth_required=False))
        self.add_route(APIRoute("GET", "/api/v1/metrics", self._handle_metrics, auth_required=False))

    def _handle_status(self, **kwargs) -> APIResponse:
        return APIResponse(body={"status": "running", "version": "3.0.0", "codename": "The Singularity"})

    def _handle_health(self, **kwargs) -> APIResponse:
        return APIResponse(body={"healthy": True})

    def _handle_metrics(self, **kwargs) -> APIResponse:
        return APIResponse(body={"metrics": "available"})

    def add_route(self, route: APIRoute) -> None:
        self._routes.append(route)

    def find_route(self, method: str, path: str) -> Optional[APIRoute]:
        for route in self._routes:
            if route.method == method and path.startswith(route.path):
                return route
        return None

    def start(self) -> None:
        AetherRequestHandler.server_instance = self
        self._server = HTTPServer((self.host, self.port), AetherRequestHandler)
        self._is_running = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"API server started on {self.host}:{self.port}")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._is_running = False
            logger.info("API server stopped")

    @property
    def is_running(self) -> bool:
        return self._is_running
