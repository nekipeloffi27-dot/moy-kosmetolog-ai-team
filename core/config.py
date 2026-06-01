"""Application configuration. Loaded from environment variables (or .env)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ─── Telegram bots ───
    telegram_pm_bot_token:       str = Field(..., alias="TELEGRAM_PM_BOT_TOKEN")
    telegram_designer_bot_token: str = Field(..., alias="TELEGRAM_DESIGNER_BOT_TOKEN")
    telegram_cto_bot_token:      str = Field(..., alias="TELEGRAM_CTO_BOT_TOKEN")
    telegram_backend_bot_token:  str = Field(..., alias="TELEGRAM_BACKEND_BOT_TOKEN")
    telegram_frontend_bot_token: str = Field(..., alias="TELEGRAM_FRONTEND_BOT_TOKEN")

    telegram_allowed_user_ids: str = Field("", alias="TELEGRAM_ALLOWED_USER_IDS")
    telegram_feature_group_id: int = Field(0, alias="TELEGRAM_FEATURE_GROUP_ID")

    # ─── Anthropic ───
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    anthropic_proxy_url: str = Field("", alias="ANTHROPIC_PROXY_URL")
    model_pm: str = Field("claude-opus-4-7", alias="MODEL_PM")
    model_designer: str = Field("claude-opus-4-7", alias="MODEL_DESIGNER")
    model_cto: str = Field("claude-opus-4-7", alias="MODEL_CTO")
    model_cto_review: str = Field("claude-opus-4-7", alias="MODEL_CTO_REVIEW")
    model_backend_dev: str = Field("claude-sonnet-4-6", alias="MODEL_BACKEND_DEV")
    model_frontend_web_dev: str = Field("claude-sonnet-4-6", alias="MODEL_FRONTEND_WEB_DEV")
    model_frontend_mobile_dev: str = Field("claude-sonnet-4-6", alias="MODEL_FRONTEND_MOBILE_DEV")

    # ─── GitHub ───
    github_token: str = Field("", alias="GITHUB_TOKEN")
    github_owner: str = Field("", alias="GITHUB_OWNER")
    github_repo_backend: str = Field("moy-kosmetolog#packages/api-python", alias="GITHUB_REPO_BACKEND")
    github_repo_pwa: str = Field("moy-kosmetolog#packages/web", alias="GITHUB_REPO_PWA")
    github_repo_landing: str = Field("moy-kosmetolog#packages/landing", alias="GITHUB_REPO_LANDING")
    github_repo_mobile: str = Field("moy-kosmetolog#packages/mobile", alias="GITHUB_REPO_MOBILE")
    github_default_branch: str = Field("main", alias="GITHUB_DEFAULT_BRANCH")
    github_merge_method: str = Field("squash", alias="GITHUB_MERGE_METHOD")

    # ─── Database ───
    postgres_user: str = Field("ai_team", alias="POSTGRES_USER")
    postgres_password: str = Field(..., alias="POSTGRES_PASSWORD")
    postgres_db: str = Field("ai_team", alias="POSTGRES_DB")
    postgres_host: str = Field("db", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")

    # ─── Budget ───
    default_budget_cap_cents: int = Field(500, alias="DEFAULT_BUDGET_CAP_CENTS")

    # ─── Sandbox ───
    sandbox_workspace: str = Field("/var/ai-team-workspace", alias="SANDBOX_WORKSPACE")
    dev_agent_timeout: int = Field(1800, alias="DEV_AGENT_TIMEOUT")
    dev_sandbox_image: str = Field("ai-team-dev-sandbox:latest", alias="DEV_SANDBOX_IMAGE")
    dev_max_turns: int = Field(20, alias="DEV_MAX_TURNS")

    # ─── Deploy (M6) ───
    # Shell command run on the AI-team VM to deploy to the dev stand.
    # Most realistic: SSH into the moy-kosmetolog dev VM and pull+restart.
    # Leave empty to skip deploy and transition straight to TESTING.
    deploy_dev_command:  str = Field("", alias="DEPLOY_DEV_COMMAND")
    deploy_prod_command: str = Field("", alias="DEPLOY_PROD_COMMAND")
    deploy_timeout:      int = Field(900, alias="DEPLOY_TIMEOUT")  # 15 min

    # ─── Ops (CTO diagnostics mode) ───
    # Comma-separated container names allowed for `docker logs` in ops mode.
    ops_allowed_containers: str = Field(
        "ai-team-bot,ai-team-db,ai-team-redis",
        alias="OPS_ALLOWED_CONTAINERS",
    )
    # Comma-separated SSH hosts allowed for read-only remote commands.
    # Leave empty to disable SSH ops entirely.
    ops_allowed_ssh_hosts: str = Field("", alias="OPS_ALLOWED_SSH_HOSTS")
    # Timeout (seconds) for shell commands run via /apply_fix.
    ops_apply_fix_timeout: int = Field(120, alias="OPS_APPLY_FIX_TIMEOUT")

    # ─── Codebase snapshot (read-only for Designer / CTO tasking) ───
    # Clone the monorepo here manually; agents read it to avoid hallucinating components.
    # refresh_snapshot() runs `git fetch && git reset --hard origin/main` before each use.
    codebase_snapshot_dir: str = Field(
        "/var/ai-team-workspace/codebase-snapshot",
        alias="CODEBASE_SNAPSHOT_DIR",
    )

    # ─── Designer ───
    # Limits codebase tool-use iterations to control cost on edit tasks.
    designer_max_tool_iterations: int = Field(4, alias="DESIGNER_MAX_TOOL_ITERATIONS")

    # ─── Skills ───
    skills_enabled: bool = Field(True, alias="SKILLS_ENABLED")
    # Path to skills root; mounted into sandbox and read by API agents.
    # In production: mount skills/ volume here. Locally: falls back to repo skills/.
    skills_dir: str = Field("/opt/ai-team/skills", alias="SKILLS_DIR")

    # ─── Logging ───
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def allowed_user_ids(self) -> set[int]:
        if not self.telegram_allowed_user_ids:
            return set()
        return {int(x.strip()) for x in self.telegram_allowed_user_ids.split(",") if x.strip()}

    def parse_repo(self, repo_str: str) -> tuple[str, str]:
        if "#" in repo_str:
            repo, subdir = repo_str.split("#", 1)
            return repo, subdir
        return repo_str, ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
