"""Tests for AetherOS API Module."""
import pytest
from api.rest_server import APIServer, APIRoute, APIResponse


class TestAPIResponse:
    def test_to_json(self):
        resp = APIResponse(status_code=200, body={"test": True})
        js = resp.to_json()
        assert "200" in js
        assert "test" in js


class TestAPIServer:
    def test_find_route(self):
        server = APIServer()
        route = server.find_route("GET", "/api/v1/status")
        assert route is not None
        assert route.method == "GET"

    def test_missing_route(self):
        server = APIServer()
        route = server.find_route("GET", "/nonexistent")
        assert route is None

    def test_add_route(self):
        server = APIServer()
        server.add_route(APIRoute("POST", "/api/v1/custom", handler=lambda **kw: {"ok": True}))
        route = server.find_route("POST", "/api/v1/custom")
        assert route is not None
