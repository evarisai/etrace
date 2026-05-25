#!/usr/bin/env python3
"""
Codegen: trace-schema.json → Python types + TypeScript types.

Usage:
  python codegen.py              # generates both
  python codegen.py --python     # Python only
  python codegen.py --typescript # TypeScript only
"""
import argparse
import json
import os
import re
import sys

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema", "trace-schema.json")
PYTHON_OUT = os.path.join(os.path.dirname(__file__), "sdks", "python", "src", "etrace", "_types.py")
TS_OUT = os.path.join(os.path.dirname(__file__), "sdks", "typescript", "src", "types.ts")


def load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _snake_case(name: str) -> str:
    """Convert camelCase or PascalCase to snake_case."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


# ─── Python Codegen ──────────────────────────────────────────────────────────

def json_type_to_python(schema: dict) -> str:
    """Map JSON Schema type to Python type annotation."""
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]

    type_map = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "list",
        "object": "dict[str, Any]",
    }
    base = type_map.get(schema.get("type", "any"), "Any")

    if schema.get("type") == "array" and "items" in schema:
        item_type = json_type_to_python(schema["items"])
        return f"list[{item_type}]"

    return base


def gen_python_enum(name: str, schema: dict) -> str:
    """Generate a Python StrEnum."""
    values = schema.get("enum", [])
    lines = [f"class {name}(str, Enum):"]
    for v in values:
        member = v.upper().replace("-", "_").replace(".", "_")
        lines.append(f'    {member} = "{v}"')
    lines.append("")
    return "\n".join(lines)


def gen_python_dataclass(name: str, schema: dict) -> str:
    """Generate a Python dataclass from a JSON Schema object."""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    lines = ["@dataclass"]

    desc = schema.get("description", "")
    if desc:
        lines.append(f'class {name}:\n    """{desc}"""')
    else:
        lines.append(f"class {name}:")

    if not props:
        lines.append("    pass")
        lines.append("")
        return "\n".join(lines)

    # Collect fields, then sort: required-without-default first, then optional
    fields = []
    for prop_name, prop_schema in props.items():
        py_name = _snake_case(prop_name)
        py_type = json_type_to_python(prop_schema)
        is_required = prop_name in required
        has_default = "default" in prop_schema
        fields.append((py_name, py_type, is_required, has_default, prop_schema))

    fields.sort(key=lambda f: (0 if f[2] and not f[3] else 1))

    for py_name, py_type, is_required, has_default, prop_schema in fields:
        if not is_required or has_default:
            default = prop_schema.get("default")
            if default is not None:
                # Check if the type is an enum reference — use enum member
                ref_name = prop_schema.get("$ref", "").split("/")[-1]
                if ref_name and isinstance(default, str):
                    member = default.upper().replace("-", "_").replace(".", "_")
                    default_repr = f"{ref_name}.{member}"
                elif isinstance(default, str):
                    default_repr = f'"{default}"'
                elif isinstance(default, list):
                    default_repr = "field(default_factory=list)"
                elif isinstance(default, dict):
                    default_repr = "field(default_factory=dict)"
                else:
                    default_repr = str(default)
                lines.append(f"    {py_name}: {py_type} = {default_repr}")
            else:
                lines.append(f"    {py_name}: {py_type} | None = None")
        else:
            lines.append(f"    {py_name}: {py_type}")

    lines.append("")
    return "\n".join(lines)


def gen_python(schema: dict) -> str:
    defs = schema.get("$defs", {})

    lines = [
        '"""',
        "AUTO-GENERATED from trace-schema.json. Do not edit by hand.",
        "Run: python codegen.py --python",
        '"""',
        "",
        "from __future__ import annotations",
        "from dataclasses import dataclass, field",
        "from enum import Enum",
        "from typing import Any",
        "",
        "",
    ]

    # First: enums
    for name, defn in defs.items():
        if "enum" in defn:
            lines.append(gen_python_enum(name, defn))

    # Then: dataclasses
    for name, defn in defs.items():
        if defn.get("type") == "object" and "enum" not in defn:
            lines.append(gen_python_dataclass(name, defn))

    return "\n".join(lines)


# ─── TypeScript Codegen ──────────────────────────────────────────────────────

def json_type_to_ts(schema: dict) -> str:
    """Map JSON Schema type to TypeScript type."""
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]

    schema_type = schema.get("type")

    if schema_type == "string" and "enum" in schema:
        return " | ".join(f'"{v}"' for v in schema["enum"])

    type_map = {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
    }

    if schema_type == "array" and "items" in schema:
        item_type = json_type_to_ts(schema["items"])
        return f"{item_type}[]"

    if schema_type == "object":
        return "Record<string, unknown>"

    return type_map.get(schema_type, "unknown")


def gen_ts_type(name: str, schema: dict) -> str:
    """Generate a TypeScript type alias (for enums) or interface (for objects)."""
    if "enum" in schema:
        union = " | ".join(f'"{v}"' for v in schema["enum"])
        return f"export type {name} = {union};\n"

    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    desc = schema.get("description", "")
    lines = []
    if desc:
        lines.append(f"/** {desc} */")

    lines.append(f"export interface {name} {{")

    for prop_name, prop_schema in props.items():
        ts_type = json_type_to_ts(prop_schema)
        is_required = prop_name in required
        has_default = "default" in prop_schema

        if is_required and not has_default:
            lines.append(f"  {prop_name}: {ts_type};")
        else:
            lines.append(f"  {prop_name}?: {ts_type};")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def gen_ts(schema: dict) -> str:
    defs = schema.get("$defs", {})

    lines = [
        "/**",
        " * AUTO-GENERATED from trace-schema.json. Do not edit by hand.",
        " * Run: python codegen.py --typescript",
        " */",
        "",
    ]

    for name, defn in defs.items():
        lines.append(gen_ts_type(name, defn))

    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate types from trace-schema.json")
    parser.add_argument("--python", action="store_true", help="Generate Python types only")
    parser.add_argument("--typescript", action="store_true", help="Generate TypeScript types only")
    args = parser.parse_args()

    generate_python = args.python or (not args.typescript)
    generate_typescript = args.typescript or (not args.python)

    schema = load_schema()

    if generate_python:
        os.makedirs(os.path.dirname(PYTHON_OUT), exist_ok=True)
        code = gen_python(schema)
        with open(PYTHON_OUT, "w") as f:
            f.write(code)
        print(f"✅ Python types → {PYTHON_OUT}")

    if generate_typescript:
        os.makedirs(os.path.dirname(TS_OUT), exist_ok=True)
        code = gen_ts(schema)
        with open(TS_OUT, "w") as f:
            f.write(code)
        print(f"✅ TypeScript types → {TS_OUT}")


if __name__ == "__main__":
    main()
