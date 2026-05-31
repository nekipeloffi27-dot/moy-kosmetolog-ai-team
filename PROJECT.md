# moy-kosmetolog

## What we're building

A skin-care platform with AI-powered skin analysis. Users (including
anonymous) submit selfies, the backend runs AI vision analysis (GPT-4o for
scoring, Anthropic Claude for explanations and recommendations), the user
gets a defect overlay, a skin score, and a personalized care routine. Plus:
diary tracking, community feed, AI chat, cosmetic product analysis, doctor
catalog, knowledge base.

Target audience: women 25–45 who care about their skin and want continuous
tracking — not a one-time consult. Premium-but-accessible, not a clinical
EHR.

We are NOT a generic SaaS. We are NOT a medical clinic portal. We aim for
something between Aman calm and Glossier warmth.

## Repo layout — MONOREPO

The whole product lives in **one GitHub repo** with npm workspaces:

```
moy-kosmetolog/                 ← single repo
├── package.json                ← workspace root
├── packages/
│   ├── api-python/             ← Backend: FastAPI + SQLAlchemy 2.0 async
│   ├── web/                    ← PWA: Next.js 16 + Tailwind 4 + Halo DS
│   ├── api/                    ← Legacy TS API — DO NOT touch unless asked
│   ├── mobile/                 ← Empty placeholder, KMP to be built
│   └── landing/                ← Doesn't exist yet, create when asked
```

When a task is `backend` → work in `packages/api-python/`.
When a task is `frontend_web` (PWA OR landing) → work in `packages/web/` or
`packages/landing/` as the task specifies.
When a task is `frontend_mobile` → work in `packages/mobile/`.

The dev sandbox clones the whole repo and changes its working directory to
the right `packages/<subdir>` automatically based on `GITHUB_REPO_*`
env config. You don't need to think about this.

## Surfaces

- **Backend** (`packages/api-python/`): Python 3.12, FastAPI, SQLAlchemy 2.0
  **async** (NOT raw asyncpg here — the existing codebase uses ORM, follow
  it), PostgreSQL 16, Redis 7, Alembic migrations. AI integrations:
  OpenAI GPT-4o Vision (skin scan), Anthropic Claude Sonnet (chat + recs).
  Storage: Yandex Cloud S3 via boto3. Already exists, to be extended.

- **PWA** (`packages/web/`): Next.js 16 (App Router), React 19, TypeScript,
  Tailwind CSS 4, **Halo DS** (custom design system in `halo-ds/`), TanStack
  Query, Zustand. Already exists, to be extended.

- **Mobile** (`packages/mobile/`): Kotlin Multiplatform with Compose
  Multiplatform. Empty — to be built from scratch.

- **Landing** (`packages/landing/`): Doesn't exist yet. When first needed,
  create as Next.js 15+ static export or stick with the same Next.js 16
  approach as `web/` but with `output: 'export'`.

See `tech/BACKEND_STACK.md`, `tech/PWA_STACK.md`, `tech/MOBILE_STACK.md`.

## Domain glossary

- **Клиент / Пользователь** — the end user (registered or anonymous).
- **Скан** (`scan`) — submitting a selfie for AI vision analysis. Returns
  `overall_score` + nested `analysis` object with detected defects and
  bounding boxes.
- **Дневник** (`diary`) — daily entries the user posts about their skin.
- **Рутина** (`routine`) — structured care routine (morning/evening steps).
- **Чат** (`chat`) — AI conversation with Claude about skin questions.
- **Анализ косметики** (`cosmetic_analysis`) — user uploads a product or
  ingredients list, gets a verdict and explanation.
- **Лента** (`feed`) — community posts.
- **Врач** (`doctor`) — entry in the doctor catalog.
- **Статья** (`article`) — knowledge-base article.

## Inviolable invariants

1. Never hard-delete a user, scan, or diary entry. Use soft-delete
   (`deleted_at TIMESTAMPTZ`).
2. PII (phone, email, photo URLs): never in INFO-level logs. DEBUG only.
3. All datetimes stored as `TIMESTAMPTZ` (UTC), converted at the edge.
4. Phone numbers in E.164 format (`+7XXXXXXXXXX`).
5. Anonymous flows: `anonymous_token` (stored in localStorage by the PWA)
   is required for unauthenticated scan/chat endpoints.
6. No third-party analytics SDKs without explicit user consent.
7. **Anthropic API**: endpoint `/v1/messages`, header `x-api-key`, header
   `anthropic-version: 2023-06-01`, system prompt as top-level field,
   images via `source.type: "url"` or base64. Current correct model ID:
   `claude-sonnet-4-5` for chat; `claude-opus-4-7` for premium reasoning.

## Tone / voice

Russian, addressed as **"ты"**. Warm, knowledgeable, never corporate.
See `DESIGN_SYSTEM.md` voice section.

## Working agreements for AI agents

- Read this file plus the relevant `tech/*.md` before touching code.
- The existing codebase uses **SQLAlchemy 2.0 async ORM** in
  `packages/api-python/`. Follow that pattern — don't switch to raw
  asyncpg even though you might know it from elsewhere.
- The PWA uses **Halo DS** (custom design system in `packages/web/halo-ds/`),
  NOT shadcn/ui. Use Halo components (`HaloButton`, `HaloGlass`,
  `HaloSheet`, `HaloTabBar`, etc.) and the tokens in `halo-ds/tokens.css`
  and `halo-ds/theme.ts`.
- API contracts change → go through the CTO tasking step first.
- Every new feature must work at mobile width (375px) before desktop is
  considered.
- Existing endpoints respect anonymous flows where applicable — preserve this.
