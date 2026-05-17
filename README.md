# Vela RemotePC Agent

**Talk to your laptop. It listens and acts.**

Vela is a **conversational AI agent** for Linux desktops that turns your PC into an intelligent assistant. Currently chat-based, but **designed to be voice-first**. Instead of clicking through settings or typing commands, you ask—naturally—and Vela understands your intent and executes.

```
"Vela, what's using up my RAM?"
→ Agent analyzes processes and tells you instantly

"Vela, is my Bluetooth off?"
→ Agent checks and reports back

"Vela, kill the app that's hogging CPU"
→ Agent identifies the culprit and terminates it immediately

"Vela, remind me to call mom in 5 minutes"
→ Agent sets a notification
```

Tasks that are **faster to ask for than to click through** are the core of Vela. It's built for the moments when you're busy and want to control your system without context-switching.

## Why Vela? How is this different?

| Tool             | What you do          | What Vela does           |
|------------------|----------------------|--------------------------|
| Remote Desktop   | Stare at a stream    | Executes intent          |
| SSH              | Remember commands    | Understands context      |
| KDE Connect      | Send files across    | Converses with you       |
| Task automation  | Write scripts        | Infers what you mean     |

Vela is **intent-driven, not command-driven**. When you say "my laptop is slow," Vela doesn't ask you for flags or arguments. It analyzes the system, identifies the problem, and proposes solutions—or executes them if you ask.

It's powered by an LLM (DashScope's Qwen) that uses **tool-calling** to map natural language to actual system operations. The assistant layer understands context, handles ambiguity, and ensures you get what you meant, not what you said literally.

**Key differentiators:**
- **Conversational, not imperative** — ask, don't command
- **Mobile-friendly** — control from your phone on the same LAN
- **Designed for voice** — currently chat-based, but built to support voice commands soon
- **Lightweight** — no remote desktop overhead, pure intent execution
- **Intelligent** — understands context and delegates to the right system layer

## Prerequisites

- Python 3.13+
- Linux desktop environment with `xrandr`, `playerctl`, `xdotool`, `nmcli`, `bluetoothctl`, `systemctl`, and `journalctl` available where applicable
- `python3-venv` and `python3-pip`
- A user-level systemd session for service deployment

## How Vela Works

### The Intent Pipeline

1. **You chat or speak** a natural language request (currently via text; voice coming soon)
2. **Frontend receives** the message and sends it to the Vela backend
3. **Assistant layer** (LLM + tool-calling) parses intent, determines which system operation is needed
4. **PC Agent router** executes the actual system operation (filesystem, processes, audio, etc.)
5. **Result flows back** to your phone/frontend with natural language summary

### Architecture: Clean Separation

```
┌─────────────────────────────────────────────────┐
│ Your Phone / Remote Client (React/native app)   │
│ - Conversational UI                             │
│ - Sends natural language requests               │
│ - Does NOT parse, execute, or sandbox anything │
└─────────────────┬───────────────────────────────┘
                  │ JWT-protected HTTPS
                  ▼
┌─────────────────────────────────────────────────┐
│ Vela Backend (FastAPI + Express proxy)          │
│ - Receives natural language                      │
│ - Routes to Assistant or direct operations      │
│ - Handles errors, permissions, logging          │
└─────────────────┬───────────────────────────────┘
                  │ Direct system calls
                  ▼
┌─────────────────────────────────────────────────┐
│ PC Agent (Routers: filesystem, audio, etc.)     │
│ - Executes against real system state            │
│ - Applies safety policies (whitelisting,        │
│   destructive action checks, permissions)       │
│ - Returns structured data back                  │
└─────────────────────────────────────────────────┘
                  │
                  ▼
            Your Linux Desktop
```

**What each layer does—and what it doesn't:**

| Layer | Does | Doesn't |
|-------|------|---------|
| Frontend | Sends messages, displays results | Parse commands, execute anything, sandbox |
| Vela API | Route requests, handle auth, enforce limits | Directly touch the filesystem (agent does) |
| PC Agent | Execute operations, enforce safety rules | Know what the user "meant" (assistant does) |
| Assistant | Understand intent, map to tools | Actually execute (routers do) |

This separation ensures that **safety decisions live where they matter most**: in the agent backend, where the actual system state is known.

## Safety & Permissions Model

Vela is designed to be safe by default, with multiple layers of protection:

### 1. **Authentication & Authorization**
- All requests require a valid JWT bearer token
- Username/password auth with bcrypt hashing
- No token = no access (rate-limited to prevent brute force)

### 2. **Filesystem Permissions**
- `allowed_base_dirs` whitelist restricts which directories the agent can access
- Empty list = all paths allowed (for local LAN only)
- Directory traversal checks prevent `../` escapes

### 3. **Intent-Level Safeguards**
- Destructive operations (file deletion, process termination) require explicit confirmation or opt-in
- The assistant layer can detect risky intents and surface warnings
- Example: "You asked me to kill the process using 99% CPU. That's `chrome`. Kill it? [Y/n]"

### 4. **Process & System Safeguards**
- Critical system processes (init, systemd, kernel threads) cannot be terminated
- Power operations (shutdown, reboot) require explicit user confirmation
- Filesystem operations limited to user-owned files unless running as root

### 5. **Rate Limiting**
- Per-endpoint rate limits prevent abuse
- Default: 100 requests/minute globally
- Auth endpoints: stricter limits (10/min) prevent credential attacks
- Ping endpoint: higher limit (60/min) for health checks

### 6. **IP Allowlisting**
- Optional `allowed_ips` restricts which addresses can connect
- Designed for LAN use; pair with a VPN/tunnel for remote access

### Why Safety is Built Into the Backend

The assistant doesn't execute—it interprets. The PC Agent doesn't decide what's safe—it enforces policy. This separation means:

- **No surprises:** You know exactly what your laptop will do before it does it
- **No accidental damage:** Warnings surface before destructive operations
- **Deterministic behavior:** The same request always behaves the same way
- **Auditability:** Every operation is logged with intent + result

## How the Assistant Works

Vela's conversational intelligence is **LLM-powered with tool-calling**:

### The Assistant Uses:
- **Large Language Model (LLM)**: DashScope's Qwen model for understanding context and intent
- **Tool-calling**: Maps natural language to specific system operations (check processes, toggle Bluetooth, etc.)
- **Hybrid approach**: Rule-based safety overlaid on top of neural understanding

### What Makes It Intelligent:
1. **Context awareness** — "My laptop is slow" → analyzes CPU, memory, disk I/O → identifies the culprit
2. **Intent inference** — "Is my Bluetooth off?" understands this as a state-check, not a toggle request
3. **Ambiguity resolution** — "Kill it" refers back to the process you were just talking about
4. **Error surfacing** — If something goes wrong, you get a human-readable explanation, not a traceback

### What the Assistant Doesn't Do:
- ✗ Execute arbitrary shell commands
- ✗ Make destructive decisions without your confirmation
- ✗ Guess what you mean when it's unclear (asks for clarification instead)
- ✗ Send telemetry or track your usage

## Real-World Use Cases

### You're in a video call—your laptop is slowing down
```
Chat: "Vela, my video is lagging. What's using the most CPU?"
→ Vela analyzes and tells you: Firefox (42%), VSCode (28%), Spotify (5%)

Chat: "Kill Firefox"
→ Vela terminates it, call smooths out immediately

(Future: Voice: "Vela, my video is lagging...")
```

### You're in the kitchen—you need a reminder
```
Chat: "Vela, remind me to take the laundry out in 15 minutes"
→ Your phone vibrates in 15 minutes with the reminder

(Future: Voice from kitchen: "Vela, remind me...")
```

### You're working out—you want to know your system health
```
Chat: "Vela, how much storage do I have left?"
→ Vela: "Your SSD is 340GB full out of 500GB. Largest items: Videos (120GB), Docker images (85GB)"

Chat: "Show me what's in Videos"
→ Vela lists the folder contents so you can decide what to delete

(Future: Voice from the gym: "Vela, how much storage...")
```

### You're on the couch—your music needs to switch devices
```
Chat: "Vela, is my Bluetooth on?"
→ Vela: "Yes, connected to My Earbuds"

Chat: "Switch audio to speakers"
→ Vela switches the audio output and resumes playback

(Future: Voice: "Switch to speakers" while hands-free)
```

### You need system maintenance but you're busy
```
Chat: "Vela, check if there are any system updates"
→ Vela: "3 security updates pending. Your kernel is out of date"

Chat: "Install them"
→ Vela runs the updates in the background, notifies you when done

(Future: Voice commands during other tasks)
```

**Today:** These work via chat on your phone or desktop.
**Soon:** Same functionality via voice—ask Vela without typing, and it responds audibly.

These aren't available in SSH, remote desktop, or KDE Connect because **those tools require command knowledge or clicking**. Vela understands what you want.

## Long-Term Vision

Vela is built with these future states in mind:

### Phase 1: Chat → Voice (Current → Immediate)
- **Current:** Chat interface (phone app and desktop)
- **Next:** Voice input/output (speak commands, get audio responses)
- **Soon:** Bluetooth headset support, hands-free operation
- **Later:** In-car integration (tell Vela to remind you when you get home)

### Phase 2: Proactive Notifications
- Phone ringing alerts on your PC
- Calendar/meeting reminders
- System health warnings ("Your SSD is 85% full")

### Phase 3: Personal AI Assistant for Your PC
- Multi-step task automation ("Organize my Downloads folder, back up my photos, then compress old logs")
- Learning from your patterns ("You always pause music when video calls come in")
- Privacy-first: 100% runs locally or on your own infrastructure

### Phase 4: Cross-Device Ecosystem
- Same voice assistant across phone, PC, car
- Seamless context switching ("Continue playing my podcast on my phone")
- Device-aware scheduling ("Don't interrupt me on video calls")

The north star: **A truly personal assistant that lives on your devices, understands you, and never leaves your control.**

## Installation & Prerequisites

**System Requirements:**
- Python 3.13+
- Linux desktop environment with `xrandr`, `playerctl`, `xdotool`, `nmcli`, `bluetoothctl`, `systemctl`, and `journalctl` available where applicable
- `python3-venv` and `python3-pip`
- A user-level systemd session for service deployment

1. Clone the repo:
```bash
git clone https://your-repo-url.git ~/Development/vela
cd ~/Development/vela
```
2. Run the setup script:
```bash
./setup.sh
```
3. The script will install dependencies, generate `config.yaml`, hash your password, and optionally install the systemd user service.

## Configuration

`config.yaml` includes:

- `host` / `port`
- `secret_key`
- `username` / `password_hash`
- `allowed_origins`
- `allowed_ips`
- `allowed_base_dirs`
- `rate_limit_default`
- `route_rate_limits`
- `feature_flags`

### Filesystem security

Set `allowed_base_dirs` to the directories the agent may access. If empty, all paths are permitted.

### Environment variables and .env

Vela supports configuration from environment variables and a `.env` file using the `VELA_` prefix. Example variables:

```bash
VELA_DASHSCOPE_API_URL=https://dashscope-intl.aliyuncs.com/api/v1
VELA_DASHSCOPE_API_KEY=<your-api-key>
VELA_DASHSCOPE_MODEL=qwen-plus
# alternate fallback env names:
# DASHSCOPE_HTTP_BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1
# DASHSCOPE_API_KEY=<your-api-key>
VELA_SECRET_KEY=<your-secret-key>
VELA_USERNAME=mike
VELA_PASSWORD_HASH=<bcrypt-hash>
```

The `.env` file is loaded automatically if present, so you can keep secrets out of `config.yaml`.

> Note: If you update `.env`, restart the Vela service or the Python process so the new values are loaded.

### Rate limiting

- `rate_limit_default`: global default limit
- `route_rate_limits`: map endpoint paths to custom limits

Example:
```yaml
rate_limit_default: 100/minute
route_rate_limits:
  /auth/token: 10/minute
  /ping: 60/minute
```

## Running

Start locally:
```bash
source .venv/bin/activate
python main.py
```

OpenAPI docs are available at `http://<host>:<port>/docs`.

## Systemd service

The service file can be installed for the current user via `./setup.sh`. The service will run the agent on login and restart on failure.

## Connecting from a phone

Use the local LAN IP shown by `ip a` or `hostname -I`. If you run behind Tailscale or another tunnel, use the provided private address and open port.

## Security recommendations

- Use a strong `secret_key`
- Do not expose the API directly to the public internet
- Use an allowlist in `allowed_ips` when possible
- Use `allowed_base_dirs` to restrict filesystem access

## Adding a new feature module

1. Add a router file under `routers/`
2. Export its router in `routers/__init__.py`
3. Add the router to `all_routers`
4. Add `feature_flags` in `config.yaml`
5. Add tests under `tests/`
6. Update `CHANGELOG.md`

## Assistant integration

A DashScope-powered assistant is available at `/assistant/chat`.
It expects a JWT bearer token and forwards natural language prompts to the configured `dashscope_api_url` using `X-API-Key`.

Example config fields:
```yaml
dashscope_api_url: https://api.dashscope.com/v1/chat/completions
dashscope_api_key: "<your-key>"
dashscope_model: qwen-max
```
