from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_spotify_callback_success_returns_html(monkeypatch):
    monkeypatch.setattr("app.routers.spotify.complete_spotify_link", lambda code: None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/spotify/callback", params={"code": "auth-code"})

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Spotify linked" in response.text
    assert "Sign-in succeeded" in response.text
    assert "access_token" not in response.text


@pytest.mark.asyncio
async def test_spotify_callback_alias_works_without_auth(monkeypatch):
    monkeypatch.setattr("app.routers.spotify.complete_spotify_link", lambda code: None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/callback", params={"code": "auth-code"})

    assert response.status_code == 200
    assert "Spotify linked" in response.text


@pytest.mark.asyncio
async def test_spotify_callback_missing_code_returns_html_error():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/spotify/callback")

    assert response.status_code == 400
    assert "Spotify sign-in failed" in response.text
    assert "Missing authorization code" in response.text


@pytest.mark.asyncio
async def test_spotify_callback_provider_error_returns_html():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/spotify/callback",
            params={"error": "access_denied", "error_description": "User denied access"},
        )

    assert response.status_code == 400
    assert "Spotify sign-in failed" in response.text
    assert "User denied access" in response.text


@pytest.mark.asyncio
async def test_spotify_callback_exchange_failure_returns_html(monkeypatch):
    def boom(_code: str) -> None:
        raise ValueError("bad code")

    monkeypatch.setattr("app.routers.spotify.complete_spotify_link", boom)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/spotify/callback", params={"code": "bad"})

    assert response.status_code == 400
    assert "Could not finish linking" in response.text
    assert "bad code" in response.text


def test_oauth_result_page_escapes_html():
    from app.services.spotify import oauth_result_page

    page = oauth_result_page(
        title="<script>alert(1)</script>",
        message='fail & "x"',
        ok=False,
    )
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "&amp;" in page
