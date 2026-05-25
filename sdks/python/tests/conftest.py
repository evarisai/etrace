"""Shared test fixtures for etrace tests."""

from __future__ import annotations

import contextlib

import pytest

import etrace
from etrace._exporter import InMemoryExporter

# ── State reset fixture ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_etrace_state():
    """Reset all global state before each test."""
    with contextlib.suppress(Exception):
        etrace.shutdown()
    etrace._initialized = False
    etrace._processor = None
    etrace._exporters = []
    etrace._calc_costs = True
    etrace._current_span.set(None)
    etrace._context_opts.set(None)
    yield
    with contextlib.suppress(Exception):
        etrace.shutdown()


# ── Exporter fixture ─────────────────────────────────────────────────────────


@pytest.fixture
def exporter():
    """Fresh InMemoryExporter per test."""
    exp = InMemoryExporter()
    yield exp


# ── Initialized client with in-memory export ────────────────────────────────


@pytest.fixture
def evaris_client(exporter: InMemoryExporter):
    """etrace initialized with InMemoryExporter. No network calls."""
    etrace.init(exporters=[exporter], auto_instrument={"llm": False})
    yield etrace
    etrace.shutdown()


# ── Span lookup helpers ─────────────────────────────────────────────────────


@pytest.fixture
def get_spans(exporter: InMemoryExporter):
    """Helper to find finished spans by name."""

    def _get_spans(name: str) -> list:
        return [s for s in exporter.get_finished_spans() if s.name == name]

    return _get_spans


@pytest.fixture
def get_span(exporter: InMemoryExporter):
    """Helper to find exactly one finished span by name."""

    def _get_span(name: str) -> etrace._types.Span:
        matches = [s for s in exporter.get_finished_spans() if s.name == name]
        assert matches, f"Span {name!r} not found"
        assert len(matches) == 1, f"Multiple spans named {name!r}"
        return matches[0]

    return _get_span


@pytest.fixture
def assert_span_hierarchy(exporter: InMemoryExporter):
    """Helper to verify parent-child span relationships."""

    def _assert(parent_name: str, child_name: str) -> None:
        spans = exporter.get_finished_spans()
        parent = next(s for s in spans if s.name == parent_name)
        child = next(s for s in spans if s.name == child_name)
        assert child.parent_span_id is not None, f"Child span {child_name!r} has no parent"
        assert child.parent_span_id == parent.span_id, (
            f"Expected {child_name!r}.parent_span_id == {parent_name!r}.span_id, "
            f"got {child.parent_span_id} != {parent.span_id}"
        )
        assert child.trace_id == parent.trace_id, f"Expected same trace_id, got {child.trace_id} != {parent.trace_id}"

    return _assert
