"""Thin GitHub REST API client. We don't use PyGithub to keep deps minimal."""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from core.config import get_settings


GITHUB_API = "https://api.github.com"


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo_path(repo_with_subdir: str) -> tuple[str, str]:
    """Parse 'owner/repo#subdir' from .env-style ref. Owner from .env."""
    settings = get_settings()
    if "#" in repo_with_subdir:
        repo, subdir = repo_with_subdir.split("#", 1)
    else:
        repo, subdir = repo_with_subdir, ""
    full = f"{settings.github_owner}/{repo}"
    return full, subdir


async def create_issue(
    repo: str,
    title: str,
    body: str,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Create a GitHub Issue. `repo` is the env ref like 'moy-kosmetolog#backend'."""
    full_repo, _ = _repo_path(repo)
    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{GITHUB_API}/repos/{full_repo}/issues",
            headers=_headers(),
            json=payload,
        )
        if r.status_code >= 400:
            logger.error("GitHub create_issue failed: {} {}", r.status_code, r.text)
            r.raise_for_status()
        data = r.json()
        logger.info("Created issue #{} in {}: {}", data["number"], full_repo, title)
        return data


async def get_pr(repo: str, pr_number: int) -> dict[str, Any]:
    full_repo, _ = _repo_path(repo)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{GITHUB_API}/repos/{full_repo}/pulls/{pr_number}",
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


async def list_pr_files(repo: str, pr_number: int) -> list[dict[str, Any]]:
    full_repo, _ = _repo_path(repo)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{GITHUB_API}/repos/{full_repo}/pulls/{pr_number}/files",
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


async def post_pr_comment(repo: str, pr_number: int, body: str) -> None:
    full_repo, _ = _repo_path(repo)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{GITHUB_API}/repos/{full_repo}/issues/{pr_number}/comments",
            headers=_headers(),
            json={"body": body},
        )
        r.raise_for_status()


async def merge_pr(repo: str, pr_number: int, *, method: str = "squash") -> bool:
    full_repo, _ = _repo_path(repo)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.put(
            f"{GITHUB_API}/repos/{full_repo}/pulls/{pr_number}/merge",
            headers=_headers(),
            json={"merge_method": method},
        )
        if r.status_code == 200:
            logger.info("Merged PR #{} in {}", pr_number, full_repo)
            return True
        logger.error("Merge failed for PR #{}: {} {}", pr_number, r.status_code, r.text)
        return False


async def clone_url(repo: str) -> str:
    full_repo, _ = _repo_path(repo)
    settings = get_settings()
    # Token-auth clone URL (works with PAT)
    return f"https://x-access-token:{settings.github_token}@github.com/{full_repo}.git"
