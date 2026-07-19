# I Built a Remote Linux Agent Because I Kept Forgetting Commands and Hating SSH Loops

**Suggested dev.to title:** I Built a Remote Linux Agent Because I Kept Forgetting Commands and Hating SSH Loops

**Suggested tags:** `linux`, `python`, `fastapi`, `opensource`, `sideproject`

---

I wanted to manage my laptop from anywhere without being on the same network.

Not "same WiFi" remote desktop. Not opening port 22 on my home router and hoping for the best. I wanted to lock the screen from my phone while I was out, check disk space, restart a service, mute audio, or skim logs without digging through my shell history for the exact `systemctl` or `journalctl` flags I used three months ago.

I am a developer. I live in terminals. And I still forget commands constantly.

I also manage servers. SSH is fine until it becomes the only interface you have for everything. Open a session, run one thing, close it. Need something else? Open again. Repeat. It works, but it never felt like the workflow I wanted on a machine I actually use every day.

So I built **Vela**.

## What Vela is

Vela is a FastAPI agent that runs on your Linux desktop and exposes real system control through a REST API:

- Filesystem (within an allowlist)
- Audio, display, power, notifications
- Processes, network, monitoring
- Maintenance (`systemctl`, logs, updates)
- Scheduler, clipboard, media, Spotify
- An LLM assistant that turns natural language into those same API calls

You can hit the API directly, talk to it through chat, or use an Android client. The important part: **your phone does not need to be on your home network**.

## Why not just SSH or Tailscale?

SSH is great for servers. For a daily driver laptop, I wanted something closer to a product:

1. **Structured actions**, not memorized one-liners
2. **A phone-friendly layer**, not a terminal in a tiny keyboard
3. **Optional AI** when I know what I want but not which command does it
4. **No inbound ports** on my home network

Tailscale and similar tools solve connectivity well. Vela solves "what do I actually want to do with the machine once I am connected?" with a consistent API and a UI path that is not "SSH from your phone and pray."

## How it works (the short version)

Vela runs as two processes:

| Process | Job |
|---------|-----|
| **Vela API** (`vela.service`) | Local FastAPI on `127.0.0.1:8765`. Does the work on your machine. |
| **Vela Agent** (`vela-agent.service`) | Keeps an outbound WebSocket to a VPS relay. Forwards requests to the API. |

Flow:

```
Phone → VPS relay → WebSocket tunnel → vela-agent → local API → Linux
```

Your PC initiates the tunnel. The VPS never punches into your network. The agent is the phone line. The API is the hands.

Pairing is QR/code based: setup registers with the relay, your phone completes pairing, credentials land in `.env`, and the agent reconnects automatically with backoff.

## The assistant is not a separate product

This was intentional. The assistant does not get its own magic path to the OS. It uses the same tool registry as the REST API. The LLM picks tools like `list_services`, `lock_screen`, or `get_disk_usage`. Vela runs them. The model summarizes.

Direct API: you know the endpoint.

Assistant: you know the intent.

Same engine underneath.

Destructive actions can require PIN confirmation. Filesystem access is allowlist-based. JWT auth and rate limits on the API side. Relay auth is separate from local API auth. Two trust layers, on purpose.

## What it feels like in practice

- Commuting and wondering if a service is stuck: open the app, check status, restart it
- Need to mute or pause media without reaching for the laptop
- Want a daily summary of CPU, memory, network without writing cron + email glue
- Ask "how much storage is left?" instead of running `df` from muscle memory

It is the remote control I wished existed when I kept thinking "there must be a simpler way than opening SSH again."

## Tech stack

- **Python 3.13+**, FastAPI, Pydantic
- **systemd** user services for the API and agent
- **WebSocket tunnel** to a VPS relay (outbound only)
- **Fireworks AI** for the optional assistant (tool calling)
- **SQLite** for audit log and scheduler state
- Shell-outs to the tools Linux already has (`systemctl`, `pactl`, `nmcli`, etc.)

Code layout follows a simple rule: `routers/` (HTTP) → `services/` (logic) → `domain/` (schemas). Feature `X` lives in three predictable files.

## Try it

```bash
git clone https://github.com/mikesplore/vela.git
cd vela
./setup.sh
```

Or if installed globally:

```bash
pip install mikesplore-vela
vela --setup
```

Useful commands after setup:

```bash
vela --status      # are services running?
vela --env         # open the .env your services actually load
vela --restart     # reload after credential changes
vela --dashboard   # local ops dashboard (audit, latency)
```

Docs in the repo:

- `README.md` for setup and reference
- `doc/HOW_IT_WORKS.md` for the full architecture story

## Why I am sharing this

I built Vela for myself: remote laptop control without same-network assumptions, less command memorization, less SSH churn for things that are not really "server work."

If you have ever SSH'd into your own laptop from your phone to run one command and thought "this should be a button," this might resonate.

Repo: [github.com/mikesplore/vela](https://github.com/mikesplore/vela)

Feedback and issues welcome. I am still learning how to explain something I built piece by piece over months. Writing this post was part of that.

---

**Cover image idea:** simple diagram of Phone → VPS → Agent → API → Desktop, or a screenshot of the Android app plus the ops dashboard.
