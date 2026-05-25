"""
Compatibility suite — shared test fixtures and assertion helpers.

Uses etrace's own InMemoryExporter (not OTel's) since the core
no longer depends on OTel. Tests verify span fields directly.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import pytest

import etrace
from etrace._exporter import InMemoryExporter

if TYPE_CHECKING:
    from etrace._types import Span

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_etrace_state():
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


@pytest.fixture
def span_exporter():
    return InMemoryExporter()


@pytest.fixture
def evaris_client(span_exporter):
    etrace.init(exporters=[span_exporter])
    yield etrace
    etrace.shutdown()


# ── Helpers ──────────────────────────────────────────────────────────────────


def get_spans_by_name(spans: list[Span], name: str) -> list[Span]:
    return [s for s in spans if s.name == name]


def get_span_by_name(spans: list[Span], name: str) -> Span:
    matches = get_spans_by_name(spans, name)
    assert matches, f"Span {name!r} not found in {[s.name for s in spans]}"
    assert len(matches) == 1, f"Multiple spans named {name!r}"
    return matches[0]


def assert_parent_child(parent: Span, child: Span) -> None:
    assert child.parent_span_id is not None, f"Child {child.name!r} has no parent"
    assert child.parent_span_id == parent.span_id, (
        f"Expected child.parent_span_id == parent.span_id, got {child.parent_span_id} != {parent.span_id}"
    )
    assert child.trace_id == parent.trace_id, f"Expected same trace_id, got {child.trace_id} != {parent.trace_id}"


def assert_span_has_attribute(span: Span, key: str, value: Any = None) -> None:
    assert key in span.attributes, (
        f"Expected attribute {key!r} on span {span.name!r}, got: {list(span.attributes.keys())}"
    )
    if value is not None:
        actual = span.attributes[key]
        assert actual == value, f"Expected {key!r}={value!r}, got {actual!r}"
