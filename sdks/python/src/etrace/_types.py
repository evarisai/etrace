"""
AUTO-GENERATED from trace-schema.json. Do not edit by hand.
Run: python codegen.py --python
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TraceKind(str, Enum):
    WORKFLOW = "workflow"
    AGENT = "agent"
    STEP = "step"
    LLM = "llm"
    TOOL = "tool"
    HTTP = "http"
    RETRIEVAL = "retrieval"
    RERANKER = "reranker"
    EMBEDDING = "embedding"
    SANDBOX = "sandbox"
    HANDOFF = "handoff"
    APPROVAL = "approval"
    GUARDRAIL = "guardrail"
    EVAL = "eval"
    SCORER = "scorer"
    CUSTOM = "custom"


class TraceStatus(str, Enum):
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


class TraceLevel(str, Enum):
    DEBUG = "debug"
    DEFAULT = "default"
    WARNING = "warning"
    ERROR = "error"


class ScoreDataType(str, Enum):
    NUMERIC = "numeric"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"


class ScoreSource(str, Enum):
    ANNOTATION = "annotation"
    API = "api"
    EVAL = "eval"


class UsageUnit(str, Enum):
    TOKENS = "tokens"
    CHARACTERS = "characters"
    IMAGES = "images"
    STEPS = "steps"


@dataclass
class TraceError:
    message: str
    type: str | None = None
    stack: str | None = None


@dataclass
class TraceEvent:
    name: str
    timestamp: str
    attributes: dict[str, Any] | None = None


@dataclass
class TraceLink:
    trace_id: str
    span_id: str
    attributes: dict[str, Any] | None = None


@dataclass
class Usage:
    """Token usage with split cost tracking."""

    input: int = 0
    output: int = 0
    total: int = 0
    unit: UsageUnit = UsageUnit.TOKENS
    input_cost: float = 0
    output_cost: float = 0
    total_cost: float = 0
    calculated_input_cost: float | None = None
    calculated_output_cost: float | None = None
    calculated_total_cost: float | None = None
    cached_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass
class StreamingMetrics:
    """Streaming LLM performance metrics."""

    completion_start_time: str | None = None
    tokens_per_second: float | None = None
    time_to_first_token_ms: float | None = None


@dataclass
class Span:
    """A single traced operation. The ONE primitive. Everything is a span with a kind."""

    trace_id: str
    span_id: str
    name: str
    kind: TraceKind
    started_at: str
    parent_span_id: str | None = None
    status: TraceStatus = TraceStatus.UNSET
    level: TraceLevel = TraceLevel.DEFAULT
    ended_at: str | None = None
    duration_ns: int | None = None
    input: Any | None = None
    output: Any | None = None
    error: TraceError | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[TraceEvent] = field(default_factory=list)
    links: list[TraceLink] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    model: str | None = None
    provider: str | None = None
    model_parameters: dict[str, Any] | None = None
    usage: Usage | None = None
    streaming: StreamingMetrics | None = None
    prompt_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    version: str | None = None
    release: str | None = None
    environment: str | None = None

    def calc_cost(self) -> None:
        """Calculate cost for this span's usage and assign it back."""
        if self.usage and self.model:
            # Late import to avoid circular dependency
            from . import calculate_usage_cost

            self.usage = calculate_usage_cost(self.usage, model=self.model)


@dataclass
class SpanOptions:
    """Options when creating a span."""

    kind: TraceKind = TraceKind.CUSTOM
    input: Any | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = None
    level: TraceLevel | None = None
    model: str | None = None
    provider: str | None = None
    model_parameters: dict[str, Any] | None = None
    prompt_id: str | None = None
    version: str | None = None
    release: str | None = None
    capture_input: bool = True
    capture_output: bool = True


@dataclass
class ContextOptions:
    """Context that propagates across all spans in a call chain."""

    user_id: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    eval_run_id: str | None = None
    tags: list[str] | None = None
    version: str | None = None
    release: str | None = None


@dataclass
class ScoreOptions:
    name: str
    trace_id: str | None = None
    span_id: str | None = None
    value: Any | None = None
    data_type: ScoreDataType | None = None
    source: ScoreSource | None = None
    comment: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class InitOptions:
    """Options for initializing the tracing library."""

    api_key: str | None = None
    project_id: str | None = None
    endpoint: str = "https://runtime.evaris.ai/v1/traces"
    service_name: str = "evaris-app"
    environment: str = "production"
    auto_instrument: dict[str, Any] = field(default_factory=dict)
    debug: bool = False
    version: str | None = None
    release: str | None = None
