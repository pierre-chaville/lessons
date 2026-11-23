"""Publisher guards on user management fail closed when Clerk cannot be reached."""

from collections.abc import Callable

from fastapi import FastAPI
import httpx
import pytest

import auth
from routers import users as users_router

ClerkHandler = Callable[[httpx.Request], httpx.Response]


def _client(monkeypatch: pytest.MonkeyPatch, role: str, clerk: ClerkHandler) -> tuple[httpx.AsyncClient, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        return clerk(request)

    real_client = httpx.Client
    monkeypatch.setattr(
        users_router.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(users_router, "_clerk_headers", lambda: {"Authorization": "Bearer test"})

    app = FastAPI()
    app.include_router(users_router.router)
    app.dependency_overrides[auth.require_auth] = lambda: {"sub": "caller", "role": role}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return client, calls


def _user(role: str) -> httpx.Response:
    return httpx.Response(200, json={"id": "user_1", "public_metadata": {"role": role}})


def _clerk_down(request: httpx.Request) -> httpx.Response:
    if request.method == "GET":
        return httpx.Response(503, text="unavailable")
    return httpx.Response(200, json={"id": "user_1", "public_metadata": {"role": "reader"}})


def _clerk_unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("unreachable", request=request)


@pytest.mark.anyio
@pytest.mark.parametrize("clerk", [_clerk_down, _clerk_unreachable])
async def test_role_change_blocked_when_target_cannot_be_loaded(monkeypatch, clerk) -> None:
    client, calls = _client(monkeypatch, "publisher", clerk)
    async with client:
        response = await client.patch("/users/user_1/role", json={"role": "reader"})
    assert response.status_code == 502
    assert not any(call.startswith("PATCH") for call in calls)


@pytest.mark.anyio
@pytest.mark.parametrize("clerk", [_clerk_down, _clerk_unreachable])
async def test_delete_blocked_when_target_cannot_be_loaded(monkeypatch, clerk) -> None:
    client, calls = _client(monkeypatch, "publisher", clerk)
    async with client:
        response = await client.delete("/users/user_1")
    assert response.status_code == 502
    assert not any(call.startswith("DELETE") for call in calls)


@pytest.mark.anyio
async def test_publisher_cannot_demote_or_delete_admin(monkeypatch) -> None:
    client, calls = _client(monkeypatch, "publisher", lambda request: _user("admin"))
    async with client:
        demote = await client.patch("/users/user_1/role", json={"role": "reader"})
        delete = await client.delete("/users/user_1")
    assert demote.status_code == 403
    assert delete.status_code == 403
    assert all(call.startswith("GET") for call in calls)


@pytest.mark.anyio
async def test_unknown_user_returns_404(monkeypatch) -> None:
    client, _ = _client(monkeypatch, "publisher", lambda request: httpx.Response(404, json={}))
    async with client:
        response = await client.delete("/users/missing")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_publisher_can_delete_non_admin(monkeypatch) -> None:
    def clerk(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _user("editor")
        return httpx.Response(200, json={"deleted": True})

    client, calls = _client(monkeypatch, "publisher", clerk)
    async with client:
        response = await client.delete("/users/user_1")
    assert response.status_code == 204
    assert calls == ["GET /v1/users/user_1", "DELETE /v1/users/user_1"]
