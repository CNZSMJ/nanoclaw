#!/usr/bin/env python3
"""Preflight checks for add-note.

Checks path/readiness from manifest config and source-specific dependencies.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Tuple


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


def resolve_xhs_downloader_dir(workspace: pathlib.Path, cfg: Dict[str, str]) -> pathlib.Path:
    raw = cfg.get("xhs_downloader_path", "groups/main/XHS-Downloader").strip()
    if not raw:
        raw = "groups/main/XHS-Downloader"
    p = pathlib.Path(raw).expanduser()
    if not p.is_absolute():
        p = workspace / p
    return p


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


def minimax_uv_env(cfg: Dict[str, str]) -> Dict[str, str]:
    cache_dir = cfg.get("minimax_uv_cache_dir", "/tmp/uv-cache").strip() or "/tmp/uv-cache"
    tool_dir = cfg.get("minimax_uv_tool_dir", "/tmp/uv-tools").strip() or "/tmp/uv-tools"
    return {"UV_CACHE_DIR": cache_dir, "UV_TOOL_DIR": tool_dir}


def _has_minimax_via_pip(pkg: str) -> Tuple[bool, str]:
    ok, msg = run_cmd([sys.executable, "-m", "pip", "show", pkg])
    if not ok:
        return False, msg
    return True, f"pip package found: {pkg}"


def has_minimax_coding_plan_mcp(cfg: Dict[str, str], pkg: str | None = None) -> Tuple[bool, str]:
    pkg_name = (pkg or cfg.get("minimax_mcp_package", "minimax-coding-plan-mcp")).strip() or "minimax-coding-plan-mcp"
    tool_bin = shutil.which("minimax-coding-plan-mcp")
    if tool_bin:
        return True, f"binary found: {tool_bin}"

    if shutil.which("uv"):
        ok, msg = run_cmd(["uv", "tool", "list"], extra_env=minimax_uv_env(cfg))
        if ok:
            normalized = msg.lower()
            if pkg_name.lower() in normalized:
                return True, f"uv tool installed: {pkg_name}"
        else:
            # Keep going; uv may be unavailable in current env, but pip install can still satisfy requirement.
            msg = f"uv tool list failed: {msg}"

    ok, pip_msg = _has_minimax_via_pip(pkg_name)
    if ok:
        return True, pip_msg
    return False, f"{pkg_name} not installed"


def ensure_minimax_coding_plan_mcp(cfg: Dict[str, str]) -> Tuple[bool, str]:
    auto_install = to_bool(cfg.get("minimax_mcp_auto_install", "true"), default=True)
    pkg = cfg.get("minimax_mcp_package", "minimax-coding-plan-mcp").strip() or "minimax-coding-plan-mcp"
    install_method = cfg.get("minimax_mcp_install_method", "auto").strip().lower() or "auto"

    ok, msg = has_minimax_coding_plan_mcp(cfg, pkg)
    if ok:
        return True, msg
    if not auto_install:
        return False, f"{msg} (auto install disabled)"

    last_err = ""
    if install_method in {"auto", "uv"}:
        if shutil.which("uv"):
            ok, install_msg = run_cmd(["uv", "tool", "install", pkg], extra_env=minimax_uv_env(cfg))
            if ok:
                ok, msg = has_minimax_coding_plan_mcp(cfg, pkg)
                if ok:
                    return True, f"installed with uv: {pkg}"
            else:
                last_err = f"uv install failed: {install_msg}"
        elif install_method == "uv":
            return False, "cannot install minimax mcp via uv: uv not found"

    if install_method in {"auto", "pip"}:
        ok, install_msg = run_cmd([sys.executable, "-m", "pip", "install", pkg])
        if ok:
            ok, msg = has_minimax_coding_plan_mcp(cfg, pkg)
            if ok:
                return True, f"installed with pip: {pkg}"
        else:
            last_err = (last_err + "; " if last_err else "") + f"pip install failed: {install_msg}"

    ok, msg = has_minimax_coding_plan_mcp(cfg, pkg)
    if ok:
        return True, f"installed: {pkg}"
    if last_err:
        return False, f"auto-install minimax mcp failed: {last_err}"
    return False, f"installed command ran but package still unavailable: {msg}"


def run_checks(source: str, workspace: pathlib.Path, cfg: Dict[str, str], require_digest: bool) -> List[Tuple[str, bool, str]]:
    results: List[Tuple[str, bool, str]] = []
    ensure_dirs = to_bool(cfg.get("ensure_dirs", "true"), default=True)

    raw_notes = (cfg.get("notes_path") or "").strip()
    raw_attachments = (cfg.get("attachments_path") or "").strip()
    raw_index = (cfg.get("index_file") or "").strip()

    notes_dir = pathlib.Path(raw_notes).expanduser() if raw_notes else None
    attachments_dir = pathlib.Path(raw_attachments).expanduser() if raw_attachments else None
    index_file = pathlib.Path(raw_index).expanduser() if raw_index else None

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
        ok, msg = ensure_minimax_coding_plan_mcp(cfg)
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

    results = run_checks(args.source, workspace, cfg, args.require_digest)
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
