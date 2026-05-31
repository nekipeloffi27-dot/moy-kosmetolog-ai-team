# moy-kosmetolog-ai-team

Team of AI agents that designs, builds, reviews, **deploys**, and ships
features for [moy-kosmetolog](#) — driven from Telegram with **5 distinct
bots**, each with its own avatar/name acting as a separate team member.

**Current status**: M0–M6 complete. Full pipeline from `/feature` to a
deployed dev stand and (with `/deploy_prod confirm`) to production.

## The team

| Bot              | Role                           | Listens? | Posts as itself |
|------------------|--------------------------------|----------|-----------------|
| `pm_bot`         | Project Manager (coordinator)  | ✅       | ✅              |
| `designer_bot`   | Designer (Opus)                | ❌       | ✅              |
| `cto_bot`        | CTO (tasking + review + deploy)| ❌       | ✅              |
| `backend_bot`    | Backend developer (Sonnet)     | ❌       | ✅              |
| `frontend_bot`   | Frontend dev (web + mobile)    | ❌       | ✅              |

PM is the only bot you talk to. Worker bots only post.

## Pipeline (M0–M6)

```
You → PM bot: /feature <text + optional screenshot>
       │
       └─→ PM creates topic + posts intro
              │
              └─→ 🎨 Designer: mockups (HTML→PNG)
                    │
                    └─→ PM: "Что дальше? /approve_design / /redo_design"
                          │
                          ├─[/redo_design]─→ Designer redoes
                          │
                          └─[/approve_design]
                                │
                                └─→ 📋 CTO: tasking → GitHub Issues
                                      │
                                      └─→ ⌨️ Dev agents (parallel Docker sandboxes)
                                            │  • Backend bot → PR
                                            │  • Frontend bot → PR
                                            │  • Frontend bot → PR (mobile)
                                            │
                                            └─→ 🔍 CTO: review each PR
                                                  │  ├ approve → merge
                                                  │  └ request_changes → back to dev
                                                  │       │
                                                  │       └─→ dev agent adds commits to same branch
                                                  │           PR auto-updates → back to review
                                                  │
                                                  └─[all merged]→ 🚀 CTO: dev deploy
                                                        │
                                                        ├─[fail]─→ BLOCKED
                                                        │
                                                        └─[ok]─→ PM: "Иди тестировать"
                                                                  │
                                                                  ├─[/fail_test]─→ back to CTO tasking
                                                                  │
                                                                  └─[/pass_test]─→ PROD_READY
                                                                        │
                                                                        └─[/deploy_prod confirm]─→ 🚀 CTO: prod deploy
                                                                              │
                                                                              └─→ 🎉 PROD_DEPLOYED
```

## Setup

### 1. Create 5 bots in @BotFather

`/newbot` × 5. Give them names, avatars, and short bios that match their roles.

### 2. Provision the VM

```bash
sudo bash setup-vm.sh
```

### 3. Clone and configure

```bash
git clone https://github.com/<you>/moy-kosmetolog-ai-team.git
cd moy-kosmetolog-ai-team
cp .env.example .env
vim .env
```

Required: 5 bot tokens, `TELEGRAM_ALLOWED_USER_IDS`, `ANTHROPIC_API_KEY`,
`GITHUB_TOKEN`, `GITHUB_OWNER`, `POSTGRES_PASSWORD`.

Optional but recommended (M6 deploy):
- `DEPLOY_DEV_COMMAND` — shell command to deploy to dev (see examples in
  `.env.example`)
- `DEPLOY_PROD_COMMAND` — same for prod

If you leave them empty, the deploy step is **skipped** and the feature
transitions straight from "all PRs merged" to "testing" — useful while
you're getting the rest of the pipeline working.

### 4. Set up SSH key (if deploy uses SSH)

If `DEPLOY_DEV_COMMAND` uses SSH (most common case), generate a key inside
the bot container and add its public key to your deploy server's
`authorized_keys`:

```bash
# Generate inside the bot container
docker compose exec bot ssh-keygen -t ed25519 -N "" -f /root/.ssh/id_ed25519
docker compose exec bot cat /root/.ssh/id_ed25519.pub
# Add that pubkey to the deploy server
```

Alternatively, mount your existing SSH key into the bot container by adding
to `docker-compose.yml`:

```yaml
services:
  bot:
    volumes:
      - ~/.ssh:/root/.ssh:ro
```

### 5. Start core services + migrate

```bash
docker compose up -d db redis
docker compose run --rm bot alembic upgrade head
```

### 6. Build dev sandbox image (M5)

```bash
docker build -t ai-team-dev-sandbox:latest agents/dev/sandbox/
```

### 7. Create workspace dir

```bash
sudo mkdir -p /var/ai-team-workspace
sudo chown -R $USER:$USER /var/ai-team-workspace
```

### 8. Start the bot service

```bash
docker compose up -d bot
docker compose logs -f bot
```

Expect 5 `Bot [<role>] connected` lines.

### 9. Bootstrap the Telegram supergroup

1. Create a Telegram supergroup with forum topics enabled.
2. Add **all 5 bots** as admins.
3. Send `/chatid` to the PM bot inside the group.
4. Put the chat_id in `.env` → `TELEGRAM_FEATURE_GROUP_ID`.
5. Restart: `docker compose restart bot`.

## Commands (PM bot only)

In a feature thread:
- `/status` — current state + budget used
- `/approve_design` — accept design, kick off CTO tasking
- `/redo_design <feedback>` — ask Designer to redo
- `/pass_test` — testing on dev succeeded
- `/fail_test <feedback>` — testing failed, re-task with feedback
- `/deploy_prod confirm` — run prod deploy
- `/cancel` — abandon feature

Anywhere:
- `/list` — your active features
- `/chatid` — IDs for setup
- `/ping` — DB health
- `/version`

## Models used

| Agent           | Model             | Why                                   |
|-----------------|-------------------|---------------------------------------|
| Designer        | claude-opus-4-7   | Visual quality + design system enforcement |
| CTO tasking     | claude-opus-4-7   | Architecture decisions, contract design |
| CTO review      | claude-opus-4-7   | Catches subtle convention violations  |
| Backend dev     | claude-sonnet-4-6 | Fast code generation, contract-bound  |
| Frontend dev    | claude-sonnet-4-6 | Same                                  |

Override via `MODEL_*` env vars.

## Budget

Each feature has a cap (`DEFAULT_BUDGET_CAP_CENTS`, default $5). Every LLM
call is logged in `agent_calls`. Going over cap → `BudgetExceeded` → state
moves to `BLOCKED`.

Inspect:
```sql
SELECT agent, model,
       COUNT(*) AS calls,
       SUM(input_tokens) AS in_tok,
       SUM(output_tokens) AS out_tok,
       SUM(cost_cents) / 100.0 AS usd
FROM agent_calls
WHERE feature_id = '<uuid>'
GROUP BY agent, model
ORDER BY usd DESC;
```

## State machine

```
design_pending → design_review → tasks_pending → coding → review
                                                            ↓
                            dev_deployed → testing → prod_ready → prod_deployed
                                  ↓                       ↓
                               blocked                 blocked

Plus loops:
  review → coding         (CTO requested fixes on ≥1 PR)
  testing → tasks_pending (user found problems during testing)
  blocked → <previous>    (manual unblock)
```

Full transition table: `core/state_machine.py`.

## How CTO review works (M6)

When all dev tasks reach PR_OPEN, state moves to REVIEW. The CTO agent:

1. For each PR (skipping already-merged tasks):
   - Fetches the diff from GitHub.
   - Calls Claude Opus with the diff + task description + API contract +
     stack conventions + (for frontend) design system.
   - Claude returns JSON: `{verdict, summary, actionable_feedback,
     design_system_violations}`.
   - Posts the review summary as a comment on the PR.
2. If approve → merges the PR (squash by default, configurable).
3. If request_changes:
   - Stores `actionable_feedback` in `feature.context`.
   - Sets task status back to `pending`.
4. After all PR_OPEN tasks processed:
   - If every task is now MERGED → transitions DEV_DEPLOYED → kicks off deploy.
   - If any went back to pending → transitions CODING → dev agent re-runs
     **only** failing tasks. The sandbox checks out the existing branch and
     adds commits, so the same PR auto-updates.

## Reuse across projects

Bot Telegram accounts are reusable across projects (Telegram scopes by
chat_id). For multiple projects on one VM, run two Compose stacks with
separate `.env` files differing in `TELEGRAM_FEATURE_GROUP_ID`,
`GITHUB_REPO_*`, and `context/`. Single-process multi-project routing is a
small future refactor (M8+).

## What's NOT done — M7

- **M7** — Full prod-deploy orchestration with: pre-deploy checks (smoke
  tests on dev), staged rollout, automatic rollback on health-check failure.
  Currently `/deploy_prod confirm` runs `DEPLOY_PROD_COMMAND` as-is and
  expects it to handle rollout.

## Project layout

```
moy-kosmetolog-ai-team/
├── docker-compose.yml
├── Dockerfile                       # bot image w/ playwright/chromium
├── requirements.txt
├── .env.example
├── setup-vm.sh
├── alembic/                         # migrations (raw SQL)
├── bot/
│   ├── main.py                      # boots 5 bots, polling on PM
│   └── handlers/                    # all attached to PM
│       ├── admin.py
│       ├── feature.py
│       └── feedback.py
├── core/
│   ├── bots.py                      # BotRegistry
│   ├── config.py
│   ├── db.py
│   ├── enums.py
│   ├── models.py
│   ├── budget.py
│   ├── state_machine.py
│   └── orchestrator.py
├── services/
│   ├── features.py
│   ├── tasks.py
│   └── threads.py
├── integrations/
│   ├── anthropic_client.py
│   ├── github.py
│   └── deploy.py                    # M6: shell command runner
├── agents/
│   ├── base.py
│   ├── designer/                    # M3
│   ├── cto_tasking/                 # M4
│   ├── dev/                         # M5: sandbox launcher + image
│   │   └── sandbox/{Dockerfile, entrypoint.sh}
│   ├── cto_review/                  # M6
│   ├── cto_deploy/                  # M6
│   ├── backend_dev/                 # M5: CLAUDE.md + system prompt
│   ├── frontend_web_dev/            # M5
│   └── frontend_mobile_dev/         # M5
└── context/
    ├── PROJECT.md
    ├── DESIGN_SYSTEM.md
    ├── MOODBOARD.md
    ├── ANTI_REFERENCES.md
    └── tech/
        ├── BACKEND_STACK.md
        ├── PWA_STACK.md
        └── MOBILE_STACK.md
```

## Troubleshooting

**Bot doesn't start: 5 `getMe` errors** → check all 5 tokens.

**CTO review crashes with "non-JSON output"** → the model produced text
instead of JSON. The review defaults to `request_changes` with the raw
text as feedback (safe default). If it happens often, increase
`MODEL_CTO_REVIEW` to Opus (already default).

**Dev sandbox can't push to branch on re-run** → the entrypoint detects
existing branches and reuses them. If a force-push happened externally
between rounds, it might fail with "non-fast-forward". Fix: delete the
remote branch and let the agent re-create it, OR `git push --force-with-lease`
in the entrypoint (currently we don't, to be safe).

**Deploy command fails with SSH errors** → check the bot container has an
SSH key with access to the deploy target. Easiest: mount `~/.ssh` into the
bot container (see Setup step 4).

**Deploy "skipped"** → `DEPLOY_DEV_COMMAND` is empty. Expected during initial
setup; fill it in when ready.

**PR auto-merge fails with 405** → branch protection on target repo is too
strict (requires reviews, status checks, etc.). Either relax protection or
let CTO post approve comment + you merge manually.

**Worker bot doesn't post in a thread** → not admin in the supergroup.
Add them.
