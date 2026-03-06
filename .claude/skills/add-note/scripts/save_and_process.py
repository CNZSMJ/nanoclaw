#!/usr/bin/env python3
"""Deterministic save-and-process executor for add-note."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple

from preflight_check import parse_manifest_config, to_bool

HASHTAG_RE = re.compile(r"(?<!\w)#([^\s#`~!$%^&*()+=[\]{}|\\;:'\",.<>/?，。！？；：、“”‘’（）《》【】]+)")
IMAGE_MD_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ASCII_ALPHA_RE = re.compile(r"[A-Za-z]")
BAD_MEDIA_RE = re.compile(r"(?i)(\./media/|/media/)")
XHS_OCR_MARK_LINE_RE = re.compile(r"(?m)^[ \t]*\[图\d+\s*OCR\][ \t]*\n?")
TEMPLATE_IF_RE = re.compile(r"{{#if_([a-z_]+)}}(.*?){{/if_\1}}", re.S)
TEMPLATE_VAR_RE = re.compile(r"{{[a-zA-Z0-9_]+}}")

ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "svg"}
MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/svg+xml": "svg",
}
SOURCE_LABEL_TO_KEY = {
    "小红书": "xiaohongshu",
    "X": "x",
    "微信公众号": "wechat-official",
    "RSS": "rss",
    "网页": "generic",
    "Pasted": "pasted",
}


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def _strip_inline_comment(v: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    out: List[str] = []
    for ch in v:
        if ch == "\\" and not escaped:
            escaped = True
            out.append(ch)
            continue
        if ch == "'" and not in_double and not escaped:
            in_single = not in_single
            out.append(ch)
            continue
        if ch == '"' and not in_single and not escaped:
            in_double = not in_double
            out.append(ch)
            continue
        if ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
        escaped = False
    return "".join(out).rstrip()


def parse_scalar(v: str) -> Any:
    raw = _strip_quotes(_strip_inline_comment(v).strip())
    low = raw.lower()
    if low in {"true", "false"}:
        return low == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def parse_manifest_quality(manifest_path: pathlib.Path) -> Tuple[set[str], Dict[str, Any]]:
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    section = ""
    categories: set[str] = set()
    tag_rules: Dict[str, Any] = {
        "style": "hashtag-zh-cn",
        "ai_min_tags": 2,
        "ai_max_tags": 5,
        "forbidden_tags": [],
    }
    in_forbidden_tags = False

    for raw in lines:
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        if not line.startswith(" ") and line.endswith(":"):
            section = line[:-1].strip()
            in_forbidden_tags = False
            continue

        if section == "categories":
            if line.startswith("  ") and not line.startswith("    "):
                stripped = line.strip()
                if ":" in stripped:
                    key, _ = stripped.split(":", 1)
                    categories.add(key.strip())
            continue

        if section == "tag_rules":
            stripped = line.strip()
            if line.startswith("  ") and not line.startswith("    "):
                in_forbidden_tags = stripped.startswith("forbidden_tags:")
                if in_forbidden_tags:
                    tag_rules["forbidden_tags"] = []
                    continue
                if ":" in stripped:
                    key, value = stripped.split(":", 1)
                    tag_rules[key.strip()] = parse_scalar(value)
            elif in_forbidden_tags and line.startswith("    - "):
                tag_rules["forbidden_tags"].append(parse_scalar(stripped[2:]))

    return categories, tag_rules


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


def load_json(path_or_stdin: str) -> Any:
    if path_or_stdin == "-":
        return json.loads(sys.stdin.read())
    return json.loads(pathlib.Path(path_or_stdin).read_text(encoding="utf-8"))


def normalize_payload_items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and all(isinstance(x, dict) for x in data):
        return data
    raise ValueError("payload must be object or list of objects")


def normalize_metadata(data: Any, count: int) -> List[Dict[str, Any]]:
    if data is None:
        return [{} for _ in range(count)]
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            arr = data["items"]
            if len(arr) != count:
                raise ValueError("metadata.items length must match payload items")
            if not all(isinstance(x, dict) for x in arr):
                raise ValueError("metadata.items must contain only objects")
            return arr
        return [data for _ in range(count)]
    if isinstance(data, list):
        if len(data) != count:
            raise ValueError("metadata list length must match payload items")
        if not all(isinstance(x, dict) for x in data):
            raise ValueError("metadata list must contain only objects")
        return data
    raise ValueError("metadata must be object or list")


def slugify(title: str) -> str:
    out: List[str] = []
    for ch in title:
        if CJK_RE.match(ch):
            out.append(ch)
        elif ch.isalnum():
            out.append(ch.lower())
        else:
            out.append("-")
    slug = re.sub(r"-{2,}", "-", "".join(out)).strip("-")
    if not slug:
        slug = "note"
    return slug[:80].rstrip("-")


def parse_date_str(collected_at: str) -> str:
    if "T" in collected_at:
        try:
            parsed = dt.datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
            return parsed.date().isoformat()
        except ValueError:
            pass
    return collected_at[:10]


def format_filename(pattern: str, slug: str, date_str: str, index: Optional[int] = None, ext: str = "") -> str:
    data: Dict[str, Any] = {"slug": slug, "date": date_str, "ext": ext}
    if index is not None:
        data["index"] = index
    return pattern.format(**data)


def source_key_from_label(source_label: str) -> str:
    key = SOURCE_LABEL_TO_KEY.get(source_label)
    if key:
        return key
    fallback = re.sub(r"[^0-9A-Za-z]+", "-", source_label.strip().lower()).strip("-")
    return fallback or "unknown"


def build_path_context(source_label: str, date_str: str, slug: str) -> Dict[str, str]:
    year, month, day = "", "", ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        year, month, day = date_str.split("-")
    return {
        "slug": slug,
        "date": date_str,
        "year": year,
        "month": month,
        "day": day,
        "source": source_label,
        "source_key": source_key_from_label(source_label),
    }


def render_path_template(template: str, context: Dict[str, str], field_name: str) -> str:
    try:
        return template.format(**context)
    except KeyError as exc:  # noqa: PERF203
        missing = str(exc).strip("'")
        raise ValueError(f"config.{field_name} uses unknown placeholder: {{{missing}}}") from exc


def resolve_config_path(raw_value: str, base_dir: pathlib.Path, context: Dict[str, str], field_name: str) -> pathlib.Path:
    rendered = render_path_template(raw_value, context, field_name)
    p = pathlib.Path(rendered).expanduser()
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return p


def resolve_note_path(notes_path: pathlib.Path, base_filename: str, strategy: str, date_str: str) -> pathlib.Path:
    target = notes_path / base_filename
    if not target.exists():
        return target
    if strategy != "suffix-date-counter":
        raise ValueError(f"note exists and unsupported conflict strategy: {strategy}")

    stem = target.stem
    suffix = target.suffix or ".md"
    candidate = notes_path / f"{stem}-{date_str}{suffix}"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = notes_path / f"{stem}-{date_str}-{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def detect_language(text: str) -> str:
    """Detect language based on CJK character ratio.
    Returns 'zh' if CJK characters make up 50% or more of the non-whitespace text.
    """
    cleaned = "".join(text.split())
    if not cleaned:
        return "zh"
    cjk_count = len(CJK_RE.findall(cleaned))
    ratio = cjk_count / len(cleaned)
    if ratio >= 0.5:
        return "zh"
    return "en"


def extract_source_tags(text: str) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for m in HASHTAG_RE.finditer(text):
        tag = m.group(1).strip()
        if not tag:
            continue
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def normalize_ai_tag(raw: str, sep: str = "-") -> str:
    t = raw.strip()
    if not t:
        return ""
    t = t.lstrip("#").strip()
    t = re.sub(r"[\s\u3000_]+", sep, t)
    t = re.sub(rf"[^{re.escape(sep)}0-9A-Za-z\u4e00-\u9fff]+", sep, t)
    t = re.sub(rf"{re.escape(sep)}{{2,}}", sep, t).strip(sep)
    if not t:
        return ""
    return f"#{t}"


def normalize_ai_tags(tags: Sequence[str], tag_rules: Dict[str, Any]) -> List[str]:
    sep = "-"
    normalization = tag_rules.get("normalization")
    if isinstance(normalization, dict):
        raw_sep = str(normalization.get("separator", "-")).strip()
        if raw_sep:
            sep = raw_sep

    forbidden = {str(x).strip().lstrip("#").lower() for x in tag_rules.get("forbidden_tags", []) if str(x).strip()}
    seen: set[str] = set()
    out: List[str] = []

    for t in tags:
        nt = normalize_ai_tag(str(t), sep=sep)
        if not nt:
            continue
        key = nt.lstrip("#").lower()
        if key in forbidden:
            continue
        if key not in seen:
            seen.add(key)
            out.append(nt)
    return out


def validate_meta(meta: Dict[str, Any], categories: set[str], tag_rules: Dict[str, Any], lang: str) -> Tuple[str, List[str], List[str], str, str]:
    category = str(meta.get("category", "")).strip()
    if not category:
        raise ValueError("metadata.category is required")
    if categories and category not in categories:
        raise ValueError(f"metadata.category must be one of [{', '.join(sorted(categories))}]")

    ai_tags_raw = meta.get("ai_tags")
    if not isinstance(ai_tags_raw, list):
        raise ValueError("metadata.ai_tags must be a list")
    ai_tags = normalize_ai_tags([str(x) for x in ai_tags_raw], tag_rules)

    min_tags = int(tag_rules.get("ai_min_tags", 2))
    max_tags = int(tag_rules.get("ai_max_tags", 5))
    if len(ai_tags) < min_tags or len(ai_tags) > max_tags:
        raise ValueError(f"metadata.ai_tags count must be in [{min_tags}, {max_tags}] after normalization")

    takeaways = meta.get("takeaways")
    if not isinstance(takeaways, list):
        raise ValueError("metadata.takeaways must be a list with 3-5 items")
    takeaways_norm = [str(x).strip() for x in takeaways if str(x).strip()]
    if len(takeaways_norm) < 3 or len(takeaways_norm) > 5:
        raise ValueError("metadata.takeaways must contain 3-5 non-empty items")

    translation = str(meta.get("translation", "")).strip()
    if lang == "en" and not translation:
        raise ValueError("metadata.translation is required when source text is English")

    notes = str(meta.get("notes", "")).strip()
    return category, ai_tags, takeaways_norm, translation, notes


def detect_ext(url: str, content_type: str) -> str:
    parsed = urllib.parse.urlparse(url)
    suffix = pathlib.Path(parsed.path).suffix.lower().lstrip(".")
    if suffix in ALLOWED_EXTS:
        return suffix
    if content_type in MIME_TO_EXT:
        return MIME_TO_EXT[content_type]
    return "bin"


def download_bytes(url: str, timeout: int) -> Tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        ctype = resp.headers.get_content_type() or ""
        return resp.read(), ctype


def replace_and_download_images(
    excerpt: str,
    note_path: pathlib.Path,
    attachments_path: pathlib.Path,
    attachment_filename_format: str,
    attachment_slug: str,
    date_str: str,
    timeout: int,
    max_images: int,
    start_index: int = 0,
    url_to_local_rel: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[Dict[str, Any]], int, Dict[str, str]]:
    pieces: List[str] = []
    last = 0
    downloads: List[Dict[str, Any]] = []
    image_idx = start_index
    if url_to_local_rel is None:
        url_to_local_rel = {}

    for m in IMAGE_MD_RE.finditer(excerpt):
        pieces.append(excerpt[last : m.start()])
        alt = m.group(1)
        target = m.group(2).strip()
        url = target.split()[0].strip("<>").strip()

        if url in url_to_local_rel:
            rel = url_to_local_rel[url]
            replacement = f"![{alt}]({rel})"
            pieces.append(replacement)
            last = m.end()
            continue

        replacement = m.group(0)
        parsed = urllib.parse.urlparse(url)
        scheme = parsed.scheme.lower()
        is_remote = scheme in {"http", "https"}
        is_local = scheme == "file" or scheme == ""

        if (is_remote or is_local) and image_idx < max_images:
            image_idx += 1
            try:
                ctype = ""
                source_hint = url
                if is_remote:
                    data, ctype = download_bytes(url, timeout=timeout)
                else:
                    local_path_raw = urllib.parse.unquote(parsed.path if scheme == "file" else url)
                    local_candidate = pathlib.Path(local_path_raw)
                    if not local_candidate.is_absolute():
                        local_candidate = (note_path.parent / local_candidate).resolve()
                    if not local_candidate.is_file():
                        raise FileNotFoundError(f"local image not found: {local_candidate}")
                    data = local_candidate.read_bytes()
                    source_hint = str(local_candidate)

                ext = detect_ext(source_hint, ctype)
                name = format_filename(
                    attachment_filename_format,
                    slug=attachment_slug,
                    date_str=date_str,
                    index=image_idx,
                    ext=ext,
                )
                local_path = attachments_path / name
                local_path.write_bytes(data)
                rel = os.path.relpath(local_path, start=note_path.parent).replace("\\", "/")
                replacement = f"![{alt}]({rel})"
                url_to_local_rel[url] = rel
                downloads.append({"url": url, "saved_to": str(local_path), "ok": True})
            except Exception as exc:  # noqa: BLE001
                downloads.append({"url": url, "ok": False, "error": str(exc)})
        elif is_remote or is_local:
            downloads.append({"url": url, "ok": False, "error": "exceed max_images"})

        pieces.append(replacement)
        last = m.end()

    pieces.append(excerpt[last:])
    return "".join(pieces), downloads, image_idx, url_to_local_rel


def sanitize_excerpt_for_note(excerpt: str) -> str:
    """Remove internal OCR marker lines before final note rendering."""
    out = XHS_OCR_MARK_LINE_RE.sub("", excerpt)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def yq(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def yl(items: Sequence[str]) -> str:
    return "[" + ", ".join(yq(x) for x in items) + "]"


def load_note_template() -> str:
    template_path = (pathlib.Path(__file__).resolve().parent.parent / "reference" / "note-template.md").resolve()
    if not template_path.is_file():
        raise FileNotFoundError(f"note template not found: {template_path}")
    return template_path.read_text(encoding="utf-8")


def render_markdown_template(template: str, values: Dict[str, str], flags: Dict[str, bool]) -> str:
    def repl_if(m: re.Match[str]) -> str:
        name = m.group(1)
        block = m.group(2)
        return block if flags.get(name, False) else ""

    out = TEMPLATE_IF_RE.sub(repl_if, template)
    for k, v in values.items():
        out = out.replace(f"{{{{{k}}}}}", v)

    unresolved = TEMPLATE_VAR_RE.findall(out)
    if unresolved:
        raise ValueError(f"note template has unresolved placeholders: {', '.join(sorted(set(unresolved)))}")

    out = re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"
    return out


def render_note(
    *,
    template_text: str,
    source: str,
    title: str,
    collected_at: str,
    category: str,
    source_tags: Sequence[str],
    ai_tags: Sequence[str],
    author: str,
    takeaways: Sequence[str],
    translation: str,
    lang: str,
    excerpt: str,
    notes: str,
) -> str:
    values = {
        "source_fm": yq(source),
        "title_fm": yq(title),
        "collected_at_fm": yq(collected_at),
        "category_fm": yq(category),
        "source_tags_fm": yl(source_tags),
        "ai_tags_fm": yl(ai_tags),
        "title": title,
        "author": author,
        "takeaways": "\n".join([f"- {t}" for t in takeaways]),
        "translation": translation,
        "excerpt": excerpt,
        "notes": notes,
    }
    flags = {
        "author": bool(author),
        "translation": bool(translation),
        "notes": bool(notes),
    }
    return render_markdown_template(template_text, values, flags)


def atomic_write(path: pathlib.Path, content: str, enabled: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not enabled:
        path.write_text(content, encoding="utf-8")
        return
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".tmp") as tf:
        tf.write(content)
        temp_path = pathlib.Path(tf.name)
    temp_path.replace(path)


def postcheck_note(note_path: pathlib.Path) -> List[str]:
    errs: List[str] = []
    content = note_path.read_text(encoding="utf-8")
    if BAD_MEDIA_RE.search(content):
        errs.append("note contains forbidden media path; use attachments_path only")
    required = ["source:", "title:", "collected_at:", "category:", "source_tags:", "ai_tags:"]
    if content.startswith("---"):
        end = content.find("\n---", 3)
        fm = content[: end + 4] if end != -1 else content[:800]
    else:
        fm = content[:800]
        errs.append("note missing YAML frontmatter delimiter")
    for key in required:
        if key not in fm:
            errs.append(f"frontmatter missing required key: {key.rstrip(':')}")
    return errs


def process_payload(
    *,
    payload_items: List[Dict[str, Any]],
    metadata_items: List[Dict[str, Any]],
    manifest_path: pathlib.Path,
    expected_source_label: Optional[str],
) -> Dict[str, Any]:
    cfg = parse_manifest_config(manifest_path)
    categories, tag_rules = parse_manifest_quality(manifest_path)
    note_template = load_note_template()
    base_dir = manifest_path.parent.resolve()

    notes_path_tpl = str(cfg.get("notes_path", "")).strip()
    attachments_path_tpl = str(cfg.get("attachments_path", "")).strip()
    note_name_fmt = str(cfg.get("note_filename_format", "{slug}.md"))
    attachment_name_fmt = str(cfg.get("attachment_filename_format", "{slug}_{index:02}.{ext}"))
    conflict_strategy = str(cfg.get("note_conflict_strategy", "suffix-date-counter"))
    timeout = int(cfg.get("download_timeout_seconds", "20"))
    max_images = int(cfg.get("max_images", "30"))
    atomic = to_bool(str(cfg.get("atomic_write", "true")), default=True)
    ensure_dirs = to_bool(str(cfg.get("ensure_dirs", "true")), default=True)
    index_file_tpl = str(cfg.get("index_file", "")).strip()

    outputs: List[Dict[str, Any]] = []
    failures: List[str] = []

    for i, (item, meta) in enumerate(zip(payload_items, metadata_items)):
        note_path: Optional[pathlib.Path] = None
        try:
            source = str(item.get("source", "")).strip()
            title = str(item.get("title", "")).strip()
            collected_at = str(item.get("collected_at", "")).strip()
            excerpt = str(item.get("excerpt", "")).strip()
            author = str(meta.get("author", item.get("author", ""))).strip()
            if expected_source_label and source != expected_source_label:
                raise ValueError(f"payload source mismatch: expected '{expected_source_label}', got '{source}'")

            slug = slugify(title)
            date_str = parse_date_str(collected_at)
            path_context = build_path_context(source, date_str, slug)
            notes_path = resolve_config_path(notes_path_tpl, base_dir, path_context, "notes_path")
            attachments_path = resolve_config_path(attachments_path_tpl, base_dir, path_context, "attachments_path")
            index_file = resolve_config_path(index_file_tpl, base_dir, path_context, "index_file") if index_file_tpl else None

            if ensure_dirs:
                notes_path.mkdir(parents=True, exist_ok=True)
                attachments_path.mkdir(parents=True, exist_ok=True)
                if index_file:
                    index_file.parent.mkdir(parents=True, exist_ok=True)

            note_name = format_filename(note_name_fmt, slug=slug, date_str=date_str)
            note_path = resolve_note_path(notes_path, note_name, conflict_strategy, date_str)

            lang = detect_language(excerpt)
            category, ai_tags, takeaways, translation, notes = validate_meta(meta, categories, tag_rules, lang)
            source_tags = extract_source_tags(excerpt)

            url_cache: Dict[str, str] = {}
            excerpt_local, downloads, img_idx, url_cache = replace_and_download_images(
                excerpt=excerpt,
                note_path=note_path,
                attachments_path=attachments_path,
                attachment_filename_format=attachment_name_fmt,
                attachment_slug=note_path.stem,
                date_str=date_str,
                timeout=timeout,
                max_images=max_images,
                start_index=0,
                url_to_local_rel=url_cache,
            )
            
            translation_local = ""
            if translation:
                translation_local, trans_downloads, img_idx, url_cache = replace_and_download_images(
                    excerpt=translation,
                    note_path=note_path,
                    attachments_path=attachments_path,
                    attachment_filename_format=attachment_name_fmt,
                    attachment_slug=note_path.stem,
                    date_str=date_str,
                    timeout=timeout,
                    max_images=max_images,
                    start_index=img_idx,
                    url_to_local_rel=url_cache,
                )
                downloads.extend(trans_downloads)

            excerpt_for_note = sanitize_excerpt_for_note(excerpt_local)
            translation_for_note = sanitize_excerpt_for_note(translation_local)

            content = render_note(
                template_text=note_template,
                source=source,
                title=title,
                collected_at=collected_at,
                category=category,
                source_tags=source_tags,
                ai_tags=ai_tags,
                author=author,
                takeaways=takeaways,
                translation=translation_for_note,
                lang=lang,
                excerpt=excerpt_for_note,
                notes=notes,
            )
            atomic_write(note_path, content, enabled=atomic)
            post_errs = postcheck_note(note_path)
            if post_errs:
                raise ValueError("; ".join(post_errs))

            if index_file:
                rel = os.path.relpath(note_path, start=index_file.parent).replace("\\", "/")
                safe_title = title.replace("]", "\\]")
                line = f"- {date_str}|[{safe_title}]({rel})|{category}\n"
                with index_file.open("a", encoding="utf-8") as f:
                    f.write(line)

            outputs.append(
                {
                    "item_index": i,
                    "note_path": str(note_path),
                    "source": source,
                    "title": title,
                    "category": category,
                    "source_tags": source_tags,
                    "ai_tags": ai_tags,
                    "lang": lang,
                    "downloads": downloads,
                    "ok": True,
                }
            )
        except Exception as exc:  # noqa: BLE001
            if note_path and note_path.exists():
                try:
                    note_path.unlink()
                except Exception:  # noqa: BLE001
                    pass
            failures.append(f"item[{i}] {exc}")
            outputs.append({"item_index": i, "ok": False, "error": str(exc)})

    return {
        "ok": not failures,
        "failures": failures,
        "outputs": outputs,
        "manifest_path": str(manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Save and process add-note payload deterministically")
    parser.add_argument("--payload", required=True, help="Payload JSON file path or '-' for stdin")
    parser.add_argument("--metadata", default=None, help="Metadata JSON file path (object/list). Required for strict mode.")
    parser.add_argument("--manifest", default="./manifest.yaml")
    parser.add_argument("--source-label", default=None, help="Expected source label, e.g. 小红书 / X / RSS")
    parser.add_argument("--report-out", default=None, help="Optional report output path")
    args = parser.parse_args()

    manifest_path = resolve_manifest_path(args.manifest)

    try:
        payload_data = load_json(args.payload)
        payload_items = normalize_payload_items(payload_data)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] cannot load payload: {exc}")
        return 2

    if args.metadata is None:
        print("[FAIL] metadata is required; pass --metadata <json>")
        return 2

    try:
        meta_data = load_json(args.metadata)
        meta_items = normalize_metadata(meta_data, len(payload_items))
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] cannot load metadata: {exc}")
        return 2

    report = process_payload(
        payload_items=payload_items,
        metadata_items=meta_items,
        manifest_path=manifest_path,
        expected_source_label=args.source_label,
    )

    if args.report_out:
        out_path = pathlib.Path(args.report_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] report written: {out_path}")

    if not report["ok"]:
        print("[FAIL] save-and-process failed:")
        for err in report["failures"]:
            print(f"  - {err}")
        return 1

    print(f"[OK] save-and-process passed ({len(report['outputs'])} item(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
