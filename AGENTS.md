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
| Human overview | `README.md` | Architecture, setup |
| Raw file tree | `ProjectTree.md` | Generated dump; ignore for navigation |

**Convention:** feature `X` → `routers/X.py` → `services/X.py` → `domain/X.py` → `tests/routers/test_X.py`.

## Module → API prefix

| Module | Prefix | Responsibility |
|---|---|---|
| `alerts` | `/alerts` | Spike checks, summaries, Alertmanager webhook |
| `audio` | `/audio` | Volume, mute, devices, beep |
| `clipboard` | `/clipboard` | Read/write/clear |
| `display` | `/display` | Screenshot, record, brightness, monitors, night light |
| `filesystem` | `/fs` | List/tree/search/upload/download, disk usage |
| `input_control` | `/input` | Mouse/keyboard |
| `maintenance` | `/maintenance` | Cache, logs, updates, systemd services |
| `media` | `/media` | Play/pause/seek, now playing |
| `monitoring` | `/monitor` | Live metrics (CPU/RAM/GPU/IO/temps/battery/top procs) |
| `network` | `/network` | IP, wifi, bluetooth, ping, speed, vnstat |
| `notifications` | `/notifications` | Desktop notifications |
| `power` | `/power` | Shutdown/restart/sleep, power profile |
| `processes` | `/processes` | List/kill/launch apps, window control |
| `push` | `/push` | Push device registration |
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

## Assistant tools

LLM tool definitions and execution live under `app/services/assistant/` (`tools.py`, `tool_exec.py`, `prompts.py`, `workflow.py`). Routers only expose `/assistant/chat` and `/assistant/stream`.

## Agent / tunnel

| File | Role |
|---|---|
| `app/agent/agent.py` | CLI entry (`vela-agent`) |
| `app/agent/pairing.py` | Pairing QR/code flow |
| `app/agent/tunnel.py` | WebSocket tunnel to VPS |
| `app/agent/loop.py` | Agent main loop |
| `app/agent/credentials.py` | Credential storage |

## Config knobs

Primary: `app/utils/config.py` + `.env`. Common keys: API port, auth users, Fireworks key, relay/agent IDs, filesystem allowlist, alert/email/push settings.

## How to extend a feature

1. Schema in `app/domain/<feature>.py`
2. Logic in `app/services/<feature>.py`
3. Route in `app/routers/<feature>.py`
4. Register router in `app/routers/__init__.py` if new
5. Test in `tests/routers/test_<feature>.py`
6. If the assistant should call it, wire a tool in `app/services/assistant/tools.py`

## Do not

- Put heavy logic in routers
- Treat `ProjectTree.md` as source of truth (includes caches)
- Assume `doc/API_DOCUMENTATION.md` is complete — verify against the router when unsure
