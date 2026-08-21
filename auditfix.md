# Vela Security Remediation Plan

Source: Vela Security Audit, 2026-08-21
Goal: close High findings first, then Medium, then supply-chain hardening. Each phase should ship as its own PR with tests.

---

## Phase 1 — High severity, ship this week

### 1.1 Fix ZIP Slip (VELA-001)
File: `app/routers/filesystem.py:363-376`

- Resolve every archive member path against the destination before extraction.
- Reject any member whose resolved path is not a child of the resolved destination.
- Reject absolute paths and symlink entries.
- Extract with exclusive-safe file creation (no overwrite via traversal).
- Test: archive containing `../../etc/passwd`-style entry, archive containing a symlink entry. Both must be rejected, not silently skipped.

### 1.2 Stop logging the tunnel token (VELA-003)
File: `app/agent/tunnel.py:324-326`, `websocket_tunnel_url()`

- Remove the full URI print. Log relay host, agent ID, and a hash/fingerprint of the token only.
- Rotate the token generation scheme so tokens are short-lived and single-connection scoped (relay-side change, coordinate if relay is a separate service).
- Action item outside code: rotate any tokens currently sitting in journals/logs from before this fix.

### 1.3 Default to loopback binding (VELA-004)
File: `app/utils/config.py:40-42`

- Change default `host` from `0.0.0.0` to `127.0.0.1`.
- If a non-loopback bind is requested, require an explicit flag/env var (`VELA_ALLOW_REMOTE_BIND=1` or similar) and emit a startup warning naming the risk.
- Test: default config binds to `127.0.0.1` with no override.

### 1.4 Decide on VELA-002 (arbitrary command exec via scheduler/process APIs)
This is a design decision, not a quick patch. Pick one:

- **A. Keep it, gate it harder.** Require a separate PIN/confirmation for scheduler job creation and process spawn, same as your existing medium/high-risk assistant tool gate. Show full command + args + recurrence + next-run before confirming.
- **B. Narrow it.** Replace free-form `command`/`args` with an allowlisted command catalog or fixed executable paths.

Given Vela's whole purpose is remote control, A is probably the right call, not B. Flag for your decision before implementing — this changes the JWT compromise blast radius either way.

---

## Phase 2 — Medium severity

### 2.1 Fix upload path handling (VELA-005)
File: `app/routers/filesystem.py:156-172`

- Discard client-supplied directory components; generate a safe basename server-side.
- Resolve final destination path, verify it's under the configured root, reject symlinked parents.
- Stream to a temp file with a byte limit, then atomic rename. Stop reading the whole upload into memory.

### 2.2 Lock down the health-check SSRF primitive (VELA-006)
File: `app/services/network.py:500-525`

- Restrict scheme to `http`/`https`.
- Resolve DNS, validate resolved address against a private/public policy (block loopback, RFC1918, link-local, cloud metadata IP) — re-check after each redirect hop.
- Cap response size/time. Strip raw exception text from the response.

### 2.3 Redact logs and error responses (VELA-007)
Files: `app/main.py:224-231`, `app/routers/processes.py:92-124`, `app/agent/tunnel.py:285-287`, `app/agent/local_auth.py:153-194`

- Replace raw `str(exc)` in responses with a stable opaque error ID; keep full detail in local logs only.
- Redact tokens, URLs, headers, upstream bodies before logging.
- Move JWT persistence out of `.env` into a dedicated 0600 credential store if persistence is needed at all; prefer in-memory.

### 2.4 Stop trusting client-supplied forwarding headers (VELA-008)
Files: `app/rate_limiter.py`, `app/middleware.py`

- Only honor `X-Forwarded-For` when the immediate peer is a configured trusted proxy.
- Otherwise use `request.client.host` directly.

### 2.5 Add resource limits (VELA-009)
Files: `app/routers/filesystem.py:259-274` (search), `app/routers/monitoring.py:106-117` (stream)

- Global request-body/upload size limit.
- Cap `find`-based search result count.
- Cap archive entry count / expanded size on zip create+extract.
- Bound `/monitor/stream` interval and connections per authenticated client.
- Rate-limit WebSocket connection attempts same as HTTP endpoints.

### 2.6 Close symlink/TOCTOU gaps (VELA-010)
File: `app/services/filesystem.py:7-45`, `app/routers/filesystem.py:345-352`

- Re-check parent and final path immediately before use, not just at initial validation.
- Reject symlinked roots/parents for any mutating operation (upload, rename, mkdir, delete, archive).
- Use `O_NOFOLLOW` / descriptor-based ops where the platform supports it.

---

## Phase 3 — Supply chain

### 3.1 Pin dependencies (VELA-011)
- Generate a hash-pinned lockfile from `pyproject.toml`/`requirements.txt`.
- Add `pip-audit` or OSV scanning to CI.
- Test production installs from the lockfile, not floating minimums.

---

## Order of operations
1. Phase 1 items 1.1–1.3 (mechanical fixes, no design decision needed) — same PR is fine.
2. Phase 1 item 1.4 — needs your call on A vs B before anyone writes code.
3. Phase 2, roughly in the listed order — 2.1 and 2.5 touch the same file, worth combining.
4. Phase 3 whenever CI bandwidth allows; not urgent but don't drop it.