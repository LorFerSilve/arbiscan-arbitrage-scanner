"""Local loopback HTTP integration tests without external API requests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
from threading import Thread
from typing import Any
from unittest.mock import patch

from arbiscan.api.http import create_local_http_server
from arbiscan.api.service import ArbiScanApi
from arbiscan.api.synthetic import SyntheticApiDataSource


@contextmanager
def _server(*, demo: bool = False, source: SyntheticApiDataSource | None = None) -> Iterator[int]:
    api = ArbiScanApi(source or SyntheticApiDataSource(demo=demo), version="test-1")
    with create_local_http_server(
        api=api, mode="synthetic" if demo else "empty", version="test-1", port=0
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            thread.join(timeout=3)


def _request(
    port: int,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        payload: dict[str, Any] = json.loads(response.read())
        return response.status, payload, dict(response.getheaders())
    finally:
        connection.close()


def _raw_request(
    port: int, path: str, *, headers: dict[str, str] | None = None
) -> tuple[int, bytes, dict[str, str]]:
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        connection.close()


def test_dashboard_assets_are_local_read_only_and_csp_protected() -> None:
    with _server(demo=True) as port:
        status, html, headers = _raw_request(port, "/")
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Arbiscan-Data-Mode"] == "synthetic"
        csp = headers["Content-Security-Policy"]
        assert "default-src 'none'" in csp
        assert "script-src 'self'" in csp
        assert "connect-src 'self'" in csp
        assert "unsafe-inline" not in csp
        assert b"/assets/styles.css" in html
        assert b"/assets/app.js" in html
        assert b'id="opportunity-rows"' in html
        assert b'id="detail-drawer"' in html
        assert b'id="provider-filter"' in html

        css_status, css, css_headers = _raw_request(port, "/assets/styles.css")
        assert css_status == 200
        assert css_headers["Content-Type"].startswith("text/css")
        assert b"@media(max-width:680px)" in css
        js_status, js, js_headers = _raw_request(port, "/assets/app.js")
        assert js_status == 200
        assert js_headers["Content-Type"].startswith("text/javascript")
        assert b"fetch(path" in js
        assert b"textContent" in js
        assert b"innerHTML" not in js.replace(b"never innerHTML", b"")
        assert b"window.location = " not in js
        assert b"THE_ODDS_API_KEY" not in js
        assert b"ODDSPAPI_API_KEY" not in js


def test_web_asset_allowlist_rejects_traversal_query_and_host_spoofing() -> None:
    with _server(demo=True) as port:
        for path in (
            "/assets/secrets.env",
            "/assets/app.js.bak",
            "/robots.txt",
        ):
            assert _request(port, path)[0] == 404
        for path in (
            "/assets/%2e%2e/app.js",
            "/assets/styles.css?debug=1",
            "/?mode=live",
        ):
            assert _request(port, path)[0] == 400
        for path in ("/", "/assets/styles.css", "/assets/app.js"):
            status, _, _ = _raw_request(port, path, headers={"Host": "evil.example"})
            assert status == 403


def test_empty_server_exposes_only_read_only_unready_contract() -> None:
    with _server() as port:
        for path in (
            "/api/v1/providers/status",
            "/api/v1/sports",
            "/api/v1/events",
            "/api/v1/odds",
            "/api/v1/opportunities",
        ):
            status, body, headers = _request(port, path)
            assert status == 200
            assert body["items"] == []
            assert body["total"] == 0
            assert headers["X-Arbiscan-Data-Mode"] == "empty"
        status, ready, _ = _request(port, "/api/v1/ready")
        assert status == 200
        assert ready["ready"] is False
        assert ready["checks"]["live_provider_ingestion"] is False
        assert ready["checks"]["phase19_quote_authorized"] is False
        assert _request(port, "/api/v1/readiness")[1] == ready


def test_status_health_and_openapi_are_versioned_and_explicit_about_demo() -> None:
    with _server(demo=True) as port:
        root_status, html, headers = _raw_request(port, "/")
        assert root_status == 200
        assert b"ArbiScan" in html
        assert b"/assets/app.js" in html
        assert headers["X-Arbiscan-Data-Mode"] == "synthetic"
        assert _request(port, "/api/v1/health")[1] == {
            "status": "ok",
            "version": "test-1",
        }
        mode = _request(port, "/api/v1/runtime")[1]
        assert mode == {
            "data_mode": "synthetic",
            "scanner_only": True,
            "live_provider_ingestion": False,
            "live_quote_authorized": False,
            "provider_calls_on_refresh": 0,
        }
        api_spec = _request(port, "/api/v1/openapi.json")[1]
        assert "/api/v1/health" in api_spec["paths"]
        assert "/api/v1/opportunities/{opportunity_id}" in api_spec["paths"]
        assert "/api/v1/runtime" in api_spec["paths"]
        assert "/api/v1/readiness" in api_spec["paths"]
        assert api_spec["servers"][0]["url"] == "/"


def test_demo_never_presents_imaginary_data_as_live_actionable() -> None:
    with _server(demo=True) as port:
        _, events, headers = _request(port, "/api/v1/events")
        assert headers["X-Arbiscan-Data-Mode"] == "synthetic"
        assert events["total"] == 1
        assert events["items"][0]["status"] == "synthetic"
        assert events["items"][0]["competition"] == "Synthetic Test League"
        assert events["items"][0]["participant_names"] == ["Example FC", "Sample Town"]
        _, quotes, _ = _request(port, "/api/v1/odds")
        assert quotes["total"] == 3
        assert all(item["status"] == "synthetic" for item in quotes["items"])
        assert {x["provider_id"] for x in quotes["items"]} == {
            "synthetic-source-a",
            "synthetic-source-b",
        }
        _, opportunities, _ = _request(port, "/api/v1/opportunities")
        assert opportunities["total"] == 1
        assert opportunities["items"][0]["opportunity_id"].startswith("synthetic-")
        _, providers, _ = _request(port, "/api/v1/providers/status")
        assert all(not item["available"] for item in providers["items"])
        metrics = _request(port, "/api/v1/metrics")[1]["values"]
        assert metrics["active_quotes"] == 0
        assert metrics["actionable_opportunities"] == 0
        assert metrics["synthetic_quotes"] == 3
        assert _request(port, "/api/v1/ready")[1]["ready"] is False


def test_opportunity_detail_uses_phase13_model_and_marks_evidence_missing() -> None:
    with _server(demo=True) as port:
        status, detail, _ = _request(port, "/api/v1/opportunities/synthetic-opportunity-1")
        assert status == 200
        assert float(detail["opportunity"]["implied_probability_sum"]) == 0.9
        assert len(detail["quote_ids"]) == 3
        assert detail["evidence_available"] is False
        plan = detail["stake_plan"]
        assert plan["synthetic"] is True
        assert plan["currency"] == "EUR"
        assert plan["bankroll"] == "100.00"
        assert len(plan["allocations"]) == 3
        assert 0 < float(plan["total_staked"]) <= 100.00
        assert float(plan["guaranteed_profit"]) > 0
        assert "Geen transactiekosten" in " ".join(plan["assumptions"])
        status, error, _ = _request(port, "/api/v1/opportunities/not-present")
        assert status == 404
        assert error["code"] == "not_found"
        status, error, _ = _request(port, "/api/v1/opportunities/a%2Fb")
        assert status == 400
        assert error["code"] == "bad_request"


def test_strict_pagination_and_filters_reuse_phase13_api_methods() -> None:
    with _server(demo=True) as port:
        for path, count in (
            ("/api/v1/events?sport=football", 1),
            ("/api/v1/events?sport=tennis", 0),
            ("/api/v1/events?status=synthetic", 1),
            ("/api/v1/odds?provider_id=synthetic-source-a", 1),
            ("/api/v1/odds?event_id=missing", 0),
            ("/api/v1/opportunities?event_id=synthetic-event-1", 1),
            ("/api/v1/opportunities?event_id=missing", 0),
        ):
            assert _request(port, path)[1]["total"] == count
        _, page, _ = _request(port, "/api/v1/odds?offset=1&limit=1")
        assert page["offset"] == 1
        assert page["limit"] == 1
        assert page["total"] == 3
        assert page["has_more"] is True
        assert len(page["items"]) == 1


def test_bad_paths_and_query_parameters_fail_closed() -> None:
    paths = (
        "/api/v1/events?limit=0",
        "/api/v1/events?limit=201",
        "/api/v1/events?offset=-1",
        "/api/v1/events?offset=%2B1",
        "/api/v1/events?offset=1000001",
        "/api/v1/events?offset=99999999999999",
        "/api/v1/events?offset=1&offset=2",
        "/api/v1/events?bad=1",
        "/api/v1/ready?limit=1",
        "/api/v1/odds?event_id=",
        "/api/v1/events?status=%0Asecret",
        "/api/v1/events?offset=1&limit=not-a-number",
        "/api/v1/events?offset=1&limit=1&unexpected=1",
        "/api/v1/events?offset=1&limit=1&",
        "http://example.com/api/v1/health",
        "/api/v1/opportunities/..",
    )
    with _server(demo=True) as port:
        for path in paths:
            headers = {"Host": f"127.0.0.1:{port}"} if path.startswith("http://") else None
            status, error, _ = _request(port, path, headers=headers)
            assert status == 400
            assert error["code"] == "bad_request"
            assert "apiKey" not in str(error)


def test_write_and_cors_preflight_methods_are_disabled() -> None:
    with _server(demo=True) as port:
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            status, error, _ = _request(port, "/api/v1/events", method=method)
            assert status == 405
            assert error["code"] == "forbidden"


def test_strict_local_host_and_origin_guards_block_dns_rebinding() -> None:
    with _server(demo=True) as port:
        for headers in (
            {"Host": "evil.example"},
            {"Origin": "http://evil.example"},
            {"Origin": "null"},
            {"Host": "localhost:99999"},
        ):
            status, error, _ = _request(port, "/api/v1/events", headers=headers)
            assert status == 403
            assert error["code"] == "forbidden"
        status, _, headers = _request(
            port, "/api/v1/health", headers={"Origin": f"http://127.0.0.1:{port}"}
        )
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
        assert "Access-Control-Allow-Origin" not in headers


def test_unknown_paths_and_get_with_request_body_are_rejected() -> None:
    with _server() as port:
        assert _request(port, "/api/v1/unknown")[0] == 404
        status, error, _ = _request(port, "/api/v1/health", headers={"Content-Length": "42"})
        assert status == 400
        assert error["code"] == "bad_request"


def test_loopback_only_server_rejects_remote_bind() -> None:
    api = ArbiScanApi(SyntheticApiDataSource(), version="test-1")
    for host in ("0.0.0.0", "::", "localhost", "192.168.1.42"):
        try:
            create_local_http_server(api=api, mode="empty", version="test-1", port=0, host=host)
        except ValueError as error:
            assert "127.0.0.1" in str(error)
        else:
            raise AssertionError("non-local server bind must fail closed")


def test_no_external_provider_requests_even_after_repeated_http_refresh() -> None:
    with (
        patch(
            "arbiscan.providers.UrllibAsyncHttpTransport.get",
            side_effect=AssertionError("provider HTTP must never be called"),
        ),
        _server(demo=True) as port,
    ):
        for _ in range(3):
            assert _request(port, "/api/v1/odds")[0] == 200
            assert _request(port, "/api/v1/opportunities")[0] == 200


class _BrokenSource(SyntheticApiDataSource):
    def events(self) -> tuple[Any, ...]:
        raise RuntimeError("secret apiKey=never-log-this")


def test_internal_error_is_sanitized_and_never_leaks_secrets() -> None:
    with _server(source=_BrokenSource()) as port:
        status, error, _ = _request(port, "/api/v1/events")
        assert status == 500
        assert error["code"] == "internal_error"
        assert "apiKey" not in str(error)
        assert "never-log-this" not in str(error)
