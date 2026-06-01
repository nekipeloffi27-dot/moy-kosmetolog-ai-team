# Agent Skills

Каждый агент получает релевантные SKILL.md в системный промпт.

## Структура

```
skills/
├── common/          # подключается ВСЕМ агентам
│   └── <name>/
│       └── SKILL.md
├── designer/        # только Designer
├── cto_tasking/     # только CTO tasking
├── cto_review/      # только CTO review
├── pm/              # только PM
├── backend/         # dev-sandbox: backend
├── frontend_web/    # dev-sandbox: frontend web
└── frontend_mobile/ # dev-sandbox: frontend mobile
```

## Как добавить скилл

1. Создай папку `skills/<role>/<skill-name>/`
2. Положи туда `SKILL.md` с содержимым скилла
3. Перезапускать бот не нужно — скиллы читаются при каждом запуске агента

## Как работает для API-агентов (designer / cto_tasking / cto_review / pm)

`load_skills_for(role)` читает все `SKILL.md` из `common/` и `<role>/`,
оборачивает каждый в `<skill name="...">...</skill>` и добавляет в системный промпт.

## Как работает для dev-агентов (sandbox)

Папки `common/` и `<role>/` монтируются в контейнер как
`/root/.claude/skills/common/` и `/root/.claude/skills/<role>/`.
Claude Code подхватывает их автоматически.

## Флаг SKILLS_ENABLED

Установи `SKILLS_ENABLED=false` в `.env` чтобы полностью отключить скиллы.
