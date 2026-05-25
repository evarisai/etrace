#!/usr/bin/env python3
"""
Sync model pricing from models.dev → static catalogs for Python and TypeScript.

Usage:
    python scripts/sync_pricing.py [--source /path/to/models.dev]

Reads providers/*/models/*.toml, generates:
    - sdks/python/src/etrace/_pricing.py   (Python dict)
    - sdks/typescript/src/pricing.ts              (TypeScript const)
"""
from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

TRACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path("/tmp/models.dev")

# Per 1M tokens → per-token multiplier
PER_M = 1 / 1_000_000

# ── Shared constants for normalize/calculate logic ────────────────────────────
# These are the single source of truth for the normalization prefixes and
# cost calculation formula. Both Python and TypeScript generators reference
# these to keep the generated code in sync.

NORMALIZE_PREFIXES = ("openrouter/", "azure/", "bedrock/")


def load_toml_pricing(source: Path) -> dict[str, dict[str, float]]:
    """Load pricing from models.dev TOML files. Returns {model_id: {input, output, ...}} per-token USD."""
    providers_dir = source / "providers"
    if not providers_dir.is_dir():
        print(f"ERROR: {providers_dir} not found. Clone models.dev first.", file=sys.stderr)
        sys.exit(1)

    catalog: dict[str, dict[str, float]] = {}

    for provider_dir in sorted(providers_dir.iterdir()):
        if not provider_dir.is_dir():
            continue
        models_dir = provider_dir / "models"
        if not models_dir.is_dir():
            continue
        provider_id = provider_dir.name

        for model_file in sorted(models_dir.glob("**/*.toml")):
            model_id = model_file.stem
            # Handle nested dirs like bedrock/anthropic.claude-3...
            relative = model_file.relative_to(models_dir)
            model_id = str(relative.with_suffix(""))
            full_id = f"{provider_id}/{model_id}"

            try:
                with open(model_file, "rb") as f:
                    data = tomllib.load(f)
            except Exception as exc:
                print(f"WARNING: failed to parse {model_file}: {exc}", file=sys.stderr)
                continue

            cost = data.get("cost")
            if not cost:
                continue

            entry: dict[str, float] = {}
            for key in ("input", "output", "cache_read", "cache_write", "reasoning"):
                val = cost.get(key)
                if val is not None:
                    # TOML values are per 1M tokens → convert to per-token
                    entry[key] = float(val) * PER_M

            if entry.get("input") or entry.get("output"):
                catalog[full_id] = entry

            # Also register under the model file name (without provider prefix)
            # for easy lookup like "gpt-4o" → openai/gpt-4o
            short_id = model_file.stem
            if short_id not in catalog:
                catalog[short_id] = entry

    return catalog


def normalize_model_name(name: str) -> str:
    """Normalize model name for lookup."""
    n = name.strip().lower()
    for prefix in NORMALIZE_PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix):]
    return n


def _load_catalog(source: Path) -> dict[str, dict[str, float]]:
    """Load pricing catalog from TOML or JSON fallback."""
    if source.is_dir():
        return load_toml_pricing(source)

    # Try models.json as fallback
    models_json = source / "models.json"
    if models_json.exists():
        print(f"Using {models_json} (JSON fallback)")
        with open(models_json) as f:
            raw = json.load(f).get("data", [])
        catalog: dict[str, dict[str, float]] = {}
        for m in raw:
            mid = m.get("id", "")
            p = m.get("pricing", {})
            entry = {}
            for key in ("prompt", "completion", "input_cache_read", "input_cache_write", "internal_reasoning"):
                v = p.get(key)
                if v is not None:
                    mapped = {
                        "prompt": "input", "completion": "output",
                        "input_cache_read": "cache_read", "input_cache_write": "cache_write",
                        "internal_reasoning": "reasoning",
                    }[key]
                    entry[mapped] = float(v)
            if entry.get("input") or entry.get("output"):
                catalog[mid] = entry
                short = mid.split("/")[-1]
                if short not in catalog:
                    catalog[short] = entry
        return catalog

    print(f"ERROR: {source} not found. Pass --source /path/to/models.dev", file=sys.stderr)
    sys.exit(1)


# ── Code generation helpers ──────────────────────────────────────────────────

def _format_rate(v: float) -> str:
    return f"{v:.12f}"


def _gen_catalog_entries(catalog: dict[str, dict[str, float]]) -> str:
    """Generate sorted model entries (shared between Python and TS)."""
    lines = []
    for model_id in sorted(catalog):
        rates = catalog[model_id]
        yield model_id, rates


def generate_python(catalog: dict[str, dict[str, float]]) -> str:
    """Generate _pricing.py"""
    lines = [
        '"""',
        "AUTO-GENERATED by scripts/sync_pricing.py from models.dev.",
        "Model pricing catalog — per-token USD rates.",
        "Do not edit by hand. Re-run: python scripts/sync_pricing.py",
        '"""',
        "from __future__ import annotations",
        "",
        "",
        "# {model_id: {input: per_token_usd, output: per_token_usd, ...}}",
        "PRICING: dict[str, dict[str, float]] = {",
    ]
    for model_id, rates in _gen_catalog_entries(catalog):
        rate_str = ", ".join(f'"{k}": {_format_rate(v)}' for k, v in sorted(rates.items()))
        lines.append(f'    "{model_id}": {{{rate_str}}},')
    lines.append("}")
    lines.append("")

    unique = len(set(k.split("/")[-1] for k in catalog))
    lines.append(f"MODEL_COUNT = {unique}")
    lines.append("")

    # Generate normalize_model_name using shared constants
    prefixes_tuple = ", ".join(f"'{p}'" for p in NORMALIZE_PREFIXES)
    lines.append("")
    lines.append("def normalize_model_name(name: str) -> str:")
    lines.append('    """Normalize model name for pricing lookup."""')
    lines.append("    n = name.strip().lower()")
    lines.append(f"    for prefix in ({prefixes_tuple},):")
    lines.append("        if n.startswith(prefix):")
    lines.append("            n = n[len(prefix):]")
    lines.append("    return n")
    lines.append("")
    lines.append("")

    # Generate calculate_cost using the standard formula
    lines.append("def calculate_cost(")
    lines.append("    model: str,")
    lines.append("    input_tokens: int,")
    lines.append("    output_tokens: int,")
    lines.append("    cached_tokens: int = 0,")
    lines.append("    reasoning_tokens: int = 0,")
    lines.append(") -> dict[str, float]:")
    lines.append('    """Calculate USD cost for a model call based on token usage."""')
    lines.append("    normalized = normalize_model_name(model)")
    lines.append("    rates = PRICING.get(model) or PRICING.get(normalized) or PRICING.get(normalized.lower())")
    lines.append("    if not rates:")
    lines.append("        return {}")
    lines.append("    cacheable_input = max(0, input_tokens - cached_tokens)")
    lines.append("    input_cost = cacheable_input * rates.get('input', 0)")
    lines.append("    output_cost = output_tokens * rates.get('output', 0)")
    lines.append("    cache_read_cost = cached_tokens * rates.get('cache_read', 0)")
    lines.append("    reasoning_cost = reasoning_tokens * rates.get('reasoning', 0)")
    lines.append("    total = input_cost + output_cost + cache_read_cost + reasoning_cost")
    lines.append("    return {")
    lines.append('        "input_cost": round(input_cost + cache_read_cost, 8),')
    lines.append('        "output_cost": round(output_cost + reasoning_cost, 8),')
    lines.append('        "total_cost": round(total, 8),')
    lines.append("    }")
    lines.append("")
    return "\n".join(lines)


def generate_typescript(catalog: dict[str, dict[str, float]]) -> str:
    """Generate pricing.ts"""
    lines = [
        "/**",
        " * AUTO-GENERATED by scripts/sync_pricing.py from models.dev.",
        " * Model pricing catalog — per-token USD rates.",
        " * Do not edit by hand. Re-run: python scripts/sync_pricing.py",
        " */",
        "",
        "export interface ModelPricing {",
        "  input: number;",
        "  output: number;",
        "  cache_read?: number;",
        "  cache_write?: number;",
        "  reasoning?: number;",
        "}",
        "",
        "/** Per-token USD rates keyed by model identifier. */",
        "export const PRICING: Record<string, ModelPricing> = {",
    ]
    for model_id, rates in _gen_catalog_entries(catalog):
        parts = [f"input: {_format_rate(rates.get('input', 0))}"]
        parts.append(f"output: {_format_rate(rates.get('output', 0))}")
        if "cache_read" in rates:
            parts.append(f"cache_read: {_format_rate(rates['cache_read'])}")
        if "cache_write" in rates:
            parts.append(f"cache_write: {_format_rate(rates['cache_write'])}")
        if "reasoning" in rates:
            parts.append(f"reasoning: {_format_rate(rates['reasoning'])}")
        lines.append(f'  "{model_id}": {{ {", ".join(parts)} }},')
    lines.append("};")
    lines.append("")

    # Generate normalizeModelName using shared constants
    prefixes_array = ", ".join(f"'{p}'" for p in NORMALIZE_PREFIXES)
    lines.append("function normalizeModelName(name: string): string {")
    lines.append("  let n = name.trim().toLowerCase();")
    lines.append(f"  for (const prefix of [{prefixes_array}]) {{")
    lines.append("    if (n.startsWith(prefix)) n = n.slice(prefix.length);")
    lines.append("  }")
    lines.append("  return n;")
    lines.append("}")
    lines.append("")

    lines.append("export interface CostBreakdown {")
    lines.append("  inputCost: number;")
    lines.append("  outputCost: number;")
    lines.append("  totalCost: number;")
    lines.append("}")
    lines.append("")

    # Generate calculateCost using the standard formula
    lines.append("export function calculateCost(")
    lines.append("  model: string,")
    lines.append("  inputTokens: number,")
    lines.append("  outputTokens: number,")
    lines.append("  cachedTokens = 0,")
    lines.append("  reasoningTokens = 0,")
    lines.append("): CostBreakdown | null {")
    lines.append("  const normalized = normalizeModelName(model);")
    lines.append("  const rates = PRICING[model] ?? PRICING[normalized] ?? PRICING[normalized.toLowerCase()];")
    lines.append("  if (!rates) return null;")
    lines.append("  const cacheableInput = Math.max(0, inputTokens - cachedTokens);")
    lines.append("  const inputCost = cacheableInput * (rates.input ?? 0);")
    lines.append("  const outputCost = outputTokens * (rates.output ?? 0);")
    lines.append("  const cacheReadCost = cachedTokens * (rates.cache_read ?? 0);")
    lines.append("  const reasoningCost = reasoningTokens * (rates.reasoning ?? 0);")
    lines.append("  const total = inputCost + outputCost + cacheReadCost + reasoningCost;")
    lines.append("  return {")
    lines.append("    inputCost: Number((inputCost + cacheReadCost).toFixed(8)),")
    lines.append("    outputCost: Number((outputCost + reasoningCost).toFixed(8)),")
    lines.append("    totalCost: Number(total.toFixed(8)),")
    lines.append("  };")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Sync pricing from models.dev")
    parser.add_argument("--source", type=str, default=str(DEFAULT_SOURCE),
                        help=f"Path to models.dev clone (default: {DEFAULT_SOURCE})")
    args = parser.parse_args()

    source = Path(args.source)
    catalog = _load_catalog(source)

    unique = len(set(k.split("/")[-1] for k in catalog))
    print(f"Loaded {len(catalog)} entries ({unique} unique models)")

    py_path = TRACE_ROOT / "sdks" / "python" / "src" / "etrace" / "_pricing.py"
    ts_path = TRACE_ROOT / "sdks" / "typescript" / "src" / "pricing.ts"

    py_path.parent.mkdir(parents=True, exist_ok=True)
    ts_path.parent.mkdir(parents=True, exist_ok=True)

    py_path.write_text(generate_python(catalog))
    ts_path.write_text(generate_typescript(catalog))

    print(f"✅ Python pricing → {py_path}")
    print(f"✅ TypeScript pricing → {ts_path}")


if __name__ == "__main__":
    main()
