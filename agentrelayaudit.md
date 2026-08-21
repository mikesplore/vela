# Agent–Relay Connection Flow Audit

**Date:** 2026-08-21  
**Scope:** Local Vela agent (`app/agent/*`) and companion VPS relay (`/home/mike/PycharmProjects/velavps`) WebSocket tunnel, liveness, reconnect, request waiting, and response correlation.  
**Method:** Static audit of both codebases and existing tunnel tests. No packet capture or production relay logs were available.

## Executive summary

The tunnel is not purely idle. The agent sends a JSON heartbeat every 30 seconds and the WebSocket client sends protocol-level ping frames every 20 seconds. The relay receives the JSON heartbeat and updates `last_seen`, so a healthy connection should remain active even without client requests.

The main failure is after a disconnect:

1. The relay keeps an `AgentConnection` object with `websocket = None`.
2. A client request arrives.
3. `Forwarder._resolve_agent()` returns that existing object immediately instead of waiting for reconnection.
4. `forward()` returns `503 Agent is not connected`.
5. The agent reconnects shortly afterwards, but the original request has already failed.

The relay only waits for reconnection when no in-memory `AgentConnection` exists. This is the direct cause of the reported behavior.

There are also two serious lifecycle defects: an old socket can clear a newer replacement socket, and requests already pending during a disconnect are failed without safe queue/replay semantics.

## Current flow

```text
vela-agent.service
  -> POST /agents/{id}/ws-token with X-Secret
  -> ws(s)://relay/tunnel?agent_id=...&token=...
  -> relay validates short-lived token and registers WebSocket
  -> agent sends JSON heartbeat every 30s
  -> relay sends forward_request frames
  -> agent calls local http://127.0.0.1:8765
  -> agent sends forward_response or response_start/chunk/end
  -> relay resolves request_id and returns HTTP response
```

### Agent side

- `app/agent/loop.py:24-49` refreshes a WebSocket token, connects, and reconnects with exponential backoff from 5 to 60 seconds.
- `app/agent/tunnel.py:336-343` uses `ping_interval=20`, `ping_timeout=20`, and `close_timeout=10`.
- `app/agent/tunnel.py:347-353` waits for relay application messages with `RELAY_READ_TIMEOUT`, default 300 seconds.
- `app/agent/tunnel.py:393-403` sends `{"type":"heartbeat"}` every 30 seconds.
- `app/agent/tunnel.py:366` awaits each forwarded request inline, blocking receipt of later application frames until the local request finishes.

### Relay side

- `/home/mike/PycharmProjects/velavps/app/routers/vela_relay.py:293-355` validates the token, accepts the socket, registers it, and receives JSON messages.
- Heartbeats call `agent.touch()` at `vela_relay.py:313-315`.
- Response frames resolve `pending_responses` or `pending_streams` by `request_id`.
- `/home/mike/PycharmProjects/velavps/app/services/vela_forwarder.py:38-57` waits for a connection only when the registry has no agent object.
- `VPSSettings.agent_connect_wait_seconds` defaults to 8 seconds.

## Findings

### AR-01 — Existing disconnected agent records bypass reconnect waiting

**Severity:** Critical reliability  
**Confidence:** Confirmed by code  
**Locations:** `velavps/app/services/vela_forwarder.py:38-57`, `vela_forwarder.py:168-180`

`_resolve_agent()` checks only whether an object exists. After a normal disconnect, `AgentRegistry.remove_websocket_connection()` retains the object and sets `websocket = None`. The next request therefore skips `_wait_for_agent_connection()` and reaches `forward()` with no transport, which returns `503` immediately.

**Fix:** Wait whenever there is no usable transport, not only when the registry object is absent:

```text
agent exists + websocket connected       -> return immediately
agent exists + websocket disconnected    -> wait for connected state
agent missing but DB record exists       -> wait for connected state
agent missing and DB record absent       -> 404
```

Use a per-agent `asyncio.Event`/condition signaled by socket registration rather than 250 ms polling. Revalidate the socket immediately before sending.

### AR-02 — No durable pending-request queue during reconnect

**Severity:** High reliability  
**Confidence:** Confirmed by code  
**Locations:** `vela_forwarder.py:197-236`, `vela_agent_registry.py:120-149`

Forward requests are stored only in in-memory futures. On disconnect, the registry sets pending futures to `RuntimeError("Agent connection closed")`, clears them, and terminates stream queues. Requests arriving while the agent reconnects have no queue and must be retried by the client.

Automatic replay is unsafe for arbitrary POST/DELETE operations because the original request may have reached the local agent before the tunnel failed.

**Fix:** Queue only requests that have not yet been dispatched. After dispatch, return a distinct gateway error on disconnect unless the request carries an idempotency key and is explicitly replayable. Bound queue size and wait time.

### AR-03 — Stale disconnect handler can unregister a newer socket

**Severity:** High  
**Confidence:** Confirmed by code  
**Locations:** `vela_relay.py:306-355`, `vela_agent_registry.py:105-149`

When a replacement WebSocket connects, it overwrites `agent.websocket`. If the old socket later disconnects, its handler unconditionally calls `remove_websocket_connection(agent_id)`, which can clear the new socket and fail its pending requests.

**Fix:** Make removal identity-aware: `remove_websocket_connection(agent_id, websocket)` must clear state only when the stored socket is the one being removed. Add a connection generation/ID and apply the same check to cleanup and notifications.

### AR-04 — Agent handles forwarded requests serially

**Severity:** Medium to High  
**Confidence:** Confirmed by code  
**Location:** `app/agent/tunnel.py:358-366`

The receive loop awaits `_handle_forward_request()` directly. A slow assistant stream, recording, filesystem transfer, or hung local endpoint blocks later `forward_request` frames. The tunnel may remain transport-live while application requests queue behind one operation.

**Fix:** Read frames continuously and create bounded tasks per request ID. Add an agent-side send lock for response frames, task cancellation on socket close, and a per-agent concurrency limit.

### AR-05 — Idle liveness is one-directional at the application layer

**Severity:** Medium  
**Confidence:** High  
**Locations:** `app/agent/tunnel.py:336-353`, `tunnel.py:393-403`, `velavps/vela_relay.py:310-315`

The agent sends heartbeats, but the relay does not send an application-level acknowledgement. The agent’s 300-second receive timeout measures application messages, not protocol-level ping/pong frames. Depending on the WebSocket stack, a healthy relay that sends no application data can eventually trigger the agent’s timeout.

**Fix:** Define a bidirectional heartbeat contract:

```text
agent -> heartbeat {connection_id, sequence, sent_at}
relay -> heartbeat_ack {sequence, server_time}
```

Track last acknowledged heartbeat and reconnect when acknowledgements stop. Do not kill a protocol-live socket solely because no application message was received.

### AR-06 — Heartbeat task lifecycle is unmanaged

**Severity:** Medium  
**Confidence:** Confirmed by code  
**Location:** `app/agent/tunnel.py:347`

The agent creates `_heartbeat_loop(websocket)` with `asyncio.create_task()` and does not retain or cancel the task. It usually exits when sending fails, but reconnect cycles can leave task cleanup implicit and make failures harder to diagnose.

**Fix:** Keep the task handle, cancel it in `finally`, and await it while suppressing `CancelledError`.

### AR-07 — Reconnect backoff is blind to failure type

**Severity:** Medium  
**Confidence:** Confirmed by code  
**Locations:** `app/agent/loop.py:32-49`, `app/agent/pairing.py:333-356`

Every tunnel failure causes another token request after a delay. Authentication/revocation/configuration failures should not retry forever like transient DNS/TLS/5xx failures. Local-service failures should not necessarily mint relay tokens repeatedly.

**Fix:** Classify failures into terminal repair-required, transient network, clean shutdown, and local-service-unavailable categories. Use exponential backoff with jitter for transient failures and alert/stop for revoked credentials.

### AR-08 — Connection identity and generation are not explicit

**Severity:** Medium  
**Confidence:** High

The protocol has `agent_id` and request IDs but no connection ID/generation. This complicates stale-socket cleanup, diagnostics, and response ownership. A response from an older connection can be difficult to distinguish from one on a replacement connection.

**Fix:** Generate a random `connection_id` for each WebSocket connection and include it in heartbeat, request, and response envelopes. Reject frames from a connection that is no longer current.

### AR-09 — Request IDs are awkwardly generated

**Severity:** Low to Medium  
**Confidence:** Confirmed by code  
**Location:** `vela_forwarder.py:115`, `vela_forwarder.py:209`

IDs are composed from `id(websocket)` and event-loop time. They are probably unique in practice but are not clear protocol identifiers and are harder to correlate across logs.

**Fix:** Use `uuid.uuid4().hex` or `secrets.token_urlsafe()`, validate type/length, and log the correlation ID.

### AR-10 — Stream cleanup has no reconnect semantics

**Severity:** Medium  
**Confidence:** Confirmed by code  
**Locations:** `vela_forwarder.py:112-166`, `vela_agent_registry.py:133-147`

Streams have explicit start/chunk/end frames and queues are terminated on disconnect, preventing clients from hanging indefinitely. However, clients cannot tell whether the local operation completed before the connection failed. Automatic replay could duplicate actions.

**Fix:** Return a terminal `agent_connection_lost` outcome and preserve operation/request correlation for client retry decisions.

## Current idle behavior

The concern that inactivity automatically cuts the tunnel is only partially true:

- Agent WebSocket protocol pings: every 20 seconds.
- Agent JSON heartbeats: every 30 seconds.
- Relay heartbeat handling: updates `last_seen` on each JSON heartbeat.
- Agent application receive timeout: 300 seconds.
- Relay application receive loop: no explicit timeout; it waits for agent heartbeats or responses.
- Local app stale status threshold: 180 seconds based on persisted local relay events.

The tunnel should survive ordinary inactivity if the heartbeat task is running and the network/proxy permits WebSocket traffic. The immediate user-visible failure is the relay’s disconnected-agent fast path, not the absence of keepalive traffic.

The five-minute receive timeout remains a design flaw because the liveness contract is not bidirectional. Heartbeat acknowledgements make the behavior explicit and observable.

## Recommended target design

### 1. Explicit connection state

Use `DISCONNECTED -> CONNECTING -> AUTHENTICATING -> CONNECTED -> DRAINING -> DISCONNECTED`, with `connection_id`, `connected_at`, `last_rx_at`, `last_tx_at`, and `last_heartbeat_ack_at`.

### 2. Relay-side reconnect wait

Add a per-agent `asyncio.Condition` or `asyncio.Event`:

- clear it when the current socket is removed;
- set it after a socket is accepted and registered;
- wait in `_resolve_agent()` when `websocket is None`;
- return `503` plus `Retry-After` only after `agent_connect_wait_seconds` expires.

For multi-worker VPS deployments, use shared presence/pub-sub or route tunnel traffic to the worker owning the connection. An in-memory registry cannot coordinate workers behind a load balancer.

### 3. Safe dispatch semantics

Before dispatch, requests may wait in memory for a connection. After dispatch, do not automatically replay arbitrary operations. Support idempotency keys for explicitly retryable requests and expose whether failure occurred before or after dispatch.

### 4. Bidirectional heartbeat

Keep WebSocket ping/pong, but add JSON heartbeat acknowledgements. Track transport liveness separately from application presence and expose both in status APIs.

### 5. Concurrent agent dispatch

Keep the frame receiver unblocked, use bounded request tasks, serialize writes with a send lock, and cancel tasks when their connection closes.

### 6. Connection-safe cleanup

Every registry mutation and response route should include connection identity. An old socket must never clear state belonging to a newer socket.

## Suggested test matrix

Add tests in both repositories for:

1. Existing registry agent with `websocket=None` waits and succeeds when a socket connects before the deadline.
2. Existing disconnected agent times out with `503` and `Retry-After`.
3. Requests are queued only before dispatch and are not silently replayed after disconnect.
4. Old socket disconnect does not clear replacement socket.
5. Heartbeats update relay presence and receive acknowledgements.
6. Agent heartbeat task is cancelled when the tunnel exits.
7. Two forwarded requests execute concurrently up to the configured limit.
8. A stalled local request does not stop the agent from receiving later frames.
9. Stream disconnect produces `agent_connection_lost`.
10. Multi-worker deployment routes frames to the owning worker or uses shared connection state.

## Priority order

1. Fix AR-01: wait for an existing disconnected agent before returning `503`.
2. Fix AR-03: identity-aware socket replacement/removal.
3. Add bounded pre-dispatch queueing and explicit no-replay semantics (AR-02).
4. Make agent request handling concurrent (AR-04).
5. Add bidirectional heartbeat acknowledgements and manage heartbeat task lifecycle (AR-05/AR-06).
6. Add connection IDs, UUID request IDs, failure classification, and structured logs (AR-07/AR-08/AR-09).

## Conclusion

The agent already has a basic keepalive, so the main outage is not simply “the connection closes when idle.” The critical defect is that the relay treats an existing but disconnected registry entry as authoritative and immediately rejects requests instead of waiting for the agent’s reconnect loop. Fixing that, combined with identity-safe socket cleanup and explicit bidirectional liveness, will make short network drops transparent to clients while preserving safe behavior for requests already dispatched.
