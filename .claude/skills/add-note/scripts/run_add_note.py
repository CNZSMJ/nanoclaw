#!/usr/bin/env python3
"""Strict end-to-end executor for add-note skill."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any, Dict, List

from preflight_check import detect_workspace_from_manifest, parse_manifest_config, run_checks
from save_and_process import (
    normalize_metadata,
    normalize_payload_items,
    parse_manifest_quality,
    process_payload,
    resolve_manifest_path,
)
from validate_payload import validate_one

SOURCE_TO_LABEL = {
    "xiaohongshu": "小红书",
    "x": "X",
    "wechat-official": "微信公众号",
    "rss": "RSS",
    "generic": "网页",
    "pasted": "Pasted",
}


def load_json(path_or_stdin: str) -> Any:
    if path_or_stdin == "-":
        import sys

        return json.loads(sys.stdin.read())
    return json.loads(pathlib.Path(path_or_stdin).read_text(encoding="utf-8"))


def write_report(path: str, report: Dict[str, Any]) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] report written: {p}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run strict add-note workflow")
    parser.add_argument("--source", required=True, choices=sorted(SOURCE_TO_LABEL.keys()))
    parser.add_argument("--payload", required=True, help="Payload JSON path or '-' for stdin")
    parser.add_argument("--metadata", required=True, help="Metadata JSON path")
    parser.add_argument("--manifest", default="./manifest.yaml")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--require-digest", action="store_true")
    parser.add_argument("--report-out", default=None)
    args = parser.parse_args()

    report: Dict[str, Any] = {"ok": False, "steps": [], "source": args.source}
    manifest_path = resolve_manifest_path(args.manifest)
    workspace = pathlib.Path(args.workspace).resolve() if args.workspace else detect_workspace_from_manifest(manifest_path)
    expected_source_label = SOURCE_TO_LABEL[args.source]

    # Step 1: Preflight gate
    try:
        cfg = parse_manifest_config(manifest_path)
    except Exception as exc:  # noqa: BLE001
        msg = f"manifest parse failed: {exc}"
        report["steps"].append({"step": "preflight", "ok": False, "error": msg})
        if args.report_out:
            write_report(args.report_out, report)
        print(f"[FAIL] {msg}")
        return 2

    preflight_results = run_checks(args.source, workspace, cfg, args.require_digest)
    preflight_failed = [r for r in preflight_results if not r[1]]
    for name, ok, msg in preflight_results:
        prefix = "[OK]" if ok else "[FAIL]"
        print(f"{prefix} preflight.{name}: {msg}")
    report["steps"].append(
        {
            "step": "preflight",
            "ok": not preflight_failed,
            "results": [{"name": n, "ok": ok, "message": m} for n, ok, m in preflight_results],
        }
    )
    if preflight_failed:
        if args.report_out:
            write_report(args.report_out, report)
        print("[FAIL] preflight gate failed")
        return 1

    # Step 2: Payload gate
    try:
        payload_data = load_json(args.payload)
        payload_items = normalize_payload_items(payload_data)
    except Exception as exc:  # noqa: BLE001
        msg = f"cannot load payload: {exc}"
        report["steps"].append({"step": "payload-load", "ok": False, "error": msg})
        if args.report_out:
            write_report(args.report_out, report)
        print(f"[FAIL] {msg}")
        return 2

    payload_errs: List[str] = []
    for i, item in enumerate(payload_items):
        payload_errs.extend(validate_one(item, i))
        source = str(item.get("source", "")).strip()
        if source != expected_source_label:
            payload_errs.append(f"item[{i}].source: expected '{expected_source_label}', got '{source}'")

    if payload_errs:
        report["steps"].append({"step": "payload-validate", "ok": False, "errors": payload_errs})
        if args.report_out:
            write_report(args.report_out, report)
        print("[FAIL] payload validation failed:")
        for err in payload_errs:
            print(f"  - {err}")
        return 1
    report["steps"].append({"step": "payload-validate", "ok": True, "count": len(payload_items)})
    print(f"[OK] payload validated ({len(payload_items)} item(s))")

    # Step 3: Metadata gate
    try:
        metadata_data = load_json(args.metadata)
        metadata_items = normalize_metadata(metadata_data, len(payload_items))
    except Exception as exc:  # noqa: BLE001
        msg = f"cannot load metadata: {exc}"
        report["steps"].append({"step": "metadata-load", "ok": False, "error": msg})
        if args.report_out:
            write_report(args.report_out, report)
        print(f"[FAIL] {msg}")
        return 2

    # Category pre-check to fail early with concise message.
    categories, _ = parse_manifest_quality(manifest_path)
    missing_meta: List[str] = []
    for i, m in enumerate(metadata_items):
        category = str(m.get("category", "")).strip()
        if not category:
            missing_meta.append(f"item[{i}].metadata.category is required")
        elif categories and category not in categories:
            missing_meta.append(f"item[{i}].metadata.category invalid: {category}")
        ai_tags = m.get("ai_tags")
        if not isinstance(ai_tags, list):
            missing_meta.append(f"item[{i}].metadata.ai_tags must be list")
        takeaways = m.get("takeaways")
        if not isinstance(takeaways, list):
            missing_meta.append(f"item[{i}].metadata.takeaways must be list(3-5)")
    if missing_meta:
        report["steps"].append({"step": "metadata-validate", "ok": False, "errors": missing_meta})
        if args.report_out:
            write_report(args.report_out, report)
        print("[FAIL] metadata validation failed:")
        for err in missing_meta:
            print(f"  - {err}")
        return 1
    report["steps"].append({"step": "metadata-validate", "ok": True, "count": len(metadata_items)})
    print(f"[OK] metadata validated ({len(metadata_items)} item(s))")

    # Step 4: Deterministic save and postcheck
    save_report = process_payload(
        payload_items=payload_items,
        metadata_items=metadata_items,
        manifest_path=manifest_path,
        expected_source_label=expected_source_label,
    )
    report["steps"].append({"step": "save-and-process", "ok": bool(save_report.get("ok")), "detail": save_report})

    if not save_report.get("ok"):
        if args.report_out:
            write_report(args.report_out, report)
        print("[FAIL] save-and-process failed:")
        for err in save_report.get("failures", []):
            print(f"  - {err}")
        return 1

    report["ok"] = True
    if args.report_out:
        write_report(args.report_out, report)
    print(f"[OK] add-note workflow passed ({len(save_report.get('outputs', []))} item(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
