"""Shared helpers for all agents."""
from __future__ import annotations

from pathlib import Path


CONTEXT_DIR = Path(__file__).parent.parent / "context"


def load_context_files(*names: str) -> str:
    """Concatenate context Markdown files with section headers.

    Example: load_context_files("PROJECT.md", "DESIGN_SYSTEM.md")
    """
    pieces = []
    for name in names:
        path = CONTEXT_DIR / name
        if not path.exists():
            continue
        pieces.append(f"\n\n===== {name} =====\n\n{path.read_text(encoding='utf-8')}")
    return "".join(pieces)


def load_prompt(agent_dir: str) -> str:
    """Load the system_prompt.md for a given agent subfolder."""
    return (Path(__file__).parent / agent_dir / "system_prompt.md").read_text(encoding="utf-8")
