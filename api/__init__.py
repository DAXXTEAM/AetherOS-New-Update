"""AetherOS API Module   REST API and WebSocket interfaces."""
from api.rest_server import APIServer, APIRoute, APIResponse
from api.websocket_handler import WebSocketManager, WSMessage

__all__ = [
    "APIServer", "APIRoute", "APIResponse",
    "WebSocketManager", "WSMessage",
]
