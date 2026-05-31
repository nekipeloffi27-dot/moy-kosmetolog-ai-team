# Backend stack — moy-kosmetolog/packages/api-python

## Stack (actual, not aspirational)

- Python 3.12
- FastAPI (async)
- **SQLAlchemy 2.0 async** with the typed ORM (NOT raw asyncpg —
  the existing codebase uses ORM, follow it)
- PostgreSQL 16
- Redis 7
- Alembic migrations
- Uvicorn server
- pytest + pytest-asyncio
- pydantic v2 for schemas
- boto3 for Yandex Cloud S3
- ruff for linting

AI clients:
- `openai` for GPT-4o Vision (skin scan)
- `anthropic` for Claude (chat, recommendations)

## Repo layout (inside packages/api-python/)

```
packages/api-python/
├── app/
│   ├── main.py                  # FastAPI app + router assembly
│   ├── server.py                # Uvicorn entrypoint
│   ├── seed.py / seed_articles.py
│   ├── core/
│   │   ├── config.py            # Pydantic settings
│   │   └── deps.py              # Auth deps (current_user, etc.)
│   ├── db/
│   │   ├── session.py           # Async SQLAlchemy engine + session
│   │   └── models.py            # 17 ORM models — single file
│   ├── modules/                 # one folder per feature
│   │   ├── auth/                # OTP, JWT, OAuth (Telegram/Yandex/Apple/Google/VK)
│   │   ├── user/
│   │   ├── scan/                # AI Vision skin scan
│   │   ├── recommendations/
│   │   ├── diary/
│   │   ├── feed/
│   │   ├── chat/                # Claude chat
│   │   ├── cosmetic_analysis/
│   │   ├── routine/
│   │   ├── home/                # home widgets
│   │   ├── articles/
│   │   ├── doctors/
│   │   └── upload/              # S3 file uploads
│   └── services/
│       ├── redis_client.py
│       ├── storage.py           # S3 / Yandex Cloud
│       └── weather.py
├── migrations/                  # Alembic
├── tests/                       # pytest
├── requirements.txt
├── pyproject.toml               # ruff config
├── alembic.ini
└── Dockerfile
```

## Module structure convention

Every feature module under `modules/<name>/` follows roughly:

```
modules/<name>/
├── __init__.py
├── router.py        # FastAPI router with endpoints
├── schemas.py       # Pydantic request/response models
├── service.py       # business logic (pure-ish; uses session)
└── (optional) ai.py # LLM-specific helpers
```

When adding new feature: follow this structure. Don't introduce a new
pattern.

## Conventions

- **SQLAlchemy 2.0 async** with the `select()` + `session.execute()` style:

```python
from sqlalchemy import select
from app.db.models import User

async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
```

  Use `session.flush()` + `session.refresh()` after creates if you need
  generated PKs. Use explicit `await session.commit()` at the endpoint
  boundary (not inside services).

- **Models are in one file**: `app/db/models.py`. Add new models there
  alongside the existing 17. Don't split per-module — that's not how the
  codebase is organized today.

- **Pydantic v2** with `model_config = ConfigDict(from_attributes=True)`
  for ORM → schema mapping.

- **Migrations**: Alembic. Use `alembic revision -m "..." --autogenerate`
  to generate from model diffs (the project DOES use autogenerate, unlike
  some other patterns). Review the generated migration before committing.

- **Money in kopecks** as integer everywhere. Never floats.

- **Datetimes as `TIMESTAMPTZ` (UTC)**. Convert to local TZ at the API
  edge if needed for display.

- **IDs**: UUID PKs.

- **Soft-delete**: `deleted_at TIMESTAMPTZ`. Queries default to
  `WHERE deleted_at IS NULL`. Add this filter to every list query for
  domain tables.

- **Anonymous endpoints**: scan, cosmetic_analysis, and some chat endpoints
  accept `anonymous_token` from the client when no JWT is present. The
  pattern is in `app/modules/scan/router.py` — copy it for any new
  anonymous-allowed endpoint.

## API conventions

- All routes under `/api/v1/<module>/...` (Nginx strips `/api/` → port 3000,
  the app sees `/v1/...`).
- Response format: directly the Pydantic schema, not wrapped. Errors via
  `HTTPException` with `status_code` + `detail`.
- For paginated lists: `?limit=20&offset=0` with response
  `{"items": [...], "total": N}`.

## AI integration patterns

### OpenAI GPT-4o Vision (scan)

```python
from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=settings.openai_api_key)

resp = await client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": "Analyze this skin photo."},
        ]},
    ],
)
```

### Anthropic Claude (chat, recommendations)

```python
from anthropic import AsyncAnthropic
client = AsyncAnthropic(api_key=settings.anthropic_api_key)

resp = await client.messages.create(
    model="claude-sonnet-4-5",   # CORRECT model id, do NOT use claude-sonnet-3-x
    max_tokens=4000,
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": user_text}],
)
text = resp.content[0].text
```

NEVER call OpenAI/Anthropic with hardcoded keys — always via
`app.core.config.settings`.

## Code style

- `ruff` (config in `pyproject.toml`).
- Type hints required on every function signature.
- `from __future__ import annotations` at the top of new files for cleaner
  forward refs.
- Errors: domain raises typed exceptions; router translates to HTTPException.
- Logging: use the standard logging setup that already exists. Structured
  log keys: `user_id`, `scan_id`, `feature_id` when relevant. Never log
  phone, email, photo URLs at INFO.

## Testing

- Unit tests for service-layer logic (pure Python, fast).
- Integration tests via `httpx.AsyncClient` against a test Postgres.
- Required coverage for new endpoints: happy path + at least one error path
  + (for anonymous-allowed endpoints) an anonymous-token path.

## Migration rules

1. Migrations forward-only in practice. Always write `downgrade()` for
   completeness, never rely on it.
2. NEVER drop a column in the same migration that adds its replacement —
   ship replacement, deploy, backfill, THEN drop later.
3. Adding NOT NULL to non-empty table: add NULL → backfill → set NOT NULL,
   in three migrations.
4. Indexes on existing tables: `CREATE INDEX CONCURRENTLY`.

## Working in the monorepo

- The Python project lives at `packages/api-python/`. The dev sandbox is
  already set to work there via `GITHUB_REPO_BACKEND=moy-kosmetolog#packages/api-python`.
- Don't pretend the rest of the monorepo doesn't exist, but don't touch it
  from backend tasks. If a frontend change is needed for your feature, the
  CTO already created a separate frontend task — that agent handles it.

## Pre-existing repo

Repo: monorepo `moy-kosmetolog`, work in `packages/api-python/`.
Default branch: `main`.
PR title format: `[<feature_id_short>] <task title>`.
Branch naming: `feat/<feature_id_short>/<slug>`.
