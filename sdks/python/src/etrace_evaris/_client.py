"""Evaris cloud client — init() and score() one-liners."""

from __future__ import annotations

import logging
from typing import Any

import etrace

from ._exporter import DEFAULT_ENDPOINT as _TRACES_ENDPOINT
from ._exporter import EvarisExporter

logger = logging.getLogger("etrace.evaris")

_BASE_URL = _TRACES_ENDPOINT.rsplit("/", 1)[0]  # .../v1
_SCORES_ENDPOINT = f"{_BASE_URL}/scores"


def init(
    *,
    api_key: str,
    project_id: str,
    endpoint: str | None = None,
    service_name: str = "etrace-app",
    environment: str = "production",
    auto_instrument: dict[str, bool] | None = None,
    calculate_costs: bool = True,
    debug: bool = False,
    version: str | None = None,
    release: str | None = None,
) -> None:
    """One-liner to configure etrace with the Evaris cloud backend.

    Args:
        api_key: Evaris API key.
        project_id: Evaris project ID.
        endpoint: Override the default backend URL.
        service_name: Name of your service.
        environment: Deployment environment.
        auto_instrument: Which providers to auto-instrument. Default: {"llm": True}.
        calculate_costs: Auto-calculate costs from pricing catalog.
        debug: Enable debug logging.
    """
    exporter = EvarisExporter(
        api_key=api_key,
        project_id=project_id,
        endpoint=endpoint,
    )

    etrace.init(
        service_name=service_name,
        environment=environment,
        exporters=[exporter],
        auto_instrument=auto_instrument,
        calculate_costs=calculate_costs,
        debug=debug,
        version=version,
        release=release,
    )


def score(
    *,
    api_key: str,
    project_id: str,
    trace_id: str,
    name: str,
    value: Any,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """Submit a score for a trace to the Evaris backend.

    Args:
        api_key: Evaris API key.
        project_id: Evaris project ID.
        trace_id: The trace to score.
        name: Score name (e.g. "relevance", "accuracy").
        value: Score value (numeric, boolean, or categorical).
        endpoint: Override the default scores URL.

    Returns:
        The server response as a dict.
    """
    import httpx

    url = endpoint or _SCORES_ENDPOINT
    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Evaris-Project-ID": project_id,
        "Content-Type": "application/json",
    }
    payload = {
        "trace_id": trace_id,
        "name": name,
        "value": value,
    }

    resp = httpx.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return dict(resp.json())
