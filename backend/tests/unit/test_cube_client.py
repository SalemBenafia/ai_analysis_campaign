"""Cube REST client: Continue-wait long-poll, tenancy JWT, failure modes."""
from __future__ import annotations

import httpx
import pytest
import respx
from jose import jwt

from app.core.settings import settings
from app.modules.semantic import cube_client
from app.modules.semantic.cube_client import CubeUnavailableError

LOAD_URL = f"{settings.CUBE_API_URL}/cubejs-api/v1/load"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "CUBEJS_API_SECRET", "x" * 32)
    monkeypatch.setattr(settings, "CUBE_LOAD_TIMEOUT", 3)


class TestSignToken:
    def test_token_carries_tenancy_context(self):
        token = cube_client.sign_token("user-1", ["ds_ab12cd34"])
        payload = jwt.decode(token, "x" * 32, algorithms=["HS256"])
        assert payload["user_id"] == "user-1"
        assert payload["dataset_cubes"] == ["ds_ab12cd34"]


class TestLoad:
    @respx.mock
    async def test_continue_wait_then_data(self):
        route = respx.post(LOAD_URL)
        route.side_effect = [
            httpx.Response(200, json={"error": "Continue wait"}),
            httpx.Response(200, json={"data": [{"ds.spend_sum": 5}]}),
        ]
        rows = await cube_client.load({"measures": []}, "u", ["ds"])
        assert rows == [{"ds.spend_sum": 5}]
        assert route.call_count == 2

    @respx.mock
    async def test_unreachable_raises_unavailable(self):
        respx.post(LOAD_URL).mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(CubeUnavailableError):
            await cube_client.load({"measures": []}, "u", ["ds"])

    @respx.mock
    async def test_5xx_raises_unavailable(self):
        respx.post(LOAD_URL).mock(return_value=httpx.Response(500, text="err"))
        with pytest.raises(CubeUnavailableError):
            await cube_client.load({"measures": []}, "u", ["ds"])

    @respx.mock
    async def test_4xx_is_a_query_error_not_fallback(self):
        respx.post(LOAD_URL).mock(
            return_value=httpx.Response(400, json={"error": "Access denied for cube: ds_x"})
        )
        with pytest.raises(ValueError, match="Access denied"):
            await cube_client.load({"measures": []}, "u", ["ds"])
