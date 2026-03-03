#!/usr/bin/env python3
"""Preflight checks for add-note.

Checks path/readiness from manifest config and source-specific dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Tuple

SOURCE_KEY_TO_LABEL = {
    "xiaohongshu": "小红书",
    "x": "X",
    "wechat-official": "微信公众号",
    "rss": "RSS",
    "generic": "网页",
    "pasted": "Pasted",
}


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def _strip_inline_comment(v: str) -> str:
    """Remove YAML-style inline comments while preserving quoted text."""
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


def parse_manifest_config(manifest_path: pathlib.Path) -> Dict[str, str]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")

    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    in_config = False
    cfg: Dict[str, str] = {}

    for raw in lines:
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not in_config:
            if line.strip() == "config:":
                in_config = True
            continue

        if line and not line.startswith(" ") and not line.startswith("\t"):
            break

        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = _strip_inline_comment(value.strip())
        value = _strip_quotes(value)
        cfg[key] = value

    if not cfg:
        raise ValueError("manifest config section is empty or malformed")
    return cfg


def to_bool(v: str, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def check_writable_dir(path: pathlib.Path, ensure_dirs: bool) -> Tuple[bool, str]:
    try:
        if ensure_dirs:
            path.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return False, f"directory does not exist: {path}"
        if not path.is_dir():
            return False, f"not a directory: {path}"

        with tempfile.NamedTemporaryFile(prefix=".preflight-", dir=path, delete=True):
            pass
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def check_file_exists(path: pathlib.Path) -> Tuple[bool, str]:
    if path.is_file():
        return True, "ok"
    return False, f"missing file: {path}"


def check_command(cmd: str) -> Tuple[bool, str]:
    hit = shutil.which(cmd)
    if hit:
        return True, hit
    return False, f"command not found: {cmd}"


def build_path_context(source_key: str, date_str: str = "2000-01-01", slug: str = "probe") -> Dict[str, str]:
    year, month, day = "", "", ""
    if len(date_str) >= 10 and date_str[4] == "-" and date_str[7] == "-":
        year, month, day = date_str[:4], date_str[5:7], date_str[8:10]
    source_label = SOURCE_KEY_TO_LABEL.get(source_key, source_key)
    return {
        "slug": slug,
        "date": date_str,
        "year": year,
        "month": month,
        "day": day,
        "source": source_label,
        "source_key": source_key,
    }


def render_path_template(template: str, context: Dict[str, str], field_name: str) -> str:
    try:
        return template.format(**context)
    except KeyError as exc:  # noqa: PERF203
        missing = str(exc).strip("'")
        raise ValueError(f"config.{field_name} uses unknown placeholder: {{{missing}}}") from exc


def resolve_cfg_path(raw_value: str, base_dir: pathlib.Path, context: Dict[str, str], field_name: str) -> pathlib.Path:
    rendered = render_path_template(raw_value, context, field_name)
    p = pathlib.Path(rendered).expanduser()
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return p


def run_cmd(
    cmd: List[str],
    cwd: pathlib.Path | None = None,
    timeout_sec: int = 600,
    extra_env: Dict[str, str] | None = None,
) -> Tuple[bool, str]:
    try:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run(  # noqa: S603
            cmd,
            cwd=str(cwd) if cwd else None,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout_sec}s"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)

    if proc.returncode == 0:
        return True, (proc.stdout or "").strip() or "ok"
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return False, output[:500] if output else f"exit code {proc.returncode}"


def load_mcp_servers(workspace: pathlib.Path) -> Dict[str, Dict[str, object]]:
    """Load MCP server configs from common project paths.

    Priority: global first, then group/local override.
    """
    merged: Dict[str, Dict[str, object]] = {}
    candidates = [
        # Host-level global MCP (mounted in container runtime).
        pathlib.Path("/workspace/global/.mcp.json"),
        workspace / ".claude" / "mcp.json",
        workspace / "groups" / "main" / ".claude" / "mcp.json",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        servers = raw.get("mcpServers")
        if isinstance(servers, dict):
            for k, v in servers.items():
                if isinstance(v, dict):
                    merged[str(k)] = v
    return merged


def check_mcp_server_declared(workspace: pathlib.Path, cfg: Dict[str, str]) -> Tuple[bool, str]:
    """Check minimax MCP readiness via MCP config/runtime launcher only."""
    server_name = (cfg.get("minimax_mcp_server_name", "minimax") or "minimax").strip()
    servers = load_mcp_servers(workspace)
    server = servers.get(server_name)
    if not server:
        return False, (
            f"mcp server '{server_name}' not found "
            f"(checked: /workspace/global/.mcp.json, <workspace>/.claude/mcp.json)"
        )

    cmd = str(server.get("command", "")).strip()
    if not cmd:
        return False, f"mcp server '{server_name}' missing command"
    args = server.get("args")
    if args is not None and not isinstance(args, list):
        return False, f"mcp server '{server_name}' args must be a list"

    lowered_args = [str(a).strip().lower() for a in args] if isinstance(args, list) else []
    has_minimax_pkg = any("minimax-coding-plan-mcp" in a for a in lowered_args)
    # Common launch styles:
    # - uvx minimax-coding-plan-mcp
    # - uv tool run minimax-coding-plan-mcp
    if cmd in {"uvx", "uv"} and lowered_args and not has_minimax_pkg:
        return False, (
            f"mcp server '{server_name}' command is {cmd} but args do not include minimax-coding-plan-mcp"
        )

    # uvx is usually shipped alongside uv; accept either binary.
    if cmd == "uvx":
        ok_uvx, msg_uvx = check_command("uvx")
        if ok_uvx:
            return True, f"mcp server '{server_name}' declared with command uvx ({msg_uvx})"
        ok_uv, msg_uv = check_command("uv")
        if ok_uv:
            return True, f"mcp server '{server_name}' declared with command uvx (uv available: {msg_uv})"
        return False, f"mcp server '{server_name}' requires uvx/uv but neither found"

    if cmd == "uv":
        ok_uv, msg_uv = check_command("uv")
        if ok_uv:
            return True, f"mcp server '{server_name}' declared with command uv ({msg_uv})"
        return False, f"mcp server '{server_name}' requires uv but command not found"

    ok, msg = check_command(cmd)
    if ok:
        return True, f"mcp server '{server_name}' declared ({cmd}: {msg})"
    return False, f"mcp server '{server_name}' declared but command not found: {cmd}"


def resolve_xhs_downloader_dir(workspace: pathlib.Path, cfg: Dict[str, str]) -> pathlib.Path:
    raw = cfg.get("xhs_downloader_path", "/workspace/group/XHS-Downloader").strip()
    if not raw:
        raw = "/workspace/group/XHS-Downloader"

    configured = pathlib.Path(raw).expanduser()
    candidates: List[pathlib.Path] = []
    if configured.is_absolute():
        candidates.append(configured)
    else:
        candidates.append((workspace / configured).resolve())

    # Common runtime/project layouts fallback (container/group variants).
    candidates.extend(
        [
            (workspace / "groups" / "main" / "XHS-Downloader").resolve(),
            (workspace / "XHS-Downloader").resolve(),
            pathlib.Path("/workspace/group/XHS-Downloader"),
            pathlib.Path("/workspace/group/groups/main/XHS-Downloader"),
            pathlib.Path("/workspace/groups/main/XHS-Downloader"),
        ]
    )

    dedup: List[pathlib.Path] = []
    seen: set[str] = set()
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        dedup.append(p)

    for p in dedup:
        if is_xhs_downloader_ready(p):
            return p

    # No ready repo found; keep configured target for potential auto-install.
    return dedup[0]


def is_xhs_downloader_ready(repo_dir: pathlib.Path) -> bool:
    return (repo_dir / "main.py").is_file() and (
        (repo_dir / "requirements.txt").is_file() or (repo_dir / "pyproject.toml").is_file()
    )


def ensure_xhs_downloader(workspace: pathlib.Path, cfg: Dict[str, str]) -> Tuple[bool, str]:
    repo_dir = resolve_xhs_downloader_dir(workspace, cfg)
    auto_install = to_bool(cfg.get("xhs_auto_install", "true"), default=True)
    install_method = cfg.get("xhs_install_method", "auto").strip().lower() or "auto"
    install_repo = cfg.get("xhs_install_repo", "https://github.com/JoeanAmier/XHS-Downloader.git").strip()

    if is_xhs_downloader_ready(repo_dir):
        return True, f"ready: {repo_dir}"

    if not auto_install:
        return False, f"missing: {repo_dir} (auto install disabled)"

    if repo_dir.exists() and not is_xhs_downloader_ready(repo_dir):
        return False, f"directory exists but not a valid XHS-Downloader repo: {repo_dir}"

    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if not repo_dir.exists():
        ok, msg = run_cmd(["git", "clone", "--depth", "1", install_repo, str(repo_dir)], cwd=workspace)
        if not ok:
            return False, f"auto-install clone failed: {msg}"

    used = ""
    if install_method in {"auto", "uv"} and shutil.which("uv"):
        ok, msg = run_cmd(["uv", "sync", "--no-dev"], cwd=repo_dir)
        if ok:
            used = "uv"
        elif install_method == "uv":
            return False, f"auto-install deps failed via uv: {msg}"
    if not used and install_method in {"auto", "pip"}:
        ok, msg = run_cmd([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=repo_dir)
        if ok:
            used = "pip"
        elif install_method == "pip":
            return False, f"auto-install deps failed via pip: {msg}"
        elif install_method == "auto" and not shutil.which("uv"):
            return False, f"auto-install deps failed via pip: {msg}"

    if not is_xhs_downloader_ready(repo_dir):
        return False, f"auto-install finished but repo still not ready: {repo_dir}"

    if used:
        return True, f"installed with {used}: {repo_dir}"
    return True, f"installed repo: {repo_dir}"


def run_checks(
    source: str,
    workspace: pathlib.Path,
    cfg: Dict[str, str],
    require_digest: bool,
    manifest_path: pathlib.Path | None = None,
) -> List[Tuple[str, bool, str]]:
    results: List[Tuple[str, bool, str]] = []
    ensure_dirs = to_bool(cfg.get("ensure_dirs", "true"), default=True)
    base_dir = manifest_path.parent.resolve() if manifest_path else workspace.resolve()
    path_context = build_path_context(source)

    raw_notes = (cfg.get("notes_path") or "").strip()
    raw_attachments = (cfg.get("attachments_path") or "").strip()
    raw_index = (cfg.get("index_file") or "").strip()

    notes_dir = None
    attachments_dir = None
    index_file = None
    if raw_notes:
        try:
            notes_dir = resolve_cfg_path(raw_notes, base_dir, path_context, "notes_path")
        except Exception as exc:  # noqa: BLE001
            results.append(("notes_path", False, str(exc)))
    if raw_attachments:
        try:
            attachments_dir = resolve_cfg_path(raw_attachments, base_dir, path_context, "attachments_path")
        except Exception as exc:  # noqa: BLE001
            results.append(("attachments_path", False, str(exc)))
    if raw_index:
        try:
            index_file = resolve_cfg_path(raw_index, base_dir, path_context, "index_file")
        except Exception as exc:  # noqa: BLE001
            results.append(("index_file", False, str(exc)))

    for name, d in (("notes_path", notes_dir), ("attachments_path", attachments_dir)):
        if d is None:
            results.append((name, False, "path is empty in manifest config"))
            continue
        ok, msg = check_writable_dir(d, ensure_dirs)
        results.append((name, ok, msg))

    if index_file:
        ok, msg = check_writable_dir(index_file.parent, ensure_dirs)
        results.append(("index_file_parent", ok, msg))

    if source in {"generic", "wechat-official"}:
        ok, msg = check_command("agent-browser")
        results.append(("agent-browser", ok, msg))

    if source == "xiaohongshu":
        ok, msg = ensure_xhs_downloader(workspace, cfg)
        results.append(("xhs-downloader", ok, msg))
        ok, msg = check_mcp_server_declared(workspace, cfg)
        results.append(("minimax-coding-plan-mcp", ok, msg))

    if source == "x":
        ok, msg = check_file_exists(workspace / ".claude/skills/x-integration/agent.ts")
        results.append(("x-integration-agent", ok, msg))
        ok, msg = check_file_exists(workspace / "data/x-auth.json")
        results.append(("x-auth", ok, msg))

    if source == "rss" and require_digest:
        ok1, msg1 = check_command("content-watcher")
        ok2, msg2 = check_command("feed-digest")
        ok = ok1 or ok2
        msg = msg1 if ok1 else msg2
        results.append(("rss-digest-tool", ok, msg))

    return results


def detect_workspace_from_manifest(manifest_path: pathlib.Path) -> pathlib.Path:
    resolved = manifest_path.resolve()
    for p in resolved.parents:
        if (p / ".claude/skills").is_dir():
            return p
    return resolved.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run preflight checks for add-note")
    parser.add_argument("--source", required=True, choices=["generic", "wechat-official", "xiaohongshu", "x", "rss", "pasted"])
    parser.add_argument("--manifest", default="./manifest.yaml")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--require-digest", action="store_true")
    args = parser.parse_args()

    manifest_arg = pathlib.Path(args.manifest)
    if manifest_arg.is_absolute():
        manifest_path = manifest_arg
    else:
        manifest_path = (pathlib.Path.cwd() / manifest_arg).resolve()
        if not manifest_path.exists() and args.manifest in {"manifest.yaml", "./manifest.yaml"}:
            # Make default invocation robust even when cwd is not the skill root.
            manifest_path = (pathlib.Path(__file__).resolve().parent.parent / "manifest.yaml").resolve()

    workspace = pathlib.Path(args.workspace).resolve() if args.workspace else detect_workspace_from_manifest(manifest_path)

    try:
        cfg = parse_manifest_config(manifest_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] manifest: {exc}")
        return 2

    results = run_checks(args.source, workspace, cfg, args.require_digest, manifest_path)
    has_fail = False
    for name, ok, msg in results:
        prefix = "[OK]" if ok else "[FAIL]"
        print(f"{prefix} {name}: {msg}")
        has_fail = has_fail or (not ok)

    if has_fail:
        print("Preflight failed. Fix failed checks before running collection/save steps.")
        return 1

    print("Preflight passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
