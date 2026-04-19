"""Web search and scraping operations."""
from __future__ import annotations

import html
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional

from tools.base import BaseTool, ToolResult

logger = logging.getLogger("aetheros.tools.web_ops")


class HTTPClient:
    """Lightweight HTTP client using urllib."""

    DEFAULT_HEADERS = {
        "User-Agent": "AetherOS/1.0 (Autonomous Agent System)",
        "Accept": "text/html,application/json,text/plain",
        "Accept-Language": "en-US,en;q=0.9",
    }

    @staticmethod
    def get(url: str, headers: Optional[dict] = None, timeout: int = 30) -> dict:
        """Perform HTTP GET request."""
        all_headers = {**HTTPClient.DEFAULT_HEADERS, **(headers or {})}
        req = urllib.request.Request(url, headers=all_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read()
                encoding = "utf-8"
                if "charset=" in content_type:
                    encoding = content_type.split("charset=")[-1].split(";")[0].strip()
                body = raw.decode(encoding, errors="replace")
                return {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "body": body,
                    "content_type": content_type,
                    "url": resp.url,
                }
        except urllib.error.HTTPError as e:
            return {"status": e.code, "error": str(e), "body": ""}
        except Exception as e:
            return {"status": 0, "error": str(e), "body": ""}

    @staticmethod
    def post(url: str, data: dict, headers: Optional[dict] = None, timeout: int = 30) -> dict:
        """Perform HTTP POST request."""
        all_headers = {**HTTPClient.DEFAULT_HEADERS, **(headers or {})}
        if "Content-Type" not in all_headers:
            all_headers["Content-Type"] = "application/json"
        encoded = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=encoded, headers=all_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return {"status": resp.status, "body": body, "headers": dict(resp.headers)}
        except Exception as e:
            return {"status": 0, "error": str(e), "body": ""}


class HTMLParser:
    """Simple HTML content extractor."""

    @staticmethod
    def extract_text(html_content: str, max_length: int = 50000) -> str:
        """Extract readable text from HTML."""
        text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_length]

    @staticmethod
    def extract_links(html_content: str, base_url: str = "") -> list[dict]:
        """Extract links from HTML."""
        pattern = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
        links = []
        for match in pattern.finditer(html_content):
            href = match.group(1)
            text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if base_url and not href.startswith(("http://", "https://")):
                href = urllib.parse.urljoin(base_url, href)
            if text and href:
                links.append({"url": href, "text": text[:200]})
        return links[:100]

    @staticmethod
    def extract_metadata(html_content: str) -> dict:
        """Extract page metadata."""
        meta = {}
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.DOTALL | re.IGNORECASE)
        if title_match:
            meta["title"] = html.unescape(title_match.group(1).strip())

        for m in re.finditer(r'<meta\s+[^>]*(?:name|property)=["\']([^"\']+)["\'][^>]*content=["\']([^"\']+)["\']', html_content, re.IGNORECASE):
            meta[m.group(1).lower()] = m.group(2)
        return meta


class WebSearchEngine:
    """Web search using DuckDuckGo HTML."""

    @staticmethod
    def search(query: str, max_results: int = 10) -> list[dict]:
        """Search the web using DuckDuckGo."""
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        response = HTTPClient.get(url, timeout=15)
        if response.get("status") != 200:
            return [{"title": "Search unavailable", "url": "", "snippet": response.get("error", "")}]

        results = []
        body = response.get("body", "")
        # Parse DuckDuckGo HTML results
        result_pattern = re.compile(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        for match in result_pattern.finditer(body):
            href = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()

            # Decode DDG redirect URL
            if "uddg=" in href:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = parsed.get("uddg", [href])[0]

            results.append({"title": html.unescape(title), "url": href, "snippet": html.unescape(snippet)})
            if len(results) >= max_results:
                break

        return results or [{"title": "No results found", "url": "", "snippet": f"Query: {query}"}]


class WebOps(BaseTool):
    """Web search and scraping operations."""

    def __init__(self, timeout: int = 30):
        super().__init__("web_ops", "Web search and content scraping")
        self.client = HTTPClient()
        self.parser = HTMLParser()
        self.search_engine = WebSearchEngine()
        self.timeout = timeout

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "search")
        dispatch = {
            "search": self._search,
            "fetch": self._fetch_page,
            "scrape": self._scrape,
            "links": self._extract_links,
            "api": self._api_call,
            "download": self._download,
        }
        handler = dispatch.get(action)
        if not handler:
            return ToolResult(success=False, error=f"Unknown action: {action}")
        return await handler(kwargs)

    def get_schema(self) -> dict:
        return {
            "name": "web_ops",
            "description": "Web search and content scraping",
            "parameters": {
                "action": {"type": "string", "enum": ["search", "fetch", "scrape", "links", "api", "download"]},
                "query": {"type": "string"},
                "url": {"type": "string"},
                "method": {"type": "string", "default": "GET"},
                "headers": {"type": "object"},
                "data": {"type": "object"},
            },
        }

    async def _search(self, args: dict) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(success=False, error="No search query provided")
        max_results = args.get("max_results", 10)
        results = self.search_engine.search(query, max_results)
        output = "\n\n".join(
            f"[{i + 1}] {r['title']}\n    {r['url']}\n    {r['snippet']}"
            for i, r in enumerate(results)
        )
        return ToolResult(
            success=True,
            output=output,
            metadata={"results_count": len(results), "query": query, "results": results},
        )

    async def _fetch_page(self, args: dict) -> ToolResult:
        url = args.get("url", "")
        if not url:
            return ToolResult(success=False, error="No URL provided")
        response = self.client.get(url, headers=args.get("headers"), timeout=self.timeout)
        if response.get("error"):
            return ToolResult(success=False, error=response["error"])
        text = self.parser.extract_text(response["body"])
        meta = self.parser.extract_metadata(response["body"])
        return ToolResult(
            success=True,
            output=text[:10000],
            metadata={"url": url, "status": response["status"], "meta": meta},
        )

    async def _scrape(self, args: dict) -> ToolResult:
        url = args.get("url", "")
        if not url:
            return ToolResult(success=False, error="No URL provided")
        selector = args.get("selector", "")
        response = self.client.get(url, timeout=self.timeout)
        if response.get("error"):
            return ToolResult(success=False, error=response["error"])

        body = response["body"]
        text = self.parser.extract_text(body)
        links = self.parser.extract_links(body, url)
        meta = self.parser.extract_metadata(body)
        output = f"Title: {meta.get('title', 'N/A')}\n\n{text[:8000]}"

        return ToolResult(
            success=True,
            output=output,
            metadata={"url": url, "links_count": len(links), "meta": meta},
        )

    async def _extract_links(self, args: dict) -> ToolResult:
        url = args.get("url", "")
        if not url:
            return ToolResult(success=False, error="No URL provided")
        response = self.client.get(url, timeout=self.timeout)
        if response.get("error"):
            return ToolResult(success=False, error=response["error"])
        links = self.parser.extract_links(response["body"], url)
        output = "\n".join(f"[{l['text'][:60]}] → {l['url']}" for l in links)
        return ToolResult(success=True, output=output, metadata={"count": len(links), "links": links})

    async def _api_call(self, args: dict) -> ToolResult:
        url = args.get("url", "")
        method = args.get("method", "GET").upper()
        if not url:
            return ToolResult(success=False, error="No URL provided")
        try:
            if method == "GET":
                response = self.client.get(url, headers=args.get("headers"), timeout=self.timeout)
            elif method == "POST":
                response = self.client.post(url, data=args.get("data", {}),
                                            headers=args.get("headers"), timeout=self.timeout)
            else:
                return ToolResult(success=False, error=f"Unsupported method: {method}")

            if response.get("error"):
                return ToolResult(success=False, error=response["error"])

            try:
                parsed = json.loads(response["body"])
                body = json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                body = response["body"]

            return ToolResult(
                success=True,
                output=body[:20000],
                metadata={"status": response["status"], "url": url, "method": method},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _download(self, args: dict) -> ToolResult:
        url = args.get("url", "")
        output_path = args.get("output_path", f"/tmp/aether_download_{int(datetime.now().timestamp())}")
        if not url:
            return ToolResult(success=False, error="No URL provided")
        try:
            urllib.request.urlretrieve(url, output_path)
            size = os.path.getsize(output_path)
            return ToolResult(
                success=True,
                output=f"Downloaded {url} → {output_path} ({size:,} bytes)",
                artifacts=[output_path],
                metadata={"path": output_path, "size": size},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


import os
