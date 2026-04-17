from __future__ import annotations

from httpx import AsyncClient
import pytest

pytestmark = pytest.mark.requires_db


async def test_system_health_endpoints(client: AsyncClient) -> None:
    health_response = await client.get("/healthz")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}

    readiness_response = await client.get("/readyz")
    assert readiness_response.status_code == 200
    assert readiness_response.json() == {"status": "ok", "database": "ok"}
