# moy-kosmetolog

## Что такое продукт

AI-платформа по уходу за кожей. Пользователь делает селфи — ИИ анализирует состояние кожи, выставляет балл, накладывает маску дефектов и генерирует персональную рутину ухода. Дополнительно: дневник кожи, AI-чат по уходу, анализ состава косметики, лента сообщества, каталог врачей-косметологов. Аудитория — женщины, которым важно наблюдать за кожей в динамике, а не получить разовую консультацию.

Продукт — не клинический портал, не booking-платформа, не SaaS для мастеров. Только пользовательское wellness-приложение.

## Стек одной строкой

Next.js 16 (PWA) / FastAPI 0.115 / PostgreSQL 16 + Redis 7 / Anthropic Claude (Sonnet) / Yandex Cloud

## Архитектура — монорепо

```
moy-kosmetolog/
├── docker-compose.yml       — все сервисы: postgres, redis, api, web
├── nginx.conf / nginx/      — reverse proxy (systemd nginx на сервере)
├── .github/workflows/       — CI: lint → test → deploy (SSH на Yandex Cloud)
└── packages/
    ├── api-python/          — Backend: FastAPI + SQLAlchemy 2.0 async
    ├── web/                 — PWA: Next.js 16 + Tailwind 4 + Halo DS
    ├── api/                 — Пустая заглушка (TypeScript), ничего не планируется
    ├── admin-web/           — Пустая папка; admin живёт в отдельном репо moy-kosmetolog-admin
    └── mobile/              — Пустая папка; мобилка не разрабатывается
```

Когда задача `backend` → работаем в `packages/api-python/`.  
Когда задача `frontend_web` → работаем в `packages/web/`.  
Задачи типа `frontend_mobile` — отклонять, мобилка не ведётся.

## Доменная модель

Основные сущности (из `packages/api-python/app/db/models.py`):

| Сущность | Описание |
|---|---|
| `User` | UUID PK, `auth_provider` enum, phone/email опционально, `is_doctor` flag |
| `SkinProfile` | 1:1 с User; `skin_type`, `concerns[]`, `allergies[]`, `age`, `gender`, `city` |
| `OtpCode` | SMS OTP (4 цифры, 5 мин TTL) |
| `RefreshToken` | хэши refresh-токенов |
| `ScanResult` | скан лица: `overall_score` (0–100), `analysis` (JSONB), `photo_url` (S3) |
| `AiRecommendation` | рекомендации по категориям: skincare/food/sport/sleep/mental |
| `DiaryEntry` | запись дневника: `mood_score` 0–4, `products[]`, `tags[]`, `entry_date` |
| `DiaryPhoto` | фото к записи дневника, с face_zone |
| `Post` | community feed: article/story/question/before_after |
| `Comment` | вложенные комментарии (parent_id nullable) |
| `Like` | unique (post_id, user_id) |
| `ChatSession` | AI чат-сессия: mode = faq/scan_explain/recommendation |
| `ChatMessage` | сообщение: sender = user/ai, `tokens_used`, `cost_usd` (Numeric 10,6) |
| `Clinic` | клиника с координатами |
| `Doctor` | врач: `rating` (Numeric 3,2), `services` (JSONB), `is_verified` |
| `Review` | отзыв на врача: rating 1–5 |
| `AiUsageLog` | лог расходов AI (tokens, `cost_usd` Numeric 10,6 в USD) |
| `UserRoutine` | AI-сгенерированная рутина ухода (JSONB), `chosen_products` |
| `RoutineCompletion` | факт выполнения шага рутины (morning/evening, дата) |
| `Article` | контентные статьи (виджет "Для тебя") |
| `ArticleRead` | факт прочтения статьи |

**Нет** сущностей Booking, Payment, Slot, Service/Procedure. Платёжная логика в продукте отсутствует.

## Главные user flows

1. **Scan-first**: анонимный пользователь → загружает фото → получает `overall_score` + overlay дефектов + рутина. После регистрации скан привязывается через `/scan/{id}/claim`.
2. **Онбординг**: регистрация (OTP по телефону или OAuth) → заполнение `SkinProfile` → первый скан.
3. **Дневник**: ежедневные записи с фото, mood_score и тегами. Стрик и статистика через `/diary/stats`.
4. **AI чат**: Claude отвечает на вопросы по уходу за кожей в трёх режимах: faq, scan_explain, recommendation.
5. **Community feed**: посты, лайки, комментарии.
6. **Каталог врачей**: поиск по городу и рейтингу, отзывы.
7. **Домашний экран**: виджеты — балл кожи из последнего скана, прогресс рутины, статья "Для тебя", погода.

## Production environment

- Платформа: Yandex Cloud (один VPS/VM)
- Deploy: GitHub Actions → SSH → `git reset --hard origin/main` → `docker compose up -d --build`
- Домен: `moikosmetolog.ru`
- Сервисы в Docker: API (port 3000, внутренний), Web/PWA (port 3001, внутренний), Admin (порт 3002, отдельный репо)
- nginx системный (не в compose) в роли reverse proxy
- Storage: Yandex Object Storage (S3-совместимый), бакет `moy-kosmetolog-media`
- CI: lint (ruff) → test (pytest + real Postgres 16 + Redis 7) → deploy (только push в main)

## Тон / голос

Русский, на «ты». Тёплый, знающий, не корпоративный. Подробнее — в `DESIGN_SYSTEM.md`.

## Инварианты для агентов

1. **Все datetime** хранятся как `TIMESTAMPTZ` (`DateTime(timezone=True)`) с `server_default=func.now()`. На уровне Python — `datetime` с tz-info. `datetime.utcnow()` запрещён.
2. **UUID PK** везде (`uuid_generate_v4()` через Postgres extension).
3. **PII** (phone, email, photo URLs): никогда не логировать на INFO-уровне. Только DEBUG.
4. **Телефоны** в формате E.164 (`+7XXXXXXXXXX`).
5. **Anonymous flows**: `anonymous_token` (UUID в localStorage) обязателен для scan-эндпоинтов без авторизации. Паттерн — в `modules/scan/router.py`.
6. **AI SDK**: scan и chat используют **Anthropic Claude** (`claude-sonnet-4-5`). OpenAI в `requirements.txt` не используется — не подключать и не добавлять.
7. **Soft-delete** в текущих моделях **не реализован** (нет `deleted_at`). При необходимости удаления — обсудить с CTO перед реализацией.
8. **Денежных транзакций нет**. `cost_usd` в `ChatMessage` и `AiUsageLog` — учёт расходов AI в USD через `Numeric(10, 6)`.
9. Мобильная разработка не ведётся. Задачи `frontend_mobile` — отклонять.
10. Изменения API-контракта → сначала CTO tasking, потом реализация.
