# Backend stack — moy-kosmetolog/packages/api-python

## Stack (actual)

- **Python 3.12**
- **FastAPI 0.115.x** — async
- **SQLAlchemy 2.0 async** с typed ORM (`Mapped`, `mapped_column`) — NOT raw asyncpg
- **asyncpg 0.30.x** — async Postgres driver (под SQLAlchemy)
- **PostgreSQL 16** (uuid-ossp + pgcrypto extensions)
- **Redis 7** — OTP rate-limiting, session data
- **Alembic 1.14.x** — миграции
- **Pydantic v2.10.x** — schemas и settings
- **pydantic-settings** — конфиг через `.env`
- **python-jose[cryptography]** — JWT (HS256)
- **Uvicorn** — ASGI server (port 3000)
- **httpx** — HTTP клиент для внешних API (OAuth, SMS, Anthropic)
- **boto3** — Yandex Cloud S3 (S3-совместимый)
- **Pillow** — image processing
- **redis[hiredis]** — Redis клиент
- **ruff 0.8.x** — linting + formatting
- **pytest + pytest-asyncio** — тесты

**AI**: только **Anthropic Claude** (`anthropic==0.42.*`, модель `claude-sonnet-4-5`) — и для scan (vision), и для chat/recommendations.  
`openai` есть в `requirements.txt` но **не используется**. Не подключать, не добавлять.

## Структура (packages/api-python/)

```
app/
├── main.py                  — FastAPI app + сборка всех router-ов
├── server.py                — Uvicorn entrypoint
├── seed.py / seed_articles.py
├── core/
│   ├── config.py            — Pydantic Settings (env vars / .env)
│   └── deps.py              — Auth зависимости: get_current_user_id, get_optional_user_id
├── db/
│   ├── session.py           — Async SQLAlchemy engine + AsyncSession factory
│   └── models.py            — ВСЕ ORM-модели в одном файле (21 модель)
├── modules/                 — по одной папке на feature
│   ├── auth/                — OTP (SMS.ru), JWT, OAuth (Telegram/Yandex/Apple/Google/VK)
│   ├── user/                — CRUD профиля
│   ├── scan/                — AI Vision скан (Anthropic Claude + MediaPipe)
│   ├── cosmetic_analysis/   — Анализ состава косметики
│   ├── recommendations/     — Персональные рекомендации
│   ├── routine/             — Рутина ухода (UserRoutine + RoutineCompletion)
│   ├── home/                — Виджеты домашнего экрана
│   ├── articles/            — Контентные статьи
│   ├── diary/               — Дневник кожи
│   ├── feed/                — Community feed
│   ├── chat/                — AI чат с Claude
│   ├── doctors/             — Каталог врачей
│   └── upload/              — S3 file uploads
└── services/
    ├── redis_client.py
    ├── storage.py           — S3 / Yandex Cloud
    └── weather.py           — Погода для контекста рутины

migrations/                  — Alembic versions
tests/                       — pytest integration tests
requirements.txt
pyproject.toml               — ruff config
alembic.ini
Dockerfile
```

## Структура модуля

Каждый `modules/<name>/` содержит:

```
modules/<name>/
├── __init__.py
├── router.py        — FastAPI router с эндпоинтами
├── schemas.py       — Pydantic request/response модели
└── service.py       — бизнес-логика (использует AsyncSession)
```

При добавлении нового feature — следовать этой структуре, не изобретать паттернов.

## Соглашения

### ORM (SQLAlchemy 2.0 async)

```python
from sqlalchemy import select
from app.db.models import User

async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
```

- `session.flush()` + `session.refresh()` после создания если нужен сгенерированный PK
- `await session.commit()` — только на границе эндпоинта, не внутри сервисов
- **Все модели в одном файле**: `app/db/models.py`. Не разносить по модулям.

### Pydantic v2

```python
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nickname: str
```

### ID и timestamps

- **UUID PK** везде через `uuid_pk()` helper (server_default = `uuid_generate_v4()`)
- **Timestamps**: `DateTime(timezone=True)`, `server_default=func.now()`. Никогда `datetime.utcnow()`.
- Все datetime в ответах API — UTC с timezone info

### Soft-delete

В текущих моделях **не реализован** (нет `deleted_at`). При необходимости — обсудить с CTO перед добавлением.

### Деньги / стоимость

Денежных транзакций в приложении нет. `cost_usd` в `ChatMessage` и `AiUsageLog` — учёт расходов AI в USD через `Numeric(10, 6)`. Не «в копейках», не float.

### Именование

- snake_case для всего Python кода
- Эндпоинты: `/{resource}` и `/{resource}/{id}` (REST-стиль)
- Request/response schemas: `UserOut`, `ScanRequest`, `AuthResponse` (PascalCase)

## API conventions

- Все маршруты: `/api/v1/<module>/...` (через `APIRouter(prefix="/api/v1")` в `main.py`)
- Response: прямо Pydantic schema, не wrapped. Ошибки через `HTTPException(status_code, detail=...)`
- Paginated lists: `?limit=N&offset=N` → `{"items": [...], "total": N}`
- Auth endpoint prefix: `/api/v1/auth/`

## Auth

- **OTP**: SMS.ru API, 4 цифры, TTL 5 мин, 3 попытки, 60 сек cooldown
- **JWT**: HS256, access 15 мин, refresh 30 дней, хэши в БД (`RefreshToken`)
- **OAuth providers**: Apple, Google, VK, Telegram, Yandex (все через `/auth/oauth/{provider}`)
- **Anonymous flow**: `anonymous_token` в теле запроса (scan без авторизации). Паттерн — в `modules/scan/router.py`
- **Dependency**: `get_current_user_id` → обязательный JWT; `get_optional_user_id` → JWT опционально

## AI integration — Anthropic Claude

```python
import httpx

# Прямой HTTP вызов (proxy support) — паттерн из scan/router.py
async with httpx.AsyncClient(transport=transport, timeout=60) as client:
    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": settings.anthropic_chat_model,   # "claude-sonnet-4-5"
            "max_tokens": 4000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": [...]}],
        },
    )
```

- Proxy: `settings.anthropic_proxy_url` (для обхода геоблокировки)
- Scan: передаёт изображение через `source.type: "url"` в content block
- Chat: стандартные text messages

**Никогда** не вызывать AI API с хардкодными ключами — только через `app.core.config.settings`.

## Миграции

```bash
# Создать миграцию
alembic revision --autogenerate -m "add_feature_to_users"

# Применить
alembic upgrade head
```

### Правила

1. Forward-only на практике. `downgrade()` писать для формальности, не полагаться на него.
2. **Никогда** не дропать колонку в той же миграции где добавляется замена. Ship replacement → deploy → backfill → drop в отдельной миграции.
3. Добавить NOT NULL на непустую таблицу: три шага (add NULL → backfill → set NOT NULL в трёх миграциях).
4. Индексы на существующих таблицах: `CREATE INDEX CONCURRENTLY` (вручную в migration, не через autogenerate).
5. Naming convention: автогенерит alembic, примеры существующих: `ad0b0cb32318_initial_schema.py`, `4c65b97a0a08_add_theme_to_users.py`

## Code style

- `ruff` (config в `pyproject.toml`)
- `from __future__ import annotations` в начале каждого нового файла
- Type hints обязательны на каждой функции
- Логирование: `logging.getLogger(__name__)`. Никогда не логировать phone, email, photo URL на INFO-уровне

## Тесты

```
tests/
├── conftest.py
├── test_auth.py
├── test_chat.py
├── test_diary.py
├── test_doctors.py
├── test_feed.py
├── test_health.py
├── test_profile.py
├── test_recommendations.py
├── test_scan.py
└── test_upload.py
```

- Integration tests через `httpx.AsyncClient` против реального Postgres
- Required coverage: happy path + минимум один error path + для anonymous-allowed эндпоинтов — anonymous token path
- CI поднимает Postgres 16 + Redis 7 как services (`.github/workflows/ci-cd.yml`)

## Работа в монорепе

- Python проект: `packages/api-python/`
- Локально: `cd packages/api-python && uvicorn app.main:app --reload --port 3000`
- Docker: `docker compose up -d api`
- Репо: `moy-kosmetolog`, рабочая папка `packages/api-python/`
- Ветки: `feat/<feature_id_short>/<slug>`, PR: `[<feature_id_short>] <task title>`
