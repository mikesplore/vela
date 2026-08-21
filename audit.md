# Vela Security Audit

Date: 2026-08-21  
Scope: repository source, configuration templates, dependency metadata, and tests.  
Method: manual review of authentication, routing, filesystem/process controls, tunnel forwarding, assistant tool gates, external HTTP clients, and resource limits. No live deployment or destructive exploit testing was performed.

## Executive summary

Vela is a single-user remote-control agent. A valid JWT or a compromised relay therefore grants access to highly privileged desktop capabilities. The most important findings are:

1. **High — ZIP extraction allows path traversal outside the selected destination.**
2. **High — authenticated scheduler and process-launch APIs provide arbitrary command execution.** This is an intentional capability, but it materially raises the impact of any stolen JWT, CSRF-equivalent browser compromise, or relay compromise.
3. **High — the tunnel prints the WebSocket URL containing the relay token.** Service journals or process/log collection can consequently expose a credential usable to reach the agent.
4. **High — default server binding is `0.0.0.0`, while the architecture describes a localhost service.** A deployment that does not override `host` exposes the entire control API to the LAN/interfaces and relies on JWT protection being correctly configured.
5. **Medium — upload path handling can escape configured filesystem roots, and uploads have no size limit.**
6. **Medium — authenticated health checks are an SSRF primitive and follow redirects without destination restrictions.**
7. **Medium — secrets and internal error details are written to logs or returned in HTTP errors.**

The report treats the authenticated user as trusted for intended desktop-control operations, but calls out where the trust boundary is broader than the architecture implies or where compromise impact can be reduced.

## Findings

### VELA-001 — ZIP Slip in `/fs/unzip` (High, confirmed)

`app/routers/filesystem.py:363-376` calls `ZipFile.extractall(destination)` without validating each archive member. A crafted entry such as `../../.config/vela/config.yaml` or an absolute/normalized equivalent can write outside the requested destination. The destination itself is checked, but extracted member paths are not.

Impact: an authenticated caller can overwrite arbitrary files writable by the Vela service, including configuration, service files, scripts, or data outside `allowed_base_dirs`; the result can be code execution on a later restart or integrity loss.

Recommendation: resolve every member against the destination, reject absolute paths and any member whose resolved path is not a child of the resolved destination, reject symlink entries, and extract with exclusive-safe file creation. Add a regression test with `../` and symlink entries.

### VELA-002 — Arbitrary command execution is exposed by normal authenticated APIs (High, design-risk)

`app/routers/scheduler.py:13-35` stores caller-supplied `command` and `args` and later executes them through `app/services/scheduler.py:command_runner`. `app/routers/processes.py:115-124` directly passes caller-supplied command and arguments to `spawn_detached`, which invokes `systemd-run` or `Popen` (`app/services/processes.py:340-400`).

These are powerful intended features, not shell-injection bugs: arguments are passed without `shell=True`. However, any stolen JWT, exposed API, compromised relay, or browser-origin attack becomes full user-level command execution. The scheduler also permits recurring jobs, so a one-time authorization can create persistence.

Recommendation: narrow the public API to an allowlisted command catalog or explicit executable paths; for scheduled jobs, require a separate high-risk confirmation/PIN and show the complete command, arguments, recurrence, and next-run time. Consider disabling arbitrary launch/scheduling by default and bind them to a separate capability/role.

### VELA-003 — Relay WebSocket token is printed in clear text (High, confirmed)

`app/agent/tunnel.py:324-326` prints the complete tunnel URI. `websocket_tunnel_url()` places `token` in the query string. User-service journals, terminal history capture, centralized logging, crash reports, or support bundles can therefore contain the bearer credential.

Impact: possession of the token may allow a party who can reach the relay to impersonate the agent connection or issue forwarded local-control requests, depending on relay validation.

Recommendation: never log the URI or token; log only the relay host, agent ID, and a hash/fingerprint. Prefer an Authorization header or WebSocket subprotocol if the relay contract permits it. Rotate the token after any possible journal exposure and ensure relay tokens are short-lived and single-connection scoped.

### VELA-004 — Insecure-by-default network exposure (High, deployment risk)

`app/utils/config.py:40-42` defaults `host` to `0.0.0.0`, while `ARCHITECTURE.md` says the service normally serves local HTTP on `127.0.0.1:8765`. If setup/configuration does not override the value, every reachable interface can expose the full control plane. `/health`, `/`, and `/ping` are intentionally unauthenticated; all other control routes depend on the JWT configuration being sound.

Recommendation: change the default to `127.0.0.1`; require an explicit opt-in for non-loopback binding, emit a startup warning or fail closed for non-loopback without TLS, and document the required reverse-proxy/firewall policy. Add a startup test that verifies the default bind address.

### VELA-005 — Upload filename/path traversal and unbounded upload memory (Medium, confirmed)

In `app/routers/filesystem.py:156-172`, `file.filename` is appended directly when the `path` points to a directory. The check at line 164 tests an unresolved `Path`; a filename containing traversal segments can pass the lexical allowlist check while the OS resolves the final open outside the configured root. The entire upload is also read into memory at line 169, with no byte limit.

Impact: writes outside `allowed_base_dirs` and memory exhaustion from a large authenticated multipart request.

Recommendation: discard client directory components and generate a safe basename, resolve the final destination, verify it remains under the configured root, reject symlinked parents, and write in bounded chunks to a temporary file followed by an atomic rename. Enforce request and per-file size limits before/during streaming.

### VELA-006 — Health-check endpoint is an SSRF primitive (Medium)

`app/services/network.py:500-525` accepts an arbitrary URL, follows redirects, and makes a server-side request. It can probe loopback, private networks, cloud metadata endpoints, Unix-adjacent services exposed over HTTP, or relay-internal addresses. Authentication reduces unauthenticated abuse but does not prevent exploitation after token compromise; the endpoint is also available as an assistant observation tool.

Recommendation: allow only `http`/`https`, resolve DNS and validate every resolved address against an explicit public/private policy, re-check after redirects, cap response handling, and consider an allowlist for destinations. Do not return raw exception text to remote callers.

### VELA-007 — Sensitive/internal data leaks through logs and error responses (Medium)

The general exception handler returns `str(exc)` (`app/main.py:224-231`), and many routers similarly place exception text in `detail` (for example `app/routers/processes.py:92-124`). The tunnel returns exception text in relay response bodies (`app/agent/tunnel.py:285-287` and its catch-all path). `local_auth.py:153-194` logs token endpoint URLs, credential labels, response details, and failures; successful authentication persists a JWT in `.env` (`app/agent/local_auth.py:180-184`).

Impact: filesystem paths, command output, upstream response details, topology, and occasionally credential-bearing URLs can be disclosed to API/relay clients or anyone with journal access.

Recommendation: return stable opaque error IDs and log full diagnostics only locally at a controlled level; redact URLs, headers, tokens, passwords, and upstream bodies. Keep access tokens in memory where possible; if persistence is required, use a dedicated 0600 credential store and rotate/revoke on logout or re-pairing.

### VELA-008 — Trusted proxy headers defeat rate-limit and audit client identity (Medium)

`app/rate_limiter.py` and `app/middleware.py` trust the first `X-Forwarded-For` value from any requester. If Vela is directly reachable, callers can rotate this header to evade the per-IP limiter and forge audit source addresses. The auth endpoint is rate-limited, but this weakens brute-force protection and audit reliability.

Recommendation: only honor forwarding headers when the immediate peer is a configured trusted proxy; otherwise use `request.client.host`. Configure proxy-aware middleware rather than accepting arbitrary client-supplied identity headers.

### VELA-009 — Resource exhaustion controls are incomplete (Medium)

There is no evident global request-body/upload limit. Filesystem search runs `find` with caller-controlled query and can return an unbounded result set (`app/routers/filesystem.py:259-274`); ZIP creation/extraction can consume substantial CPU, disk, and memory; and `/monitor/stream` accepts arbitrary numbers of WebSocket connections and an unbounded `interval` value (`app/routers/monitoring.py:106-117`) without rate limiting or connection quotas.

Recommendation: enforce body/file, archive entry/count/expanded-size, search result, and operation time limits; add concurrency semaphores for expensive tools; bound WebSocket interval and connections per authenticated client; and apply rate limits to WebSockets and all expensive endpoints.

### VELA-010 — ZIP and filesystem operations are vulnerable to symlink/TOCTOU races (Medium)

The filesystem allowlist resolves paths before performing later operations (`app/services/filesystem.py:7-45`), then operations such as upload, rename, mkdir, delete, and archive traversal act on paths later. A writable directory containing symlinks can change between validation and use. Archive creation also walks files after validation (`app/routers/filesystem.py:345-352`).

Recommendation: use descriptor-based operations (`openat`/`O_NOFOLLOW` where practical), re-check parent and final objects immediately before use, reject symlinked roots/parents for mutating operations, and avoid following symlinks during recursive walks.

### VELA-011 — Dependency versions are unconstrained above minimums (Low/Medium, supply-chain risk)

`pyproject.toml` and `requirements.txt` use mostly lower bounds (`fastapi>=...`, `httpx>=...`, `websockets`, etc.) and there is no lockfile in the repository. Builds can therefore resolve different versions over time, including versions with regressions or incompatible security behavior. This audit did not perform an online CVE lookup.

Recommendation: generate and commit a hash-pinned lockfile, update dependencies through review, run `pip-audit`/OSV scanning in CI, and test production installs from the lockfile.

## Positive controls observed

- JWT verification pins the algorithm to HS256 and validates expiry through the JWT library.
- Passwords are bcrypt-hashed and setup validates a non-placeholder, minimum-length JWT secret.
- Most control routes require `get_current_user`; the WebSocket monitor validates a bearer token separately.
- Assistant medium/high-risk tools have confirmation/PIN policy and pending actions expire.
- Shell commands are generally passed as argument arrays rather than `shell=True`.
- `.env` and desktop environment files are written with mode `0600` by setup/helpers.

## Prioritized remediation plan

1. Fix ZIP extraction and upload destination validation; add malicious archive, traversal filename, symlink, and size-limit tests.
2. Remove token-bearing URI logging and rotate any tokens that may already be in journals.
3. Make loopback binding the default and explicitly gate remote binding behind TLS/firewall configuration.
4. Add request/file/archive/resource limits and SSRF destination validation.
5. Replace broad exception responses and logs with redacted, opaque errors.
6. Decide whether arbitrary process launch/scheduling is required; if retained, isolate it behind explicit capability grants and stronger confirmation/PIN semantics.
7. Pin dependencies and add automated security/dependency scanning.

