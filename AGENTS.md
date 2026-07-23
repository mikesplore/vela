# Vela — Agent Project Index

Use this file before scanning the repo. Prefer jumping to the mapped path over broad searches.

## What this is

Linux remote-PC agent: FastAPI REST API (+ optional WebSocket tunnel to a VPS relay) that exposes desktop control and an LLM assistant with tool-calling.

## Layer map (edit path)

| Concern | Path | Notes |
|---|---|---|
| App entry / lifespan | `app/main.py` | Routers, middleware, health |
| HTTP routers | `app/routers/<module>.py` | Thin handlers; register in `app/routers/__init__.py` |
| Business logic | `app/services/<module>.py` | Prefer putting logic here |
| Request/response models | `app/domain/<module>.py` | Pydantic schemas |
| Auth / JWT | `app/auth.py`, `app/dependencies.py` | Most routes use `get_current_user` |
| Config / env | `app/utils/config.py`, `.env` | Settings object |
| Tunnel agent | `app/agent/` | Pairing, WS tunnel, agent loop |
| Setup / install | `app/setup/` | Wizard, deps, systemd writers |
| DB / audit | `app/db/` | Audit log, pending actions |
| LLM assistant | `app/services/assistant/` | Tools, prompts, execution |
| Tests | `tests/`, `tests/routers/` | Mirror router names |
| Full API shapes | `doc/API_DOCUMENTATION.md` | Request/response examples (may lag code) |
| How it works | `doc/HOW_IT_WORKS.md` | Architecture, flows, auth, mental model |
| Human overview | `README.md` | Pitch, setup, config reference |
| Raw file tree | `ProjectTree.md` | Generated dump; ignore for navigation |

**Convention:** feature `X` → `routers/X.py` → `services/X.py` → `domain/X.py` → `tests/routers/test_X.py`.

## Module → API prefix

| Module | Prefix | Responsibility |
|---|---|---|
| `alerts` | `/alerts` | Spike checks, summaries, Alertmanager webhook |
| `audio` | `/audio` | Volume, mute, devices, beep |
| `clipboard` | `/clipboard` | Read/write/clear |
| `display` | `/display` | Screenshot, record, brightness, monitors, night light |
| `docker` | `/docker` | Docker daemon info, containers, logs, compose status |
| `filesystem` | `/fs` | List/tree/search/upload/download, disk usage |
| `input_control` | `/input` | Mouse/keyboard |
| `maintenance` | `/maintenance` | Cache, logs, updates, systemd services/timers |
| `media` | `/media` | Play/pause/seek, now playing |
| `monitoring` | `/monitor` | Live metrics (CPU/RAM/GPU/IO/temps/battery/top procs) |
| `network` | `/network` | IP, wifi, bluetooth, ping, speed, vnstat, port/health/firewall/VPN |
| `notifications` | `/notifications` | Desktop notifications |
| `power` | `/power` | Shutdown/restart/sleep (API/UI only — not assistant tools), power profile |
| `processes` | `/processes` | List/kill/open apps, installed app catalog (`.desktop`), running check, window control (`POST /processes/launch` is API-only — not an assistant tool) |
| `push` | `/push` | FCM device registration + send to user's devices |
| `scheduler` | `/scheduler` | Create/list/cancel/run tasks |
| `security` | `/security` | Lock, webcam/mic, login/SSH history |
| `spotify` | `/spotify` | OAuth + playback helpers |
| `system_info` | `/system` | Static hardware/OS inventory |
| `assistant` | `/assistant` | Chat + SSE stream |
| `admin` | `/admin` | Audit dashboard/events |
| auth (in `app/auth.py`) | `/auth` | Token issue |

Also: `GET /`, `GET /health`, `GET /ping` in `app/main.py`.

## Monitoring vs system_info

- **`/system/*`** — inventory snapshots (CPU model, disk partitions, OS, USB, BIOS).
- **`/monitor/*`** — live rates/usage. Dedicated pieces:
  - `GET /monitor/disk-io` — `[{device, read_bytes_per_sec, write_bytes_per_sec}]`
  - `GET /monitor/network-io` — `[{interface, bytes_sent_per_sec, bytes_recv_per_sec}]`
  - `GET /monitor/processes` — `{by_cpu, by_memory}` (top 20 each)
  - `GET /monitor/snapshot` — bundles the above + CPU/RAM/GPU/temps/etc.
  - `WS /monitor/stream` — periodic snapshots

## Service & container monitoring

**Systemd** (`/maintenance`, logic in `app/services/maintenance.py`):

- `GET /maintenance/services?filter=&scope=system|user|all` — list units (Vela itself is **user** scope: `vela.service`, `vela-agent.service`)
- `GET /maintenance/service/status?name=` — single-unit status; prefer this over listing all services
- `GET /maintenance/services/failed`, `GET /maintenance/timers`, `GET /maintenance/package-installed`, `GET /maintenance/boot-errors`
- `POST /maintenance/service/start|stop|restart` — idempotent start/stop (already running/stopped → message, no-op)

**Docker** (`/docker`, logic in `app/services/docker.py`):

- `GET /docker/info` — CLI installed + daemon running
- `GET /docker/containers?all=&filter=` — list containers
- `GET /docker/containers/{id}` — detail, ports, health
- `GET /docker/containers/{id}/logs`, `POST .../start|stop|restart`
- `GET /docker/compose?project_directory=&project=` — compose project services

**Process / network probes** (for “is X up?” without starting anything):

- `GET /processes/apps?filter=` — installed GUI apps from Freedesktop `.desktop` files (name, id, exec binary)
- `POST /processes/app/open` — opens by friendly name / desktop id / exec; resolved via `.desktop` entries (+ `gtk-launch` when available)
- `POST /processes/app/close` — closes using the same `.desktop`-aware process matching (exec binary + process name)
- `GET /processes/running/{name}` — process running by name
- `GET /network/port/{port}` — local TCP listener check
- `GET /network/health-check?url=` — HTTP(S) probe
- `GET /network/firewall`, `GET /network/vpn`

## Assistant tools

LLM tool definitions and execution live under `app/services/assistant/` (`tools.py`, `tool_exec.py`, `prompts.py`, `workflow.py`, `safety.py`). Routers only expose `/assistant/chat` and `/assistant/stream`.

**Check-before-act (important):** status questions must use read-only tools first — `get_service_status`, `get_container_status`, `list_docker_containers`, `is_process_running`, `check_port`, `health_check`. Do not call `start_service`, `start_container`, or `open_application` to answer “is it running?”. There is no assistant tool for arbitrary binary/script launch (`launch_process` was removed); use `open_application` or `schedule_job`, or tell the user to call `POST /processes/launch` directly. **No assistant tools for shutdown/restart/sleep/hibernate/schedule-shutdown** — use the app Power UI or `/power/*` API.

Key assistant tools for ops:

| Question | Tool(s) |
|---|---|
| Is systemd service X running? | `get_service_status` (scope=`all` for Vela user units) |
| What services failed? | `list_failed_services` |
| Docker containers up? | `get_docker_info`, `list_docker_containers`, `get_container_status` |
| Compose stack status? | `compose_status` |
| Is app/process open? | `is_process_running` |
| What apps are installed? / open Chrome? | `list_installed_applications`, then `open_application` |
| Port / HTTP endpoint up? | `check_port`, `health_check` |

**Desktop app launch:** Logic in `app/services/processes.py` scans `*/applications/*.desktop`, caches ~5 min, matches friendly names/aliases to entries, then launches via `gtk-launch` or parsed `Exec=`. Alias map: `APP_ALIASES` in same file. Assistant: `list_installed_applications` (read-only), `open_application` (confirmation).

**Tool execution notes** (`tool_exec.py`):

- Path placeholders in tool defs (`{name_or_id}`, `{port}`, `{pid}`) are substituted from `tool_input`
- Tools with `"query_input": true` send params as query string (maintenance service actions, `run_update`)
- Read-only ops tools are low-risk; service/container start/stop/restart and `send_push_notification` are medium-risk (confirmation)
- High-risk tools (`delete_path`, `upload_file`, `kill_process`, `kill_process_by_name`) require PIN when `assistant_action_pin` is set; otherwise they fall back to yes/no confirmation
- **Gate flow:** planner emits the tool call → server registers a pending action → client gets `gate` SSE (stream) or `pending_action_id` + `confirmation` (chat). User approves with yes (medium) or PIN (high). The LLM must never ask for PIN/confirmation in chat — only the app gate UI/prompt does. "Kill/stop container" → `stop_container` (confirmation), not `kill_process` (PIN).

Wire new capabilities: add tool in `tools.py` → add to `TOOL_DISPLAY_NAMES` → add read-only tools to `LOW_RISK_TOOLS` in `safety.py` (or medium/high as appropriate) → extend `_is_observation_tool` in `workflow.py` if check-first behavior applies.

## Agent / tunnel

| File | Role |
|---|---|
| `app/agent/agent.py` | CLI entry (`vela-agent`) |
| `app/agent/pairing.py` | Pairing QR/code flow |
| `app/agent/tunnel.py` | WebSocket tunnel to VPS — reuses one `httpx.AsyncClient` per connection; streams bodies >256 KiB or unknown size instead of buffering whole response in RAM |
| `app/agent/loop.py` | Agent main loop |
| `app/agent/credentials.py` | Credential storage |

## Config knobs

Primary: `app/utils/config.py` + `.env`. Common keys: API port, auth users, Fireworks key, relay/agent IDs, filesystem allowlist, alert/email/push settings (`VELA_FCM_SERVICE_ACCOUNT_PATH` for push send).

## How to extend a feature

1. Schema in `app/domain/<feature>.py`
2. Logic in `app/services/<feature>.py`
3. Route in `app/routers/<feature>.py`
4. Register router in `app/routers/__init__.py` if new
5. Test in `tests/routers/test_<feature>.py`
6. If the assistant should call it, wire a tool in `app/services/assistant/tools.py` (see Assistant tools above)

## Do not

- Put heavy logic in routers
- Treat `ProjectTree.md` as source of truth (includes caches)
- Assume `doc/API_DOCUMENTATION.md` is complete — verify against the router when unsure
- Use `start_service` / `start_container` / `open_application` to answer status questions in assistant prompts or tool descriptions
