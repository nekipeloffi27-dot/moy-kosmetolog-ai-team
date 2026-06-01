#!/usr/bin/env bash
#
# Sandbox entrypoint. Runs as user 'dev' inside the container.
#
# Required env:
#   REPO_URL, REPO_FULL, REPO_SUBDIR, BRANCH, DEFAULT_BRANCH,
#   ANTHROPIC_API_KEY, MODEL, GH_TOKEN, TASK_TITLE, PR_TITLE,
#   ISSUE_NUMBER (optional), IS_RERUN (0|1)
#
# Required mounts:
#   /prompts/TASK.md, /prompts/CLAUDE.md, /prompts/AGENT_SYSTEM_PROMPT.md
#
# Outputs on stdout:
#   PR_URL=https://github.com/.../pull/123

set -euo pipefail

log() { echo "[sandbox $(date +%H:%M:%S)] $*" >&2; }

require() {
    if [[ -z "${!1:-}" ]]; then
        echo "ERROR: env $1 is required" >&2
        exit 2
    fi
}

require REPO_URL
require REPO_FULL
require BRANCH
require DEFAULT_BRANCH
require ANTHROPIC_API_KEY
require MODEL
require GH_TOKEN
require PR_TITLE

# ── Git identity ──
git config --global user.email "ai-team@moy-kosmetolog.local"
git config --global user.name  "moy-kosmetolog-ai-team"
git config --global init.defaultBranch "${DEFAULT_BRANCH}"

cd /workspace

# ── Clean any leftover state from a previous run on this workspace ──
if [[ -d repo ]]; then
    log "Removing stale /workspace/repo from prior run"
    rm -rf repo
fi

# ── Clone ──
log "Cloning ${REPO_FULL} (subdir='${REPO_SUBDIR:-}')"
git clone "${REPO_URL}" repo
cd repo

# ── Branch: re-use existing or create fresh ──
if git ls-remote --exit-code --heads origin "${BRANCH}" >/dev/null 2>&1; then
    log "Branch ${BRANCH} exists on origin — checking out for revision"
    git fetch origin "${BRANCH}":"${BRANCH}"
    git checkout "${BRANCH}"
else
    log "Creating new branch ${BRANCH} from ${DEFAULT_BRANCH}"
    git checkout -b "${BRANCH}" "origin/${DEFAULT_BRANCH}"
fi

# Determine working subdirectory
if [[ -n "${REPO_SUBDIR:-}" ]]; then
    WORKDIR="/workspace/repo/${REPO_SUBDIR}"
    if [[ ! -d "${WORKDIR}" ]]; then
        log "Subdir '${REPO_SUBDIR}' does not exist — creating"
        mkdir -p "${WORKDIR}"
    fi
else
    WORKDIR="/workspace/repo"
fi

# Place CLAUDE.md so Claude Code picks it up
cp /prompts/CLAUDE.md "${WORKDIR}/CLAUDE.md"

# Build prompt
PROMPT_FILE=$(mktemp)
{
    cat /prompts/AGENT_SYSTEM_PROMPT.md
    echo
    echo "---"
    echo
    cat /prompts/TASK.md
    echo
    echo "---"
    echo
    echo "When done, do not commit yet — just finalize your edits."
    echo "Do not run \`git\`, \`gh\`, or any push commands. The wrapper handles that."
} > "${PROMPT_FILE}"

cd "${WORKDIR}"
log "Skills available:"
ls -la /root/.claude/skills/ 2>/dev/null || echo "  (none mounted)" >&2

log "Running Claude Code (model=${MODEL}, rerun=${IS_RERUN:-0}, max_turns=${CLAUDE_MAX_TURNS:-20})…"

PROXY_ENV=""
if [[ -n "${ANTHROPIC_PROXY_URL:-}" ]]; then
    PROXY_ENV="HTTPS_PROXY=${ANTHROPIC_PROXY_URL} HTTP_PROXY=${ANTHROPIC_PROXY_URL}"
    log "Using HTTPS proxy for Claude Code"
fi

# TODO: add --max-turns "${CLAUDE_MAX_TURNS:-20}" once Claude Code CLI exposes the flag.
# As of 2026-06-01 the CLI has --max-budget-usd but no --max-turns / --max-iterations.
env ${PROXY_ENV} ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
    claude \
    --print \
    --model "${MODEL}" \
    --permission-mode acceptEdits \
    --append-system-prompt "$(cat /prompts/AGENT_SYSTEM_PROMPT.md)" \
    < "${PROMPT_FILE}" \
    > /tmp/agent.log 2>&1 || {
        log "Claude Code failed. Tail of log:"
        tail -100 /tmp/agent.log >&2
        exit 1
    }

log "Claude Code finished. Tail of log:"
tail -50 /tmp/agent.log >&2

# Remove the temporary CLAUDE.md before committing
rm -f "${WORKDIR}/CLAUDE.md"

# Commit & push
cd /workspace/repo

if [[ -z "$(git status --porcelain)" ]]; then
    log "No new changes — checking if the branch is already ahead"
    if [[ "${IS_RERUN:-0}" = "1" ]] && [[ -n "$(git log "origin/${DEFAULT_BRANCH}..HEAD" --oneline)" ]]; then
        log "Re-run but Claude made no new edits — branch has prior commits only"
        # Still try to find existing PR to report back
    else
        log "Re-run produced no changes — aborting"
        exit 3
    fi
fi

if [[ -n "$(git status --porcelain)" ]]; then
    git add -A
    COMMIT_MSG="${PR_TITLE}"
    if [[ "${IS_RERUN:-0}" = "1" ]]; then
        COMMIT_MSG="${COMMIT_MSG} (review fixes)"
    fi
    git commit -m "${COMMIT_MSG}

Made by moy-kosmetolog-ai-team."
    log "Pushing branch ${BRANCH}"
    git push origin "${BRANCH}"
fi

# Open or report existing PR
log "Looking up or opening PR"
PR_URL=$(gh pr view --repo "${REPO_FULL}" "${BRANCH}" --json url -q .url 2>/dev/null || echo "")

if [[ -z "${PR_URL}" ]]; then
    PR_BODY=$(mktemp)
    {
        cat /prompts/TASK.md
        echo
        echo "---"
        echo
        if [[ -n "${ISSUE_NUMBER:-}" ]]; then
            echo "Closes #${ISSUE_NUMBER}"
            echo
        fi
        echo "_Authored by moy-kosmetolog-ai-team. Review before merging._"
    } > "${PR_BODY}"

    PR_URL=$(gh pr create \
        --repo "${REPO_FULL}" \
        --base "${DEFAULT_BRANCH}" \
        --head "${BRANCH}" \
        --title "${PR_TITLE}" \
        --body-file "${PR_BODY}")
    log "PR opened: ${PR_URL}"
else
    log "Existing PR: ${PR_URL}"
fi

# Final line on stdout — parsed by orchestrator
echo "PR_URL=${PR_URL}"
