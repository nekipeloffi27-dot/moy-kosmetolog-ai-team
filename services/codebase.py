"""Read-only codebase snapshot tools for Designer and CTO tasking agents.

The snapshot lives at CODEBASE_SNAPSHOT_DIR (default:
/var/ai-team-workspace/codebase-snapshot). Clone it there manually on VM
setup; refresh_snapshot() keeps it current via `git fetch + reset --hard`.

All path operations are sandboxed to the snapshot root — no escapes,
no absolute paths, no symlinks pointing outside.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from loguru import logger


class CodebaseAccessError(Exception):
    pass


def _snapshot_root() -> Path:
    from core.config import get_settings
    return Path(get_settings().codebase_snapshot_dir)


def _safe_resolve(root: Path, user_path: str) -> Path:
    """Resolve *user_path* relative to *root*, rejecting any escape attempt."""
    if not user_path or Path(user_path).is_absolute():
        raise CodebaseAccessError(f"Absolute or empty path not allowed: {user_path!r}")

    resolved = (root / user_path).resolve()
    root_resolved = root.resolve()

    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise CodebaseAccessError(f"Path escape not allowed: {user_path!r}")

    return resolved


# ─── Public tool functions ────────────────────────────────────────────────────

def list_directory(path: str) -> list[str]:
    """List entries in *path* (relative to snapshot root). Returns sorted list."""
    root = _snapshot_root()
    target = _safe_resolve(root, path or ".")
    if not target.exists():
        raise CodebaseAccessError(f"Path not found: {path!r}")
    if not target.is_dir():
        raise CodebaseAccessError(f"Not a directory: {path!r}")
    entries = sorted(item.relative_to(root) for item in target.iterdir())
    return [str(e) + ("/" if (root / e).is_dir() else "") for e in entries]


def read_file(path: str, max_chars: int = 50_000) -> str:
    """Read *path* (relative to snapshot root), capped at *max_chars*."""
    root = _snapshot_root()
    target = _safe_resolve(root, path)
    if not target.exists():
        raise CodebaseAccessError(f"File not found: {path!r}")
    if not target.is_file():
        raise CodebaseAccessError(f"Not a file: {path!r}")
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... [truncated at {max_chars} chars]"
    return text


def search_codebase(pattern: str, glob: str = "**/*") -> list[dict[str, Any]]:
    """Search for *pattern* (regex) in files matching *glob*.

    Returns up to 50 hits: [{file, line, content}, ...].
    """
    root = _snapshot_root()
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise CodebaseAccessError(f"Invalid regex: {e}")

    results: list[dict[str, Any]] = []
    for file_path in sorted(root.glob(glob)):
        if not file_path.is_file():
            continue
        # Skip binary and very large files
        if file_path.stat().st_size > 500_000:
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if compiled.search(line):
                results.append({
                    "file": str(file_path.relative_to(root)),
                    "line": i,
                    "content": line.rstrip(),
                })
                if len(results) >= 50:
                    return results
    return results


# ─── Anthropic tool spec ─────────────────────────────────────────────────────

def get_codebase_tools_spec() -> list[dict]:
    return [
        {
            "name": "list_directory",
            "description": (
                "List files and subdirectories in a directory of the codebase snapshot. "
                "Use to explore the project layout before generating code or designs."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Relative path from repo root, e.g. 'packages/web/components'. "
                            "Use '.' or '' for the root."
                        ),
                    }
                },
                "required": ["path"],
            },
        },
        {
            "name": "read_file",
            "description": (
                "Read the full contents of a file in the codebase snapshot. "
                "Useful for inspecting existing components, routes, or models."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative file path from repo root.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return (default 50000).",
                    },
                },
                "required": ["path"],
            },
        },
        {
            "name": "search_codebase",
            "description": (
                "Search for a regex pattern across files in the codebase. "
                "Returns up to 50 matches with file path, line number, and content. "
                "Useful for finding existing component names, API endpoints, or types."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern (case-insensitive) to search for.",
                    },
                    "glob": {
                        "type": "string",
                        "description": (
                            "Glob pattern to restrict search to specific files "
                            "(default '**/*', e.g. '**/*.tsx' for React files)."
                        ),
                    },
                },
                "required": ["pattern"],
            },
        },
    ]


async def codebase_tool_executor(name: str, args: dict) -> str:
    """Dispatch a codebase tool call and return its result as a string."""
    try:
        if name == "list_directory":
            entries = list_directory(args.get("path", "."))
            return json.dumps(entries, ensure_ascii=False)

        if name == "read_file":
            return read_file(args["path"], args.get("max_chars", 50_000))

        if name == "search_codebase":
            hits = search_codebase(args["pattern"], args.get("glob", "**/*"))
            if not hits:
                return "No matches found."
            return json.dumps(hits, ensure_ascii=False)

        return f"Unknown tool: {name}"

    except CodebaseAccessError as e:
        return f"Access error: {e}"
    except Exception as e:
        logger.exception("Codebase tool '{}' failed: {}", name, e)
        return f"Error: {type(e).__name__}: {e}"


# ─── Snapshot refresh ─────────────────────────────────────────────────────────

async def refresh_snapshot() -> None:
    """Run `git fetch && git reset --hard origin/main` in the snapshot dir.

    Raises RuntimeError if the snapshot directory does not exist.
    The initial clone must be done manually during VM setup.
    """
    root = _snapshot_root()
    if not root.exists():
        raise RuntimeError(
            f"Codebase snapshot directory not found: {root}. "
            "Clone the repo there manually as part of VM setup."
        )

    async def _run(*cmd: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(
                f"`{' '.join(cmd)}` failed (exit {proc.returncode}): "
                f"{stderr.decode(errors='replace')[-500:]}"
            )
        logger.debug("Snapshot {}: {}", " ".join(cmd), stdout.decode(errors="replace")[-200:])

    await _run("git", "fetch", "origin")
    await _run("git", "reset", "--hard", "origin/main")
    logger.info("Codebase snapshot refreshed at {}", root)
