"""Helper for creating revert PRs via git + gh CLI.

Creates a shallow clone of the target repo, runs `git revert`, pushes a new
branch, and opens a PR. Cleans up the temp clone on exit.
"""
from __future__ import annotations

import shutil
import tempfile
from uuid import uuid4

from loguru import logger

from core.config import get_settings
from services.ops_tools import _run_subprocess


class RevertError(Exception):
    pass


def _full_repo(repo_ref: str) -> str:
    """Return 'owner/repo' from env-style ref like 'moy-kosmetolog#packages/api-python'."""
    settings = get_settings()
    repo = repo_ref.split("#", 1)[0]
    return f"{settings.github_owner}/{repo}"


async def create_revert_pr(
    repo_ref: str,
    pr_number: int,
    pr_title: str,
    merge_commit_sha: str,
    base_branch: str,
) -> str:
    """Shallow-clone the repo, revert the merge commit, push, open a PR.

    Returns the URL of the newly created revert PR.
    Raises RevertError on failure.
    """
    settings = get_settings()
    full_repo = _full_repo(repo_ref)
    clone_url = (
        f"https://x-access-token:{settings.github_token}"
        f"@github.com/{full_repo}.git"
    )
    revert_branch = f"revert/pr-{pr_number}-{uuid4().hex[:6]}"

    tmpdir = tempfile.mkdtemp(prefix="ai-team-revert-")
    logger.info("Reverting PR #{} in {} → branch {}", pr_number, full_repo, revert_branch)
    try:
        await _run_subprocess(
            "git", "clone", "--depth", "30", "--branch", base_branch,
            clone_url, tmpdir,
            timeout=180,
        )

        # Configure git identity (required for commit)
        await _run_subprocess(
            "git", "-C", tmpdir, "config", "user.email", "ai-team@moy-kosmetolog.local",
            timeout=10,
        )
        await _run_subprocess(
            "git", "-C", tmpdir, "config", "user.name", "moy-kosmetolog AI Team",
            timeout=10,
        )

        await _run_subprocess(
            "git", "-C", tmpdir, "checkout", "-b", revert_branch,
            timeout=15,
        )

        # -m 1 selects the first parent (the base branch) as the mainline
        await _run_subprocess(
            "git", "-C", tmpdir,
            "revert", merge_commit_sha, "-m", "1", "--no-edit",
            timeout=60,
        )

        await _run_subprocess(
            "git", "-C", tmpdir, "push", "origin", revert_branch,
            timeout=60,
        )

        output = await _run_subprocess(
            "gh", "pr", "create",
            "--repo", full_repo,
            "--base", base_branch,
            "--head", revert_branch,
            "--title", f"Revert: PR #{pr_number} — {pr_title[:60]}",
            "--body", (
                f"Automatic revert of PR #{pr_number} created by moy-kosmetolog AI Team.\n\n"
                f"Original PR title: {pr_title}\n"
                f"Reverted commit: `{merge_commit_sha}`"
            ),
            timeout=60,
        )

        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        url = next((ln for ln in reversed(lines) if ln.startswith("http")), None)
        if not url:
            raise RevertError(f"gh pr create output did not contain a URL:\n{output[:500]}")
        logger.info("Revert PR created: {}", url)
        return url

    except RevertError:
        raise
    except Exception as e:
        raise RevertError(f"create_revert_pr failed for PR #{pr_number}: {e}") from e
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
