#!/usr/bin/env python3
"""Check whether a link already exists in local notes."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse
from typing import Dict, List, Set

from preflight_check import parse_manifest_config


def resolve_manifest_path(manifest: str) -> pathlib.Path:
    p = pathlib.Path(manifest)
    if p.is_absolute():
        return p
    candidate = (pathlib.Path.cwd() / p).resolve()
    if candidate.exists():
        return candidate
    if manifest in {"manifest.yaml", "./manifest.yaml"}:
        return (pathlib.Path(__file__).resolve().parent.parent / "manifest.yaml").resolve()
    return candidate


def _normalize_url_once(url: str, drop_query: bool) -> str:
    s = url.strip()
    if not s:
        return ""
    p = urllib.parse.urlparse(s)
    if not p.scheme:
        return s

    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    path = urllib.parse.unquote(p.path or "")
    if path != "/":
        path = path.rstrip("/")
    query = "" if drop_query else p.query
    fragment = ""
    out = urllib.parse.urlunparse((scheme, netloc, path, "", query, fragment))
    return out


def build_url_candidates(url: str) -> Set[str]:
    u = url.strip()
    out: Set[str] = set()
    if not u:
        return out

    variants = {
        u,
        urllib.parse.unquote(u),
        _normalize_url_once(u, drop_query=False),
        _normalize_url_once(u, drop_query=True),
    }
    for v in variants:
        if not v:
            continue
        out.add(v)
        out.add(v.rstrip("/"))

    # X/Twitter common equivalence.
    extra: Set[str] = set()
    for v in out:
        if "x.com/" in v:
            extra.add(v.replace("x.com/", "twitter.com/"))
        if "twitter.com/" in v:
            extra.add(v.replace("twitter.com/", "x.com/"))
    out.update(extra)

    return {x for x in out if x}


def resolve_notes_search_root(notes_path_tpl: str, manifest_dir: pathlib.Path) -> pathlib.Path:
    raw = notes_path_tpl.strip()
    if not raw:
        return manifest_dir

    # If path uses templates, search from the static prefix before first placeholder.
    brace_idx = raw.find("{")
    if brace_idx != -1:
        raw = raw[:brace_idx].rstrip("/\\")
        if not raw:
            raw = "."

    p = pathlib.Path(raw).expanduser()
    if not p.is_absolute():
        p = (manifest_dir / p).resolve()
    return p


def search_notes(root: pathlib.Path, url_candidates: Set[str], max_files: int = 20000) -> List[str]:
    if not root.exists() or not root.is_dir():
        return []

    hits: List[str] = []
    count = 0
    for md in root.rglob("*.md"):
        count += 1
        if count > max_files:
            break
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        if any(c in text for c in url_candidates):
            hits.append(str(md))
    return sorted(hits)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether a URL already exists in notes")
    parser.add_argument("--url", required=True, help="Original source URL")
    parser.add_argument("--manifest", default="./manifest.yaml")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    report: Dict[str, object] = {
        "ok": False,
        "exists": False,
        "url": args.url,
        "manifest": "",
        "notes_search_root": "",
        "matches": [],
    }

    try:
        manifest_path = resolve_manifest_path(args.manifest)
        cfg = parse_manifest_config(manifest_path)
        notes_tpl = str(cfg.get("notes_path", "")).strip()
        notes_root = resolve_notes_search_root(notes_tpl, manifest_path.parent.resolve())
        candidates = build_url_candidates(args.url)
        matches = search_notes(notes_root, candidates)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] check-existing-note: {exc}")
        report["error"] = str(exc)
        if args.json_out:
            out = pathlib.Path(args.json_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2

    report["ok"] = True
    report["exists"] = bool(matches)
    report["manifest"] = str(manifest_path)
    report["notes_search_root"] = str(notes_root)
    report["matches"] = matches

    if args.json_out:
        out = pathlib.Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if matches:
        print(f"[FOUND] {len(matches)} note(s) contain this URL:")
        for p in matches:
            print(f"- {p}")
        return 0

    print("[MISS] no existing note contains this URL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

