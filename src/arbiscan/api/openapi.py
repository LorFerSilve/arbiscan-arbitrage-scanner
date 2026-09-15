"""Dependency-free OpenAPI description of the Phase 13 public surface."""

from typing import Any

_ENDPOINTS: tuple[tuple[str, str, str], ...] = (
    ("/health", "get", "Health and version"),
    ("/ready", "get", "Readiness checks"),
    ("/providers/status", "get", "Provider ingestion status"),
    ("/sports", "get", "Supported sports"),
    ("/events", "get", "Canonical events"),
    ("/odds", "get", "Current canonical odds"),
    ("/opportunities", "get", "Arbitrage opportunities"),
    ("/opportunities/{opportunity_id}", "get", "Opportunity detail and provenance"),
    ("/configuration/status", "get", "Safe public configuration status"),
    ("/metrics", "get", "Operational metrics"),
)


def openapi_document(*, version: str) -> dict[str, Any]:
    """Return the transport contract without importing a web framework."""
    paths: dict[str, Any] = {}
    for path, method, summary in _ENDPOINTS:
        operation: dict[str, Any] = {
            "summary": summary,
            "responses": {
                "200": {"description": "Successful response"},
                "400": {"description": "Bad request"},
                "429": {"description": "Rate limited"},
                "500": {"description": "Internal error"},
            },
        }
        if "{opportunity_id}" in path:
            operation["parameters"] = [
                {
                    "name": "opportunity_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "minLength": 1},
                }
            ]
            operation["responses"]["404"] = {"description": "Opportunity not found"}
        paths[path] = {method: operation}

    return {
        "openapi": "3.1.0",
        "info": {"title": "ArbiScan API", "version": version},
        "paths": paths,
        "components": {
            "schemas": {
                "ApiError": {
                    "type": "object",
                    "required": ["code", "message"],
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "correlation_id": {"type": ["string", "null"]},
                    },
                }
            }
        },
    }
