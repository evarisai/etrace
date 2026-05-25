"""etrace[otel] — Bridge etrace spans to OpenTelemetry.

Provides OtelExporter that converts etrace Span objects to OTel ReadableSpan
format and delegates to a standard OTel SpanExporter.
"""

from .exporter import OtelExporter

__all__ = ["OtelExporter"]
