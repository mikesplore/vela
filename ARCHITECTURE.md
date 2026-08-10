# Vela — Architecture Guide

## 1. Purpose & Role

Vela is the **on-device Linux agent** in the ecosystem: a FastAPI service (`app/main.py`) that runs on the user's PC and exposes desktop control (filesystem, audio, display, processes, power, network, monitoring, etc.) as a REST API, plus an LLM assistant with tool-calling. Its specific role is to be the **execution endpoint** — it never initiates inbound connections; it either serves local HTTP on `127.0.0.1:8765` or maintains an **outbound WebSocket tunnel** to the velavps relay so remote clients (vela-android) can reach it. It is the only repo that touches the actual Linux desktop.

## 2. Key Modules & Responsibilities

- **`app/routers/` + `app/services/`**: Thin HTTP handlers and business logic per feature (audio, display, docker, filesystem, monitoring, network, processes, security, spotify, etc.), loaded capability-gated via `app/routers/registry.py`.
- **`app/agent/`**: The outbound tunnel agent — `tunnel.py` maintains the WebSocket to velavps and forwards relayed requests to the local API; `pairing.py` handles QR/code onboarding; `local_auth.py` mints/caches the local JWT used to authenticate forwarded requests.
- **`app/services/assistant/`**: LLM assistant — `helpers.py` (two-stage domain→tool planner + Fireworks streaming), `tool_exec.py` (tool execution), `safety.py` (risk tiers + PIN gate), `workflow.py` (check-before-act stages).
- **`app/services/gatekeeper/` + `app/routers/gatekeeper_proxy.py`**: Proxies the external Gatekeeperd admin API (`/api/admin/*`) through Vela so remote clients can reach it via the relay.
- **`app/db/`**: SQLite-backed audit log, pending-action store, and capability persistence.

## 3. External Interfaces

**Incoming (consumed by velavps / vela-android / external agents):**
- **REST API** (`app/routers/*`): all desktop-control endpoints. Auth: JWT bearer (HS256, `app/auth.py`); data: JSON. Consumed directly by vela-android and by the tunnel.
- **WebSocket tunnel** (`app/agent/tunnel.py`): receives `forward_request` frames from velavps, relays responses (`forward_response`, `forward_response_start/chunk/end` for SSE/streams). Auth: `ws_token` in URL; forwarded requests re-authenticated with a local JWT.
- **SSE** (`/assistant/stream`): streaming assistant responses, including `gate` events for action confirmation.

**Outgoing (calls made to velavps / vela-mcp / third parties):**
- **velavps pairing/relay REST** (`app/agent/pairing.py`, `app/services/push.py`): `POST /agents/register/start|activate`, `GET /agents/register/status`, `POST /agents/{id}/ws-token`, `POST /relay/{agent_id}/push/devices`, `DELETE /relay/{agent_id}/push/devices`, `POST /agents/{agent_id}/push/send`. Auth: `X-Secret: <RELAY_SECRET>`; data: JSON.
- **Gatekeeperd admin API** (`app/services/gatekeeper/client.py`): proxied REST, JSON, bearer-token auth.
- **Fireworks AI** (`app/services/assistant/helpers.py`): `POST /chat/completions` (JSON + SSE), Bearer API key.
- **Resend** (email alerts), **Spotify API** (`app/utils/spotify_client.py`), **ipify/ipinfo** (public IP/geo).

## 4. Multitenancy & Security Model

Vela is a **single-user, single-agent** service — there is no tenant isolation at the code level. Isolation is delegated to the velavps relay, which scopes agents by `agent_id` and issues per-agent `RELAY_SECRET`/`ws_token`. Local security: JWT bearer auth (bcrypt-hashed password, `app/auth.py`), per-route rate limiting (`app/rate_limiter.py`), filesystem allowlist (`allowed_base_dirs`), and a pending-action gate where high-risk assistant tools require yes/no or PIN confirmation (`app/services/assistant/safety.py`). Push titles are prefixed with the agent label for multi-agent phones (`app/services/push.py`).

## 5. Configuration & Environment Variables

- `VPS_URL`, `AGENT_ID`, `RELAY_SECRET`, `AGENT_CREDENTIAL`: velavps relay identity/auth (`app/utils/config.py`).
- `GATEKEEPER_BASE_URL`, `GATEKEEPER_EMAIL`, `GATEKEEPER_PASSWORD`, `GATEKEEPER_TOKEN`: Gatekeeperd admin API credentials for the proxy.
- `FIREWORKS_API_KEY`, `FIREWORKS_MODEL`, `FIREWORKS_API_URL`: LLM assistant provider.
- `RESEND_API_KEY`, `RECIPIENT_EMAIL`: email alert delivery.
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`: Spotify OAuth.
- `MCP_SERVER_URL`: public vela-mcp URL used by `vela --mcp` to build the MCP link.
- `LOCAL_SERVICE_URL`, `LOCAL_SERVICE_USERNAME`, `LOCAL_SERVICE_PASSWORD`: local API credentials the tunnel uses to authenticate forwarded requests.
- `assistant_action_pin`, `assistant_action_timeout_seconds`: PIN gate for high-risk assistant actions.

## 6. Integration Contract with Other Repos

**Vela EXPECTS from:**
- **velavps**: pairing endpoints (`/agents/register/*`), `ws-token` minting, WebSocket tunnel relay, push device registration/send endpoints, and per-agent secret scoping.
- **vela-mcp**: a public `MCP_SERVER_URL` (used only to build the MCP connection link).
- **vela-android**: pairing completion (code/PIN) and JWT-authenticated REST calls against the relayed API.

**Vela PROVIDES to:**
- **velavps**: outbound tunnel connection, heartbeat, `X-Secret`-authenticated push device registration/send, and relay status events (`app/services/relay_status.py`).
- **vela-mcp**: the local REST API surface that MCP tools wrap (via the relay).
- **vela-android**: the full desktop-control REST API and SSE assistant stream, reachable through the relay.