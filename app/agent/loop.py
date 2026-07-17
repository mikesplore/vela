"""Agent reconnect loop."""

from __future__ import annotations

import asyncio

from app.agent.local_auth import wait_for_local_service
from app.agent.pairing import refresh_ws_token
from app.agent.tunnel import tunnel
from app.utils.config import get_config


async def start_agent_loop() -> None:
    """Main agent loop.
    
    Expects the device to be paired (AGENT_ID + RELAY_SECRET in .env).
    Uses the refresh token endpoint (POST /agents/{id}/ws-token) for connection.
    
    The /register endpoint should only be used by setup.sh for initial registration.
    """
    config = get_config()
    await wait_for_local_service()

    if not config.vps_url:
        raise RuntimeError("VPS_URL must be set before starting vela-agent")

    if not config.relay_secret:
        raise RuntimeError(
            "Agent is not paired yet. Run `vela --setup` to complete pairing."
        )

    backoff = 5
    max_backoff = 60

    while True:
        try:
            token = await asyncio.to_thread(refresh_ws_token)
            print(f"Refreshed ws_token: {token[:10]}...")
            await tunnel(token)
            # Tunnel exited cleanly — reset backoff
            backoff = 5
        except Exception as exc:
            print(f"Agent loop error: {exc}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
