from fastapi import HTTPException, Request

# In-memory session store: {(user_id, session_id): history}
SESSION_STORE: dict[tuple[str, str], list[dict[str, str]]] = {}
MAX_HISTORY_CHARS = 4000  # Token-budget-aware trimming instead of message count


def get_or_init_session(user_id: str, session_id: str) -> list[dict[str, str]]:
    key = (user_id, session_id)
    if key not in SESSION_STORE:
        SESSION_STORE[key] = []
    return SESSION_STORE[key]


def trim_history(history: list[dict[str, str]], max_chars: int = MAX_HISTORY_CHARS) -> list[dict[str, str]]:
    """Keep the most recent messages that fit within max_chars."""
    total = 0
    trimmed: list[dict[str, str]] = []
    for msg in reversed(history):
        total += len(msg["content"])
        if total > max_chars:
            break
        trimmed.insert(0, msg)
    return trimmed


def extract_session_id(request: Request) -> str:
    """Extract a persistent session ID from request headers.

    Each client/app should generate a unique session ID (any string) once,
    store it persistently, and include it in every request via X-Session-ID header.
    This ensures multi-step confirmations (pending actions) work correctly.

    Session IDs must be consistent across multiple requests from the same device/client.
    """
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        raise HTTPException(status_code=400, detail="X-Session-ID header is required")
    return session_id
