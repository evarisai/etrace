"""Auto-instrumentation registry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .anthropic import AnthropicInstrumentor
from .openai import OpenAIInstrumentor

if TYPE_CHECKING:
    from .base import BaseInstrumentor

logger = logging.getLogger("etrace.instrumentation")

_INSTRUMENTOR_CLASSES: list[type[BaseInstrumentor]] = [
    OpenAIInstrumentor,
    AnthropicInstrumentor,
]

_active: list[BaseInstrumentor] = []


def instrument_all(tracer: Any, calc_costs: bool = True) -> list[str]:
    """Try every registered instrumentor. Returns names of successfully patched providers."""
    global _active

    enabled: list[str] = []

    for cls in _INSTRUMENTOR_CLASSES:
        inst = cls()
        try:
            if inst.instrument(tracer, calc_costs):
                _active.append(inst)
                enabled.append(inst.name)
        except Exception as exc:
            logger.warning("instrumentor %s failed: %s", inst.name, exc)

    if enabled:
        logger.info("auto-instrumentation enabled: %s", ", ".join(enabled))
    else:
        logger.info("no LLM providers found for auto-instrumentation")

    return enabled


def uninstrument_all() -> None:
    for inst in _active:
        inst.uninstrument()
    _active.clear()
