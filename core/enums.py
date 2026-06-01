"""Python enums mirroring DB enums. Keep these in sync with migration 0001."""
from enum import StrEnum


class FeatureState(StrEnum):
    CLARIFICATION = "clarification"
    DESIGN_PENDING = "design_pending"
    DESIGN_REVIEW = "design_review"
    TASKS_PENDING = "tasks_pending"
    CODING = "coding"
    REVIEW = "review"
    DEV_DEPLOYED = "dev_deployed"
    TESTING = "testing"
    PROD_READY = "prod_ready"
    PROD_DEPLOYED = "prod_deployed"
    DESIGN_DONE = "design_done"
    BLOCKED = "blocked"
    FAILED = "failed"


class TaskType(StrEnum):
    BACKEND = "backend"
    FRONTEND_WEB = "frontend_web"
    FRONTEND_MOBILE = "frontend_mobile"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PR_OPEN = "pr_open"
    MERGED = "merged"
    BLOCKED = "blocked"


# Human-readable labels for Telegram messages
FEATURE_STATE_LABELS_RU: dict[FeatureState, str] = {
    FeatureState.CLARIFICATION:   "💬 PM уточняет задачу",
    FeatureState.DESIGN_PENDING:  "🎨 Дизайнер думает",
    FeatureState.DESIGN_REVIEW:   "👀 Жду твой ОК по дизайну",
    FeatureState.TASKS_PENDING:   "📋 CTO режет на задачи",
    FeatureState.CODING:          "⌨️ Разработчики кодят",
    FeatureState.REVIEW:          "🔍 CTO ревьюит PR",
    FeatureState.DEV_DEPLOYED:    "🚀 Выкачено на dev",
    FeatureState.TESTING:         "🧪 Жду твою проверку",
    FeatureState.PROD_READY:      "✅ Готово к проду",
    FeatureState.PROD_DEPLOYED:   "🎉 В проде",
    FeatureState.DESIGN_DONE:     "🖼 Дизайн готов",
    FeatureState.BLOCKED:         "⛔ Заблокировано — нужен ты",
    FeatureState.FAILED:          "💥 Упало",
}
