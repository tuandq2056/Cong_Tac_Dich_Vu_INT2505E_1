#!/usr/bin/env python3
"""Fail when the schemas shared by REST and WebSocket have drifted.

`Message`, `TextContent` and `PublicUser` must mean exactly the same thing in
`contracts/openapi.yaml` and `contracts/asyncapi.yaml`. The spec says the WebSocket reuses the REST
structures; copying them without a check is how a contract drifts.

Local `$ref`s are resolved before comparison, so `format: uuid` and `$ref: Uuid` compare equal.
"""

from __future__ import annotations

import json
import sys

import yaml

ROOT = __file__.rsplit("/", 1)[0]
SHARED = ("Message", "TextContent", "PublicUser")


def load(name: str) -> dict:
    with open(f"{ROOT}/{name}", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def resolve(node, schemas: dict, seen: tuple[str, ...] = ()):
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[-1]
            if name in seen:
                return {"$cycle": name}
            return resolve(schemas[name], schemas, seen + (name,))
        return {key: resolve(value, schemas, seen) for key, value in node.items()}
    if isinstance(node, list):
        return [resolve(item, schemas, seen) for item in node]
    return node


def main() -> int:
    rest = load("openapi.yaml")["components"]["schemas"]
    ws = load("asyncapi.yaml")["components"]["schemas"]
    failures = []
    for name in SHARED:
        if name not in rest or name not in ws:
            failures.append(f"{name}: missing from openapi.yaml or asyncapi.yaml")
            continue
        left = resolve(rest[name], rest)
        right = resolve(ws[name], ws)
        if left != right:
            failures.append(
                f"{name}: REST and WebSocket schemas differ\n"
                f"  rest: {json.dumps(left, sort_keys=True, ensure_ascii=False)}\n"
                f"  ws:   {json.dumps(right, sort_keys=True, ensure_ascii=False)}"
            )
    if failures:
        print("Shared contract drift:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Shared schemas match: {', '.join(SHARED)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
