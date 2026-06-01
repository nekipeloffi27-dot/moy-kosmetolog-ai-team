"""Read-only ops diagnostic tools for CTO ops agent.

All tools are strictly read-only. No writes, no restarts, no destructive ops.
SSH commands are validated against a whitelist before execution.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from loguru import logger


class OpsError(Exception):
    pass


# ─── SSH command whitelist ────────────────────────────────────────────────────

_SSH_ALLOWED: list[re.Pattern] = [
    re.compile(r"^docker\s+ps(\s|$)"),
    re.compile(r"^docker\s+logs(\s|$)"),
    re.compile(r"^cat\s+/var/log/"),
    re.compile(r"^journalctl(\s|$)"),
    re.compile(r"^df\s+-h(\s|$)"),
    re.compile(r"^free\s+-h(\s|$)"),
    re.compile(r"^git\s+(log|status|diff)(\s|$)"),
    re.compile(r"^systemctl\s+status\s+"),
    re.compile(r"^uptime(\s|$)"),
    re.compile(r"^ps\s+(aux|axf)(\s|$)"),
]

_SSH_BLOCKED_TOKENS = re.compile(
    r"\b(rm|mv|cp|kill|pkill|killall|shutdown|reboot|poweroff|halt|"
    r"chmod|chown|dd|mkfs|fdisk|sudo|su|passwd|useradd|userdel|"
    r"iptables|firewall|systemctl\s+stop|systemctl\s+restart|"
    r"docker\s+stop|docker\s+restart|docker\s+rm|docker\s+kill)\b",
    re.IGNORECASE,
)


def _validate_ssh_command(command: str) -> None:
    """Raise OpsError if command is not in the read-only whitelist."""
    if _SSH_BLOCKED_TOKENS.search(command):
        raise OpsError(
            f"Command contains a forbidden token (write/destructive ops not allowed): {command!r}"
        )
    for pattern in _SSH_ALLOWED:
        if pattern.match(command.strip()):
            return
    raise OpsError(
        f"Command not in SSH read-only whitelist: {command!r}. "
        "Allowed: docker ps, docker logs, cat /var/log/*, journalctl, "
        "df -h, free -h, git log/status/diff, systemctl status, uptime, ps aux."
    )


async def _run_subprocess(*args: str, timeout: int = 60) -> str:
    """Run a subprocess and return stdout+stderr as a single string."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise OpsError(f"Command timed out after {timeout}s: {' '.join(args[:3])}")
    return stdout.decode(errors="replace")


# ─── Tool functions ───────────────────────────────────────────────────────────

async def gh_run_list(workflow: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """List recent GitHub Actions runs."""
    cmd = [
        "gh", "run", "list",
        "--json", "databaseId,status,conclusion,workflowName,headBranch,createdAt",
        f"--limit={limit}",
    ]
    if workflow:
        cmd += ["--workflow", workflow]
    try:
        output = await _run_subprocess(*cmd)
        return json.loads(output)
    except json.JSONDecodeError:
        raise OpsError(f"gh returned non-JSON: {output[:500]}")
    except Exception as e:
        raise OpsError(f"gh_run_list failed: {e}")


async def gh_run_view(run_id: str) -> str:
    """View logs of a specific GitHub Actions run (failed steps only)."""
    try:
        return await _run_subprocess("gh", "run", "view", str(run_id), "--log-failed", timeout=60)
    except OpsError:
        raise
    except Exception as e:
        raise OpsError(f"gh_run_view failed: {e}")


async def read_docker_logs(container: str, tail: int = 200) -> str:
    """Read recent logs from a whitelisted Docker container."""
    from core.config import get_settings
    allowed = [c.strip() for c in get_settings().ops_allowed_containers.split(",") if c.strip()]
    if container not in allowed:
        raise OpsError(
            f"Container {container!r} is not in the allowed list. "
            f"Allowed: {allowed}. Set OPS_ALLOWED_CONTAINERS to add more."
        )
    try:
        return await _run_subprocess("docker", "logs", "--tail", str(tail), container)
    except OpsError:
        raise
    except Exception as e:
        raise OpsError(f"read_docker_logs failed: {e}")


async def ssh_run_readonly(host: str, command: str) -> str:
    """Run a read-only command on an allowed SSH host."""
    from core.config import get_settings
    allowed_hosts = [h.strip() for h in get_settings().ops_allowed_ssh_hosts.split(",") if h.strip()]
    if not allowed_hosts:
        raise OpsError("SSH ops are disabled. Set OPS_ALLOWED_SSH_HOSTS to enable.")
    if host not in allowed_hosts:
        raise OpsError(
            f"Host {host!r} is not in the SSH allowed list. Allowed: {allowed_hosts}"
        )
    _validate_ssh_command(command)
    try:
        return await _run_subprocess(
            "ssh", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
            host, command,
            timeout=60,
        )
    except OpsError:
        raise
    except Exception as e:
        raise OpsError(f"ssh_run_readonly failed: {e}")


# ─── Anthropic tool spec ─────────────────────────────────────────────────────

def get_ops_tools_spec() -> list[dict]:
    return [
        {
            "name": "gh_run_list",
            "description": "List recent GitHub Actions workflow runs. Use to see if CI is failing.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "workflow": {
                        "type": "string",
                        "description": "Optional workflow name or filename to filter by.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of runs to return (default 5, max 20).",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "gh_run_view",
            "description": "View the failed step logs of a specific GitHub Actions run.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "The numeric run ID from gh_run_list.",
                    }
                },
                "required": ["run_id"],
            },
        },
        {
            "name": "read_docker_logs",
            "description": (
                "Read recent log lines from a Docker container running on this host. "
                "Only whitelisted containers are accessible."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "container": {
                        "type": "string",
                        "description": "Container name (e.g. 'ai-team-bot', 'ai-team-db').",
                    },
                    "tail": {
                        "type": "integer",
                        "description": "Number of log lines to return (default 200).",
                    },
                },
                "required": ["container"],
            },
        },
        {
            "name": "ssh_run_readonly",
            "description": (
                "Run a read-only command on a remote server via SSH. "
                "Only whitelisted hosts and commands are allowed."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "SSH host (e.g. 'user@server.example.com').",
                    },
                    "command": {
                        "type": "string",
                        "description": (
                            "Read-only shell command. Allowed: docker ps, docker logs, "
                            "cat /var/log/*, journalctl, df -h, free -h, "
                            "git log/status/diff, systemctl status, uptime, ps aux."
                        ),
                    },
                },
                "required": ["host", "command"],
            },
        },
    ]


async def ops_tool_executor(name: str, args: dict) -> str:
    """Dispatch an ops tool call and return its result as a string."""
    try:
        if name == "gh_run_list":
            result = await gh_run_list(
                workflow=args.get("workflow"),
                limit=min(int(args.get("limit", 5)), 20),
            )
            return json.dumps(result, ensure_ascii=False, default=str)

        if name == "gh_run_view":
            return await gh_run_view(str(args["run_id"]))

        if name == "read_docker_logs":
            return await read_docker_logs(
                args["container"],
                tail=min(int(args.get("tail", 200)), 1000),
            )

        if name == "ssh_run_readonly":
            return await ssh_run_readonly(args["host"], args["command"])

        return f"Unknown ops tool: {name}"

    except OpsError as e:
        return f"Ops error: {e}"
    except Exception as e:
        logger.exception("Ops tool '{}' failed: {}", name, e)
        return f"Error: {type(e).__name__}: {e}"
