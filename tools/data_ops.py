"""Data Operations Tool — Data transformation, analysis, and formatting."""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import statistics
from typing import Any, Optional

from tools.base import BaseTool, ToolResult

logger = logging.getLogger("aetheros.tools.data_ops")


class DataOps(BaseTool):
    """Data transformation and analysis operations."""

    def __init__(self):
        super().__init__("data_ops", "Data transformation, analysis, filtering, and formatting")

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        dispatch = {
            "json_parse": self._json_parse,
            "json_format": self._json_format,
            "csv_parse": self._csv_parse,
            "csv_format": self._csv_format,
            "filter": self._filter_data,
            "sort": self._sort_data,
            "aggregate": self._aggregate,
            "transform": self._transform,
            "stats": self._statistics,
            "regex_extract": self._regex_extract,
            "diff": self._diff,
        }
        handler = dispatch.get(action)
        if not handler:
            return ToolResult(success=False, error=f"Unknown data action: {action}")
        try:
            return await handler(kwargs)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": "data_ops",
            "description": "Data operations",
            "parameters": {
                "action": {"type": "string", "enum": [
                    "json_parse", "json_format", "csv_parse", "csv_format",
                    "filter", "sort", "aggregate", "transform", "stats",
                    "regex_extract", "diff",
                ]},
                "data": {"type": "string"},
                "options": {"type": "object"},
            },
        }

    async def _json_parse(self, args: dict) -> ToolResult:
        data = json.loads(args.get("data", "{}"))
        return ToolResult(success=True, output=json.dumps(data, indent=2))

    async def _json_format(self, args: dict) -> ToolResult:
        data = args.get("data", {})
        indent = args.get("indent", 2)
        return ToolResult(success=True, output=json.dumps(data, indent=indent, default=str))

    async def _csv_parse(self, args: dict) -> ToolResult:
        data = args.get("data", "")
        reader = csv.DictReader(io.StringIO(data))
        rows = list(reader)
        return ToolResult(success=True, output=json.dumps(rows, indent=2))

    async def _csv_format(self, args: dict) -> ToolResult:
        rows = args.get("data", [])
        if not rows:
            return ToolResult(success=True, output="")
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return ToolResult(success=True, output=output.getvalue())

    async def _filter_data(self, args: dict) -> ToolResult:
        data = args.get("data", [])
        field_name = args.get("field", "")
        value = args.get("value", "")
        op = args.get("operator", "eq")
        filtered = []
        for item in data:
            item_val = item.get(field_name) if isinstance(item, dict) else item
            if op == "eq" and str(item_val) == str(value):
                filtered.append(item)
            elif op == "contains" and str(value) in str(item_val):
                filtered.append(item)
            elif op == "gt" and float(item_val) > float(value):
                filtered.append(item)
            elif op == "lt" and float(item_val) < float(value):
                filtered.append(item)
        return ToolResult(success=True, output=json.dumps(filtered))

    async def _sort_data(self, args: dict) -> ToolResult:
        data = args.get("data", [])
        key = args.get("key", "")
        reverse = args.get("reverse", False)
        if key and data and isinstance(data[0], dict):
            data.sort(key=lambda x: x.get(key, ""), reverse=reverse)
        else:
            data.sort(reverse=reverse)
        return ToolResult(success=True, output=json.dumps(data))

    async def _aggregate(self, args: dict) -> ToolResult:
        data = args.get("data", [])
        group_by = args.get("group_by", "")
        agg_field = args.get("aggregate_field", "")
        agg_func = args.get("function", "count")
        groups: dict[str, list] = {}
        for item in data:
            key = item.get(group_by, "unknown") if isinstance(item, dict) else str(item)
            groups.setdefault(key, []).append(
                float(item.get(agg_field, 0)) if isinstance(item, dict) and agg_field else 1
            )
        result = {}
        for key, values in groups.items():
            if agg_func == "count":
                result[key] = len(values)
            elif agg_func == "sum":
                result[key] = sum(values)
            elif agg_func == "avg":
                result[key] = sum(values) / len(values) if values else 0
            elif agg_func == "min":
                result[key] = min(values)
            elif agg_func == "max":
                result[key] = max(values)
        return ToolResult(success=True, output=json.dumps(result))

    async def _transform(self, args: dict) -> ToolResult:
        data = args.get("data", [])
        mapping = args.get("mapping", {})
        result = []
        for item in data:
            if isinstance(item, dict):
                new_item = {}
                for new_key, old_key in mapping.items():
                    new_item[new_key] = item.get(old_key)
                result.append(new_item)
        return ToolResult(success=True, output=json.dumps(result))

    async def _statistics(self, args: dict) -> ToolResult:
        values = args.get("data", [])
        nums = [float(v) for v in values if str(v).replace(".", "").replace("-", "").isdigit()]
        if not nums:
            return ToolResult(success=False, error="No numeric data")
        stats = {
            "count": len(nums),
            "mean": statistics.mean(nums),
            "median": statistics.median(nums),
            "stdev": statistics.stdev(nums) if len(nums) > 1 else 0,
            "min": min(nums),
            "max": max(nums),
            "sum": sum(nums),
        }
        return ToolResult(success=True, output=json.dumps(stats, indent=2))

    async def _regex_extract(self, args: dict) -> ToolResult:
        text = args.get("data", "")
        pattern = args.get("pattern", "")
        matches = re.findall(pattern, text)
        return ToolResult(success=True, output=json.dumps(matches))

    async def _diff(self, args: dict) -> ToolResult:
        import difflib
        a = args.get("text_a", "").splitlines()
        b = args.get("text_b", "").splitlines()
        diff = list(difflib.unified_diff(a, b, lineterm=""))
        return ToolResult(success=True, output="\n".join(diff))
