"""Validate render.yaml against a pinned copy of Render's official JSON Schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Render schema must be a JSON object")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Render Blueprint must be a YAML mapping")
    return value


def validate_blueprint(blueprint_path: Path, schema_path: Path) -> None:
    schema = _load_json(schema_path)
    blueprint = _load_yaml(blueprint_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(blueprint),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return
    messages = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        messages.append(f"{location}: {error.message}")
    raise ValueError("Render Blueprint validation failed:\n" + "\n".join(messages))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("schema", type=Path)
    args = parser.parse_args()
    validate_blueprint(args.blueprint, args.schema)
    print(f"Validated {args.blueprint} against {args.schema}")


if __name__ == "__main__":
    main()
