"""Run configured deploy command via shell.

The orchestrator runs whatever `DEPLOY_DEV_COMMAND` / `DEPLOY_PROD_COMMAND`
the user put in `.env`. Most realistic shapes:

- SSH + git pull + docker compose:
    ssh deploy@dev.moy-kosmetolog.ru 'cd /app && git pull && docker compose up -d --build'

- Trigger a GitHub Actions workflow:
    gh workflow run deploy-dev.yml --repo owner/moy-kosmetolog -f branch=main

- Trigger your own webhook:
    curl -fsSL -X POST -H 'Authorization: Bearer XYZ' https://deploy.example.com/dev

The orchestrator captures stdout+stderr and posts the tail back to Telegram
on failure.
"""
from __future__ import annotations

import asyncio


async def run_deploy_command(cmd: str, timeout: int) -> tuple[bool, str]:
    """Execute a shell command. Returns (success, combined_output)."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return False, "TIMEOUT: deploy command exceeded the configured DEPLOY_TIMEOUT"

    output = stdout.decode(errors="replace")
    return proc.returncode == 0, output
