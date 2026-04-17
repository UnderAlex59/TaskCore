from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from alembic import command

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://app_user:app_pass@localhost:5432/taskplatform_test",
)

os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_value_that_is_long_enough_123456789")
os.environ.setdefault("LLM_SETTINGS_ENCRYPTION_KEY", "llm_test_runtime_secret_key")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("ALLOWED_ORIGINS", '["http://localhost:5173"]')

from app.core.database import engine  # noqa: E402
from main import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TRUNCATE_TARGETS = [
    "audit_events",
    "llm_request_logs",
    "llm_agent_overrides",
    "llm_runtime_settings",
    "llm_provider_configs",
    "change_proposals",
    "messages",
    "task_attachments",
    "tasks",
    "custom_rules",
    "project_members",
    "projects",
    "refresh_tokens",
    "users",
]
DB_MARKER = "requires_db"
_DB_PREPARED = False


def apply_migrations() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(config, "head")


@pytest_asyncio.fixture(autouse=True)
async def manage_database(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    if request.node.get_closest_marker(DB_MARKER) is None:
        yield
        return

    global _DB_PREPARED
    if not _DB_PREPARED:
        apply_migrations()
        _DB_PREPARED = True

    await engine.dispose()
    yield
    truncate_sql = f"TRUNCATE TABLE {', '.join(TRUNCATE_TARGETS)} RESTART IDENTITY CASCADE"
    async with engine.begin() as connection:
        await connection.execute(text(truncate_sql))
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
