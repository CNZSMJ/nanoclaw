#!/usr/bin/env python3
"""Validate collection payload for add-note."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any, Dict, List

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_LIKE_RE = re.compile(r"^(https?://|www\.)", re.IGNORECASE)
ALLOWED_SOURCES = {"小红书", "X", "微信公众号", "RSS", "网页", "Pasted"}


def load_input(input_arg: str) -> Any:
    if input_arg == "-":
        raw = sys.stdin.read()
    else:
        raw = pathlib.Path(input_arg).read_text(encoding="utf-8")
    return json.loads(raw)


def non_empty_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def is_valid_collected_at(v: str) -> bool:
    if DATE_RE.match(v):
        return True
    try:
        dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_one(item: Dict[str, Any], idx: int) -> List[str]:
    errs: List[str] = []
    required = ["title", "source", "collected_at", "excerpt"]
    for key in required:
        if key not in item:
            errs.append(f"item[{idx}].{key}: missing")
            continue
        if not non_empty_str(item[key]):
            errs.append(f"item[{idx}].{key}: must be non-empty string")

    if "collected_at" in item and isinstance(item.get("collected_at"), str):
        if not is_valid_collected_at(item["collected_at"].strip()):
            errs.append(f"item[{idx}].collected_at: must be YYYY-MM-DD or ISO-8601")

    source = item.get("source")
    if isinstance(source, str) and source.strip():
        source_norm = source.strip()
        if URL_LIKE_RE.match(source_norm):
            errs.append(f"item[{idx}].source: must be source label, URL is not allowed")
        elif source_norm not in ALLOWED_SOURCES:
            allowed = ", ".join(sorted(ALLOWED_SOURCES))
            errs.append(f"item[{idx}].source: must be one of [{allowed}]")

    excerpt = item.get("excerpt")
    if isinstance(excerpt, str) and "data:image/" in excerpt.lower():
        errs.append(f"item[{idx}].excerpt: base64 inline image is forbidden")

    return errs


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate collection payload")
    parser.add_argument("--input", default="-", help="JSON file path or '-' for stdin")
    args = parser.parse_args()

    try:
        data = load_input(args.input)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] cannot load JSON: {exc}")
        return 2

    items: List[Dict[str, Any]]
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        if not all(isinstance(x, dict) for x in data):
            print("[FAIL] payload list must contain only objects")
            return 2
        items = data
    else:
        print("[FAIL] payload must be object or list of objects")
        return 2

    all_errs: List[str] = []
    for i, item in enumerate(items):
        all_errs.extend(validate_one(item, i))

    if all_errs:
        print("[FAIL] payload validation failed:")
        for err in all_errs:
            print(f"  - {err}")
        return 1

    print(f"[OK] payload validation passed ({len(items)} item(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
