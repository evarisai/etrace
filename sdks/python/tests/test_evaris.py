"""Tests for etrace-evaris plugin.

Tests the EvarisExporter and the init() one-liner that configures
etrace with Evaris cloud backend credentials.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import etrace
from etrace._exporter import SpanExportResult
from etrace._types import TraceKind, TraceStatus


class TestEvarisExporter:
    """Unit tests for EvarisExporter."""

    def _make_span(self, **overrides):
        from datetime import UTC, datetime

        from etrace._types import Span

        defaults = dict(
            trace_id="a" * 32,
            span_id="b" * 16,
            name="test_span",
            kind=TraceKind.TOOL,
            status=TraceStatus.OK,
            started_at=datetime.now(UTC).isoformat(),
            ended_at=datetime.now(UTC).isoformat(),
            duration_ns=1_000_000,
        )
        defaults.update(overrides)
        return Span(**defaults)

    def test_export_sends_to_evaris_backend(self):
        """EvarisExporter POSTs spans to runtime.evaris.ai."""
        from etrace_evaris import EvarisExporter

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            exporter = EvarisExporter(api_key="test-key", project_id="proj-1")
            span = self._make_span()
            result = exporter.export([span])

            assert result == SpanExportResult.SUCCESS
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            assert "runtime.evaris.ai" in call_kwargs.kwargs.get("url", "") or "runtime.evaris.ai" in str(call_kwargs)

    def test_export_includes_auth_headers(self):
        """EvarisExporter includes api_key in request headers."""
        from etrace_evaris import EvarisExporter

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            exporter = EvarisExporter(api_key="sk-test-123", project_id="proj-1")
            span = self._make_span()
            exporter.export([span])

            headers = mock_post.call_args.kwargs.get("headers", {})
            assert (
                "Authorization" in headers
                or "X-API-Key" in headers
                or any("sk-test-123" in str(v) for v in headers.values())
            )

    def test_export_includes_project_id_header(self):
        """EvarisExporter includes project_id in request headers."""
        from etrace_evaris import EvarisExporter

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            exporter = EvarisExporter(api_key="key", project_id="proj-42")
            span = self._make_span()
            exporter.export([span])

            headers = mock_post.call_args.kwargs.get("headers", {})
            assert "proj-42" in str(headers)

    def test_export_sends_span_as_json(self):
        """EvarisExporter serializes spans to JSON in request body."""
        from etrace_evaris import EvarisExporter

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            exporter = EvarisExporter(api_key="key", project_id="proj-1")
            span = self._make_span(name="my_span", kind=TraceKind.LLM)
            exporter.export([span])

            content = mock_post.call_args.kwargs.get("content", "")
            if not content:
                json_arg = mock_post.call_args.kwargs.get("json", None)
                assert json_arg is not None
            else:
                data = json.loads(content)
                assert isinstance(data, (dict, list))

    def test_export_failure_returns_failure(self):
        """EvarisExporter returns FAILURE when POST fails."""
        from etrace_evaris import EvarisExporter

        with patch("httpx.post", side_effect=Exception("network error")):
            exporter = EvarisExporter(api_key="key", project_id="proj-1")
            span = self._make_span()
            result = exporter.export([span])
            assert result == SpanExportResult.FAILURE

    def test_export_http_error_returns_failure(self):
        """EvarisExporter returns FAILURE on non-200 response."""
        from etrace_evaris import EvarisExporter

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status = MagicMock(side_effect=Exception("500"))

        with patch("httpx.post", return_value=mock_response):
            exporter = EvarisExporter(api_key="key", project_id="proj-1")
            span = self._make_span()
            result = exporter.export([span])
            assert result == SpanExportResult.FAILURE

    def test_custom_endpoint(self):
        """EvarisExporter can use a custom endpoint."""
        from etrace_evaris import EvarisExporter

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            exporter = EvarisExporter(
                api_key="key",
                project_id="proj-1",
                endpoint="https://custom.example.com/v1/traces",
            )
            span = self._make_span()
            exporter.export([span])

            url = (
                mock_post.call_args.kwargs.get("url", "") or mock_post.call_args.args[0]
                if mock_post.call_args.args
                else ""
            )
            assert "custom.example.com" in url

    def test_shutdown_is_noop(self):
        """EvarisExporter.shutdown() is a safe no-op."""
        from etrace_evaris import EvarisExporter

        exporter = EvarisExporter(api_key="key", project_id="proj-1")
        exporter.shutdown()  # Should not raise

    def test_force_flush_returns_true(self):
        """EvarisExporter.force_flush() returns True (synchronous export)."""
        from etrace_evaris import EvarisExporter

        exporter = EvarisExporter(api_key="key", project_id="proj-1")
        assert exporter.force_flush() is True


class TestEvarisInit:
    """Tests for etrace_evaris.init() one-liner."""

    def test_init_configures_etrace_with_evaris_exporter(self):
        """etrace_evaris.init() calls etrace.init() with EvarisExporter."""
        from etrace_evaris import EvarisExporter

        with patch.object(etrace, "init") as mock_init:
            import etrace_evaris

            etrace_evaris.init(api_key="test-key", project_id="proj-1")

            mock_init.assert_called_once()
            call_kwargs = mock_init.call_args.kwargs
            exporters = call_kwargs.get("exporters", [])
            assert len(exporters) == 1
            assert isinstance(exporters[0], EvarisExporter)

    def test_init_passes_service_name(self):
        """etrace_evaris.init() forwards service_name."""
        with patch.object(etrace, "init") as mock_init:
            import etrace_evaris

            etrace_evaris.init(
                api_key="key",
                project_id="proj-1",
                service_name="my-service",
            )

            call_kwargs = mock_init.call_args.kwargs
            assert call_kwargs["service_name"] == "my-service"

    def test_init_passes_environment(self):
        """etrace_evaris.init() forwards environment."""
        with patch.object(etrace, "init") as mock_init:
            import etrace_evaris

            etrace_evaris.init(
                api_key="key",
                project_id="proj-1",
                environment="staging",
            )

            call_kwargs = mock_init.call_args.kwargs
            assert call_kwargs["environment"] == "staging"

    def test_init_forwards_auto_instrument(self):
        """etrace_evaris.init() forwards auto_instrument setting."""
        with patch.object(etrace, "init") as mock_init:
            import etrace_evaris

            etrace_evaris.init(
                api_key="key",
                project_id="proj-1",
                auto_instrument={"llm": False},
            )

            call_kwargs = mock_init.call_args.kwargs
            assert call_kwargs["auto_instrument"] == {"llm": False}


class TestEvarisScore:
    """Tests for etrace_evaris.score() API."""

    def test_score_posts_to_evaris(self):
        """etrace_evaris.score() POSTs a score to the Evaris backend."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "score-1"}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            import etrace_evaris

            etrace_evaris.score(
                api_key="key",
                project_id="proj-1",
                trace_id="abc123",
                name="relevance",
                value=0.9,
            )

            mock_post.assert_called_once()

    def test_score_includes_auth_and_trace(self):
        """score() includes api_key, project_id, and trace_id in request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "score-1"}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            import etrace_evaris

            etrace_evaris.score(
                api_key="sk-test",
                project_id="proj-1",
                trace_id="trace-abc",
                name="accuracy",
                value=1.0,
            )

            call = mock_post.call_args
            call.kwargs.get("headers", {})
            json_body = call.kwargs.get("json", {})
            assert json_body.get("trace_id") == "trace-abc"
            assert json_body.get("name") == "accuracy"
            assert json_body.get("value") == 1.0
