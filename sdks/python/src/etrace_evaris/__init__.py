"""etrace-evaris — Evaris cloud backend plugin for etrace.

Usage:
    import etrace_evaris
    etrace_evaris.init(api_key="...", project_id="...")

    # Or use the exporter directly:
    from etrace_evaris import EvarisExporter
    import etrace
    etrace.init(exporters=[EvarisExporter(api_key="...", project_id="...")])
"""

from __future__ import annotations

from ._client import init, score
from ._exporter import DEFAULT_ENDPOINT, EvarisExporter

__all__ = ["DEFAULT_ENDPOINT", "EvarisExporter", "init", "score"]
