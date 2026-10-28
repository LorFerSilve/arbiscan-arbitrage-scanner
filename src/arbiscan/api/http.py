"""Loopback-only, read-only HTTP transport for the existing Phase 13 API.

No odds-provider adapter, network polling, persistence or bet execution.
Only Python's standard library is used. Phase 20.2 will add the browser UI.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import parse_qsl, urlsplit

from arbiscan.api.contracts import ApiError, ErrorCode, Page, PageRequest
from arbiscan.api.openapi import openapi_document
from arbiscan.api.service import ArbiScanApi

API_PREFIX = "/api/v1"
_LOCAL_HOST = "127.0.0.1"
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def _parameters(raw_query: str, *, allowed: frozenset[str]) -> dict[str, str]:
    if len(raw_query) > 2048:
        raise ValueError("query too long")
    pairs = parse_qsl(raw_query, keep_blank_values=True, strict_parsing=True, max_num_fields=12)
    params: dict[str, str] = {}
    for key, value in pairs:
        if key not in allowed or key in params or not value or len(value) > 256:
            raise ValueError("invalid query parameter")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("control character in query")
        params[key] = value
    return params


def _page(params: dict[str, str]) -> PageRequest:
    offset_text, limit_text = params.get("offset", "0"), params.get("limit", "50")
    if (
        not offset_text.isascii()
        or not offset_text.isdecimal()
        or len(offset_text) > 9
        or not limit_text.isascii()
        or not limit_text.isdecimal()
        or len(limit_text) > 3
    ):
        raise ValueError("invalid page")
    offset, limit = int(offset_text), int(limit_text)
    if offset > 1_000_000:
        raise ValueError("offset too large")
    return PageRequest(offset=offset, limit=limit)


def _openapi(version: str) -> dict[str, Any]:
    document = openapi_document(version=version)
    document["paths"] = {API_PREFIX + path: methods for path, methods in document["paths"].items()}
    document["paths"][API_PREFIX + "/runtime"] = {
        "get": {"summary": "Local synthetic/empty mode and disabled live access"}
    }
    document["paths"][API_PREFIX + "/readiness"] = document["paths"][API_PREFIX + "/ready"]
    document["servers"] = [{"url": "/"}]
    return document


def _dispatch(
    api: ArbiScanApi, *, path: str, raw_query: str, mode: str, version: str
) -> tuple[HTTPStatus, object]:
    """Never consult providers; only call the existing application API."""
    if path == "/":
        _parameters(raw_query, allowed=frozenset())
        return HTTPStatus.OK, {
            "service": "ArbiScan Phase 20.1 local HTTP API",
            "data_mode": mode,
            "browser_dashboard": "planned for Phase 20.2",
            "api_base": API_PREFIX,
        }
    if path == API_PREFIX + "/runtime":
        _parameters(raw_query, allowed=frozenset())
        return HTTPStatus.OK, {
            "data_mode": mode,
            "scanner_only": True,
            "live_provider_ingestion": False,
            "live_quote_authorized": False,
            "provider_calls_on_refresh": 0,
        }
    if path == API_PREFIX + "/openapi.json":
        _parameters(raw_query, allowed=frozenset())
        return HTTPStatus.OK, _openapi(version)
    simple = {
        API_PREFIX + "/health": api.health,
        API_PREFIX + "/ready": api.readiness,
        API_PREFIX + "/readiness": api.readiness,
        API_PREFIX + "/configuration/status": api.configuration,
        API_PREFIX + "/metrics": api.metrics,
    }
    if path in simple:
        _parameters(raw_query, allowed=frozenset())
        return HTTPStatus.OK, simple[path]()
    collections = {
        API_PREFIX + "/providers/status": frozenset({"offset", "limit"}),
        API_PREFIX + "/sports": frozenset({"offset", "limit"}),
        API_PREFIX + "/events": frozenset({"offset", "limit", "sport", "status"}),
        API_PREFIX + "/odds": frozenset({"offset", "limit", "event_id", "provider_id"}),
        API_PREFIX + "/opportunities": frozenset({"offset", "limit", "event_id"}),
    }
    if path in collections:
        params = _parameters(raw_query, allowed=collections[path])
        page = _page(params)
        if path.endswith("/providers/status"):
            return HTTPStatus.OK, api.providers(page)
        if path.endswith("/sports"):
            return HTTPStatus.OK, api.sports(page)
        if path.endswith("/events"):
            return HTTPStatus.OK, api.events(
                page, sport=params.get("sport"), status=params.get("status")
            )
        if path.endswith("/odds"):
            return HTTPStatus.OK, api.odds(
                page, event_id=params.get("event_id"), provider_id=params.get("provider_id")
            )
        return HTTPStatus.OK, api.opportunities(page, event_id=params.get("event_id"))
    detail_prefix = API_PREFIX + "/opportunities/"
    if path.startswith(detail_prefix):
        _parameters(raw_query, allowed=frozenset())
        item_id = path.removeprefix(detail_prefix)
        if not _SAFE_ID.fullmatch(item_id):
            raise ValueError("invalid opportunity identifier")
        detail = api.opportunity(item_id)
        if detail is None:
            return HTTPStatus.NOT_FOUND, asdict(ApiError(ErrorCode.NOT_FOUND, "Not found"))
        return HTTPStatus.OK, detail
    return HTTPStatus.NOT_FOUND, asdict(ApiError(ErrorCode.NOT_FOUND, "Not found"))


def _serialize(value: object) -> bytes:
    if isinstance(value, Page):
        page_data = asdict(value)
        page_data["has_more"] = value.has_more
        value = page_data
    elif is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def create_local_http_server(
    *, api: ArbiScanApi, mode: str, version: str, port: int = 8000, host: str = _LOCAL_HOST
) -> ThreadingHTTPServer:
    """Create a socket only on 127.0.0.1; test suites may use port 0."""
    if host != _LOCAL_HOST:
        raise ValueError("Phase 20.1 only permits binding to 127.0.0.1")
    if not 0 <= port <= 65535 or type(port) is not int:
        raise ValueError("invalid local port")
    if mode not in {"synthetic", "empty"}:
        raise ValueError("unknown data mode")

    class LocalHandler(BaseHTTPRequestHandler):
        server_version = "ArbiScanLocalAPI"
        sys_version = ""

        def log_message(self, format: str, *args: object) -> None:
            # Do not emit URL/query parameters or secrets into access logs.
            return

        def _send(self, status: HTTPStatus, payload: object) -> None:
            data = _serialize(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("X-Arbiscan-Data-Mode", mode)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            server_port = cast(ThreadingHTTPServer, self.server).server_port
            allowed_hosts = {
                f"127.0.0.1:{server_port}",
                f"localhost:{server_port}",
            }
            request_host = self.headers.get("Host", "")
            if (
                request_host not in allowed_hosts
                or self.headers.get("Origin", f"http://{request_host}") != f"http://{request_host}"
            ):
                self._send(
                    HTTPStatus.FORBIDDEN,
                    asdict(ApiError(ErrorCode.FORBIDDEN, "Local origin required")),
                )
                return
            if (
                self.headers.get("Transfer-Encoding")
                or self.headers.get("Content-Length", "0") != "0"
            ):
                self._send(
                    HTTPStatus.BAD_REQUEST,
                    asdict(ApiError(ErrorCode.BAD_REQUEST, "GET request body not accepted")),
                )
                return
            try:
                parsed = urlsplit(self.path)
                if (
                    parsed.scheme
                    or parsed.netloc
                    or parsed.fragment
                    or len(parsed.path) > 512
                    or "%" in parsed.path
                ):
                    raise ValueError("unsafe request path")
                status, payload = _dispatch(
                    api,
                    path=parsed.path,
                    raw_query=parsed.query,
                    mode=mode,
                    version=version,
                )
            except (ValueError, UnicodeError):
                status = HTTPStatus.BAD_REQUEST
                payload = asdict(ApiError(ErrorCode.BAD_REQUEST, "Invalid request"))
            except Exception:
                # Do not expose provider configuration, tracebacks or secrets.
                status = HTTPStatus.INTERNAL_SERVER_ERROR
                payload = asdict(ApiError(ErrorCode.INTERNAL_ERROR, "Internal error"))
            self._send(status, payload)

        def _readonly(self) -> None:
            # All request methods other than GET are disallowed.
            self._send(
                HTTPStatus.METHOD_NOT_ALLOWED,
                asdict(ApiError(ErrorCode.FORBIDDEN, "Read-only API: GET only")),
            )

        do_POST = _readonly
        do_PUT = _readonly
        do_PATCH = _readonly
        do_DELETE = _readonly
        do_OPTIONS = _readonly
        do_HEAD = _readonly

    return ThreadingHTTPServer((host, port), LocalHandler)
