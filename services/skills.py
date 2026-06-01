"""Agent skills loader.

Skills are Markdown files that get injected into agent system prompts.
Layout:
    skills/
        common/<skill-name>/SKILL.md   — injected for every role
        <role>/<skill-name>/SKILL.md   — injected for that role only
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger


# Fallback: skills/ adjacent to repo root (for local dev and tests)
_REPO_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _skills_root() -> Path:
    """Return the resolved skills root directory.

    Prefers SKILLS_DIR from settings; falls back to the repo-local skills/ dir.
    """
    try:
        from core.config import get_settings
        configured = Path(get_settings().skills_dir)
        if configured.exists():
            return configured
    except Exception:
        pass
    return _REPO_SKILLS_DIR


def list_skill_dirs(role: str) -> list[Path]:
    """Return existing skill directories for *role* (common + role-specific), sorted."""
    root = _skills_root()
    dirs: list[Path] = []

    for base in (root / "common", root / role):
        if not base.exists():
            continue
        skill_dirs = sorted(d for d in base.iterdir() if d.is_dir())
        dirs.extend(skill_dirs)

    return dirs


def load_skills_for(role: str, only: list[str] | None = None) -> str:
    """Load and concatenate SKILL.md files for *role*.

    Each skill is wrapped in <skill name="...">...</skill>.
    Missing directories are silently skipped.
    *only* — if provided, only load skills whose directory name is in this list.
    """
    parts: list[str] = []

    for skill_dir in list_skill_dirs(role):
        if only is not None and skill_dir.name not in only:
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        try:
            content = skill_file.read_text(encoding="utf-8").strip()
            parts.append(f'<skill name="{skill_dir.name}">\n{content}\n</skill>')
            logger.debug("Loaded skill '{}' for role '{}'", skill_dir.name, role)
        except Exception as e:
            logger.warning("Failed to read skill {}: {}", skill_file, e)

    return "\n\n".join(parts)
