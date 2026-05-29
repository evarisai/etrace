"""Deep research agent example — idiomatic etrace usage.

Key principles:
- etrace.init() auto-detects LangChain, disables LLM auto-instrument
- @etrace.agent / @etrace.tool decorators auto-capture input/output
- etrace.langchain_handler() creates a fresh handler per invocation
  that inherits the active trace context
- No manual trace(), no manual flush(), no auto_instrument config
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Annotated, Literal

from dotenv import load_dotenv

load_dotenv()

import etrace
import httpx
from deepagents import create_deep_agent
from etrace.otel import OtelExporter
from langchain_core.messages import HumanMessage
from langchain_core.tools import InjectedToolArg, tool
from langchain_openai import ChatOpenAI
from markdownify import markdownify
from tavily import TavilyClient


# ── Environment ───────────────────────────────────────────────────────────────

ZAI_OPENAI_BASE_URL = "https://api.z.ai/api/paas/v4/"
DEFAULT_STUDIO_OTLP_ENDPOINT = "http://localhost:3001/v1/traces"


def configure_environment() -> None:
    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("ZAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["ZAI_API_KEY"]

    os.environ.setdefault("OPENAI_BASE_URL", ZAI_OPENAI_BASE_URL)
    os.environ.setdefault(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        os.environ.get("ETRACE_STUDIO_OTLP_ENDPOINT", DEFAULT_STUDIO_OTLP_ENDPOINT),
    )
    os.environ.setdefault("OTEL_SERVICE_NAME", "etrace-deep-research-agent")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# ── Tracing setup ─────────────────────────────────────────────────────────────
# One call. Auto-detects LangChain → disables LLM auto-instrument internally.
# ──────────────────────────────────────────────────────────────────────────────

def init_tracing() -> None:
    etrace.init(
        service_name="etrace-deep-research-agent",
        environment=os.environ.get("ETRACE_ENVIRONMENT", "local"),
        exporters=[OtelExporter()],
        calculate_costs=True,
    )


# ── Tools ─────────────────────────────────────────────────────────────────────
# Helper functions use @etrace.tool for auto-capture.
# LangChain tools use @tool (LangChain's decorator) — the callback handler
# traces them automatically. Nested @etrace.tool calls inside LangChain tools
# inherit the handler's span context via _current_span bridging.
# ──────────────────────────────────────────────────────────────────────────────

tavily_client: TavilyClient | None = None


def get_tavily_client() -> TavilyClient:
    global tavily_client
    if tavily_client is None:
        tavily_client = TavilyClient(api_key=require_env("TAVILY_API_KEY"))
    return tavily_client


@etrace.tool
def fetch_webpage_content(url: str, timeout: float = 10.0) -> str:
    """Fetch webpage and convert HTML to markdown."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
    }
    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return markdownify(response.text)
    except Exception as exc:
        return f"Error fetching content from {url}: {exc!s}"


@tool(parse_docstring=True)
def tavily_search(
    query: str,
    max_results: Annotated[int, InjectedToolArg] = 1,
    topic: Annotated[
        Literal["general", "news", "finance"],
        InjectedToolArg,
    ] = "general",
) -> str:
    """Search the web for information on a given query.

    Uses Tavily to discover relevant URLs, then fetches and returns full webpage
    content as markdown.

    Args:
        query: Search query to execute.
        max_results: Maximum number of results to return.
        topic: Topic filter: general, news, or finance.
    """
    search_results = get_tavily_client().search(
        query,
        max_results=max_results,
        topic=topic,
    )
    result_texts = []
    for result in search_results.get("results", []):
        url = result["url"]
        title = result["title"]
        content = fetch_webpage_content(url)
        result_texts.append(f"## {title}\n**URL:** {url}\n\n{content}\n---")

    return f"Found {len(result_texts)} result(s) for '{query}':\n\n" + "\n".join(
        result_texts
    )


@tool(parse_docstring=True)
def think_tool(reflection: str) -> str:
    """Record strategic reflection on research progress.

    Args:
        reflection: Analysis of current findings, gaps, quality, and next steps.
    """
    return f"Reflection recorded: {reflection}"


# ── Agent configuration ──────────────────────────────────────────────────────

RESEARCH_WORKFLOW_INSTRUCTIONS = """# Research Workflow

Follow this workflow for all research requests:
1. Plan with write_todos.
2. Save the user's research question to `/research_request.md`.
3. Delegate research tasks to sub-agents using the task() tool.
4. Synthesize findings and consolidate citations.
5. Write a final report to `/final_report.md`.
6. Verify the final report addresses the original request.

## Report Writing Guidelines
- Use clear section headings.
- Write in paragraph form by default.
- Avoid self-referential language.
- Cite sources inline with [1], [2], [3].
- End with a Sources section listing each numbered source.
"""

RESEARCHER_INSTRUCTIONS = """You are a research assistant conducting research on the user's input topic.
For context, today's date is {date}.

Use tavily_search to find sources and think_tool after each search to assess progress.

Tool budgets:
- Simple queries: 2-3 searches maximum.
- Complex queries: up to 5 searches maximum.
- Stop when you have enough evidence to answer comprehensively.

Return structured findings with inline citations and a Sources section.
"""

SUBAGENT_DELEGATION_INSTRUCTIONS = """# Sub-Agent Research Coordination

Default to one comprehensive sub-agent for most research tasks.
Use multiple sub-agents only for explicit comparisons or clearly independent aspects.

Limits:
- Use at most {max_concurrent_research_units} parallel sub-agents per iteration.
- Stop after {max_researcher_iterations} delegation rounds.
"""


def build_agent():
    current_date = datetime.now().strftime("%Y-%m-%d")
    max_concurrent_research_units = 3
    max_researcher_iterations = 3

    instructions = (
        RESEARCH_WORKFLOW_INSTRUCTIONS
        + "\n\n"
        + "=" * 80
        + "\n\n"
        + SUBAGENT_DELEGATION_INSTRUCTIONS.format(
            max_concurrent_research_units=max_concurrent_research_units,
            max_researcher_iterations=max_researcher_iterations,
        )
    )

    research_sub_agent = {
        "name": "research-agent",
        "description": "Delegate research to the sub-agent. Give one topic at a time.",
        "system_prompt": RESEARCHER_INSTRUCTIONS.format(date=current_date),
        "tools": [tavily_search, think_tool],
    }

    model_name = os.environ.get("OPENAI_MODEL", "glm-5.1")
    model = ChatOpenAI(
        model=model_name,
        api_key=require_env("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_BASE_URL", ZAI_OPENAI_BASE_URL),
        temperature=0.0,
    )

    agent = create_deep_agent(
        model=model,
        tools=[tavily_search, think_tool],
        system_prompt=instructions,
        subagents=[research_sub_agent],
    )
    return model_name, agent


# ── Main: the ideal API ──────────────────────────────────────────────────────
# @etrace.agent auto-captures input (query) and output (answer).
# etrace.langchain_handler() creates a handler inheriting the active trace.
# No manual trace(), flush(), or auto_instrument config.
# ──────────────────────────────────────────────────────────────────────────────

@etrace.agent
def deep_research(query: str) -> str:
    """Run the deep research agent on a query."""
    _, agent = build_agent()
    result = agent.invoke(
        {"messages": [HumanMessage(content=query)]},
        config={"callbacks": [etrace.langchain_handler()]},
    )

    # Extract the final answer
    messages = result.get("messages", [])
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if content:
            return content
    return "No answer found."


def main() -> None:
    configure_environment()
    init_tracing()

    question = (
        " ".join(sys.argv[1:])
        or "What are the main differences between RAG and fine-tuning for LLM applications?"
    )

    answer = deep_research(question)
    print(answer)


if __name__ == "__main__":
    main()
