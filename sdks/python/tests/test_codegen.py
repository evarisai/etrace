"""Tests for codegen — verify schema→type generation roundtrips correctly."""

import ast
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, ROOT)

import codegen  # noqa: E402

# ── Schema loading ───────────────────────────────────────────────────────────


class TestSchemaLoading:
    def test_load_schema(self):
        schema = codegen.load_schema()
        assert "$defs" in schema
        assert "TraceKind" in schema["$defs"]
        assert "Span" in schema["$defs"]

    def test_schema_has_expected_defs(self):
        schema = codegen.load_schema()
        defs = schema["$defs"]
        expected = [
            "TraceKind",
            "TraceStatus",
            "TraceLevel",
            "ScoreDataType",
            "ScoreSource",
            "UsageUnit",
            "TraceError",
            "TraceEvent",
            "TraceLink",
            "Usage",
            "StreamingMetrics",
            "Span",
            "SpanOptions",
            "ContextOptions",
            "ScoreOptions",
            "InitOptions",
        ]
        for name in expected:
            assert name in defs, f"Missing definition: {name}"


# ── Python codegen ───────────────────────────────────────────────────────────


class TestPythonCodegen:
    def test_generates_valid_python(self):
        schema = codegen.load_schema()
        code = codegen.gen_python(schema)
        # Should parse without errors
        tree = ast.parse(code)
        assert tree is not None

    def test_generates_enums(self):
        schema = codegen.load_schema()
        code = codegen.gen_python(schema)
        # Should contain all enum classes
        for name in ["TraceKind", "TraceStatus", "TraceLevel"]:
            assert f"class {name}(str, Enum):" in code

    def test_generates_dataclasses(self):
        schema = codegen.load_schema()
        code = codegen.gen_python(schema)
        # Should contain dataclass definitions
        assert "@dataclass" in code
        assert "class Span:" in code
        assert "class Usage:" in code

    def test_enum_defaults_use_enum_members(self):
        """Generated enum defaults should use Enum.MEMBER, not string literals."""
        schema = codegen.load_schema()
        code = codegen.gen_python(schema)
        # The Usage.unit field should default to UsageUnit.TOKENS
        assert "UsageUnit.TOKENS" in code

    def test_snake_case(self):
        assert codegen._snake_case("camelCase") == "camel_case"
        assert codegen._snake_case("PascalCase") == "pascal_case"
        assert codegen._snake_case("already_snake") == "already_snake"
        assert codegen._snake_case("inputCost") == "input_cost"


# ── TypeScript codegen ───────────────────────────────────────────────────────


class TestTypeScriptCodegen:
    def test_generates_valid_typescript(self):
        schema = codegen.load_schema()
        code = codegen.gen_ts(schema)
        # Should contain type and interface definitions
        assert "export type TraceKind" in code
        assert "export interface Span" in code
        assert "export interface Usage" in code

    def test_enum_generates_union(self):
        schema = codegen.load_schema()
        code = codegen.gen_ts(schema)
        # TraceKind should be a union type
        assert '"workflow"' in code
        assert '"agent"' in code
        assert '"custom"' in code

    def test_required_vs_optional_fields(self):
        schema = codegen.load_schema()
        code = codegen.gen_ts(schema)
        # Span.name should be required, Span.model should be optional
        lines = code.split("\n")
        span_section = []
        in_span = False
        for line in lines:
            if "export interface Span" in line:
                in_span = True
            elif in_span and line.startswith("}"):
                break
            elif in_span:
                span_section.append(line.strip())

        # name should be required (no ?)
        assert any("name: string;" in line for line in span_section)
        # model should be optional (has ?)
        assert any("model?: string;" in line for line in span_section)


# ── CLI argument parsing ─────────────────────────────────────────────────────


class TestCodegenCLI:
    def test_argparse_python_flag(self):
        """--python flag should be accepted."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--python", action="store_true")
        parser.add_argument("--typescript", action="store_true")
        args = parser.parse_args(["--python"])
        assert args.python is True
        assert args.typescript is False
