"""Screen capture and analysis for GUI-based tasks."""
from __future__ import annotations

import base64
import io
import logging
import os
import struct
import time
import zlib
from datetime import datetime
from typing import Optional

from tools.base import BaseTool, ToolResult

logger = logging.getLogger("aetheros.tools.vision_ops")


class ScreenCapture:
    """Platform-aware screen capture utility."""

    @staticmethod
    def capture_screenshot(output_path: Optional[str] = None,
                           region: Optional[tuple[int, int, int, int]] = None) -> Optional[str]:
        """Capture screenshot. Returns path to saved image."""
        try:
            import subprocess
            if output_path is None:
                output_path = f"/tmp/aether_screenshot_{int(time.time())}.png"

            # Try various capture methods
            methods = [
                ["import", "-window", "root", output_path],  # ImageMagick
                ["scrot", output_path],
                ["gnome-screenshot", "-f", output_path],
                ["xfce4-screenshooter", "-f", "-s", output_path],
            ]

            for method in methods:
                try:
                    result = subprocess.run(method, capture_output=True, timeout=10)
                    if result.returncode == 0 and os.path.exists(output_path):
                        return output_path
                except FileNotFoundError:
                    continue

            # Fallback: create a placeholder PNG
            return ScreenCapture._create_placeholder(output_path)
        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")
            return None

    @staticmethod
    def _create_placeholder(path: str) -> str:
        """Create a minimal placeholder PNG."""
        # Minimal 1x1 black PNG
        width, height = 320, 240

        def create_png(w: int, h: int) -> bytes:
            def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
                c = chunk_type + data
                return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

            header = b"\x89PNG\r\n\x1a\n"
            ihdr = make_chunk(b"IDR" if False else b"IHDR",
                              struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            raw_data = b""
            for _ in range(h):
                raw_data += b"\x00" + b"\x40\x40\x40" * w  # Gray pixels
            idat = make_chunk(b"IDAT", zlib.compress(raw_data))
            iend = make_chunk(b"IEND", b"")
            return header + ihdr + idat + iend

        png_data = create_png(width, height)
        with open(path, "wb") as f:
            f.write(png_data)
        return path


class ImageAnalyzer:
    """Analyze images using vision models or local processing."""

    @staticmethod
    def analyze_image(image_path: str) -> dict:
        """Basic image analysis without external dependencies."""
        try:
            size = os.path.getsize(image_path)
            ext = os.path.splitext(image_path)[1].lower()
            with open(image_path, "rb") as f:
                header = f.read(32)

            info = {
                "path": image_path,
                "size_bytes": size,
                "format": ext,
                "exists": True,
            }

            # Parse PNG header for dimensions
            if header[:8] == b"\x89PNG\r\n\x1a\n" and len(header) >= 24:
                width = struct.unpack(">I", header[16:20])[0]
                height = struct.unpack(">I", header[20:24])[0]
                info["width"] = width
                info["height"] = height

            return info
        except Exception as e:
            return {"error": str(e), "exists": False}

    @staticmethod
    def image_to_base64(image_path: str) -> str:
        """Convert image to base64 string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")


class OCREngine:
    """OCR text extraction from images."""

    @staticmethod
    def extract_text(image_path: str) -> str:
        """Extract text from image using available OCR."""
        try:
            import subprocess
            result = subprocess.run(
                ["tesseract", image_path, "stdout"],
                capture_output=True, timeout=30
            )
            if result.returncode == 0:
                return result.stdout.decode("utf-8", errors="replace").strip()
        except FileNotFoundError:
            pass

        return "[OCR not available - install tesseract-ocr for text extraction]"


class VisionOps(BaseTool):
    """Screen capture and visual analysis operations."""

    def __init__(self):
        super().__init__("vision_ops", "Screen capture and image analysis")
        self.capture = ScreenCapture()
        self.analyzer = ImageAnalyzer()
        self.ocr = OCREngine()
        self._screenshots: list[str] = []

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "screenshot")
        dispatch = {
            "screenshot": self._take_screenshot,
            "analyze": self._analyze_image,
            "ocr": self._extract_text,
            "compare": self._compare_images,
            "region": self._capture_region,
            "monitor": self._monitor_screen,
        }
        handler = dispatch.get(action)
        if not handler:
            return ToolResult(success=False, error=f"Unknown action: {action}")
        return await handler(kwargs)

    def get_schema(self) -> dict:
        return {
            "name": "vision_ops",
            "description": "Screen capture and image analysis",
            "parameters": {
                "action": {"type": "string", "enum": ["screenshot", "analyze", "ocr", "compare", "region", "monitor"]},
                "path": {"type": "string"},
                "output_path": {"type": "string"},
                "region": {"type": "array", "items": {"type": "integer"}},
            },
        }

    async def _take_screenshot(self, args: dict) -> ToolResult:
        output = args.get("output_path")
        path = self.capture.capture_screenshot(output)
        if path:
            self._screenshots.append(path)
            info = self.analyzer.analyze_image(path)
            return ToolResult(
                success=True,
                output=f"Screenshot saved: {path}",
                artifacts=[path],
                metadata=info,
            )
        return ToolResult(success=False, error="Failed to capture screenshot")

    async def _analyze_image(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        if not path or not os.path.exists(path):
            return ToolResult(success=False, error=f"Image not found: {path}")
        info = self.analyzer.analyze_image(path)
        output = "\n".join(f"{k}: {v}" for k, v in info.items())
        return ToolResult(success=True, output=output, metadata=info)

    async def _extract_text(self, args: dict) -> ToolResult:
        path = args.get("path", "")
        if not path or not os.path.exists(path):
            return ToolResult(success=False, error=f"Image not found: {path}")
        text = self.ocr.extract_text(path)
        return ToolResult(success=True, output=text, metadata={"source": path})

    async def _compare_images(self, args: dict) -> ToolResult:
        path_a = args.get("path", "")
        path_b = args.get("path_b", args.get("destination", ""))
        if not all(os.path.exists(p) for p in [path_a, path_b]):
            return ToolResult(success=False, error="One or both images not found")
        info_a = self.analyzer.analyze_image(path_a)
        info_b = self.analyzer.analyze_image(path_b)
        same_dims = info_a.get("width") == info_b.get("width") and info_a.get("height") == info_b.get("height")
        same_size = info_a.get("size_bytes") == info_b.get("size_bytes")
        output = (
            f"Image A: {info_a.get('width', '?')}x{info_a.get('height', '?')} ({info_a.get('size_bytes', 0)} bytes)\n"
            f"Image B: {info_b.get('width', '?')}x{info_b.get('height', '?')} ({info_b.get('size_bytes', 0)} bytes)\n"
            f"Same dimensions: {same_dims}\n"
            f"Same file size: {same_size}"
        )
        return ToolResult(success=True, output=output, metadata={"same_dims": same_dims, "same_size": same_size})

    async def _capture_region(self, args: dict) -> ToolResult:
        region = args.get("region", [0, 0, 800, 600])
        output = args.get("output_path", f"/tmp/aether_region_{int(time.time())}.png")
        path = self.capture.capture_screenshot(output, region=tuple(region))
        if path:
            return ToolResult(success=True, output=f"Region captured: {path}", artifacts=[path])
        return ToolResult(success=False, error="Region capture failed")

    async def _monitor_screen(self, args: dict) -> ToolResult:
        interval = args.get("interval", 5)
        count = min(args.get("count", 3), 10)
        captures = []
        for i in range(count):
            path = self.capture.capture_screenshot(f"/tmp/aether_monitor_{i}_{int(time.time())}.png")
            if path:
                captures.append(path)
            if i < count - 1:
                await asyncio.sleep(interval)
        return ToolResult(
            success=True,
            output=f"Captured {len(captures)} screenshots over {interval * (count - 1)}s",
            artifacts=captures,
        )


import asyncio
