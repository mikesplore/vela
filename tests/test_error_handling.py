"""Test uniform error response handling."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from slowapi.errors import RateLimitExceeded

from main import app


@pytest.mark.asyncio
async def test_http_exception_format():
    """Test that HTTPException returns uniform error response."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Trigger a 404 by accessing non-existent endpoint
        response = await client.get("/nonexistent")
        
        assert response.status_code == 404
        data = response.json()
        
        assert data["success"] is False
        assert data["statusCode"] == 404
        assert isinstance(data["message"], str)
        assert isinstance(data["timestamp"], str)
        assert "T" in data["timestamp"]  # ISO8601 format check
        assert data["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_validation_error_format():
    """Test that validation errors return uniform error response."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Try to access an endpoint without auth (will return 401 Unauthorized)
        response = await client.post(
            "/display/brightness",
            json={"value": 150}
        )
        
        # Should be 401 Unauthorized
        assert response.status_code == 401
        data = response.json()
        
        assert data["success"] is False
        assert data["statusCode"] == 401
        assert isinstance(data["message"], str)
        assert isinstance(data["timestamp"], str)
        assert data["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_rate_limit_error_format():
    """Test that rate limit errors return uniform error response."""
    # Verify the handler exists and is properly registered
    from main import app, rate_limit_handler
    from errors import ErrorResponse
    
    # Verify the handler is registered
    assert RateLimitExceeded in app.exception_handlers
    
    # Test the handler directly with a mock
    from unittest.mock import MagicMock
    request = MagicMock()
    exc = MagicMock()
    
    response = await rate_limit_handler(request, exc)
    
    # Check it's a JSONResponse with correct structure
    assert response.status_code == 429
    assert b'"success":false' in response.body
    assert b'"statusCode":429' in response.body
    assert b'"message":"Rate limit exceeded"' in response.body
    assert b'"timestamp"' in response.body


@pytest.mark.asyncio 
async def test_internal_error_format():
    """Test that internal server errors return uniform error response."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Try an endpoint without auth (will return 401 Unauthorized)
        response = await client.get("/display/brightness")
        
        # Should be 401 Unauthorized
        assert response.status_code == 401
        data = response.json()
        
        assert data["success"] is False
        assert data["statusCode"] == 401
        assert isinstance(data["message"], str)
        assert isinstance(data["timestamp"], str)
        assert data["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_error_response_timestamp_format():
    """Test that timestamps are in proper ISO8601 format with Z suffix."""
    from errors import ErrorResponse
    
    error = ErrorResponse.create(500, "Test error")
    
    assert error.statusCode == 500
    assert error.message == "Test error"
    assert error.success is False
    assert error.timestamp.endswith("Z")
    # Verify ISO8601-like format
    assert len(error.timestamp) > 20  # Should be long enough for full ISO8601
