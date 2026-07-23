import base64

import httpx

from app.agent.tunnel import (
    BUFFER_MAX_BYTES,
    STREAM_PATH_SUFFIX,
    _content_length,
    _encode_ws_chunk,
    _is_streaming_request,
    _is_streaming_response,
    _should_relay_streamed,
)


def test_streaming_request_detection():
    assert _is_streaming_request(f"{STREAM_PATH_SUFFIX}", "POST") is True
    assert _is_streaming_request("/assistant/stream/", "POST") is True
    assert _is_streaming_request("/assistant/chat", "POST") is False
    assert _is_streaming_request("/assistant/stream", "GET") is False


def test_streaming_response_detection():
    assert _is_streaming_response("text/event-stream; charset=utf-8") is True
    assert _is_streaming_response("application/json") is False
    assert _is_streaming_response(None) is False


def test_encode_ws_chunk_utf8():
    assert _encode_ws_chunk(b"event: content\n") == {
        "body": "event: content\n",
        "body_encoding": "utf-8",
    }


def test_encode_ws_chunk_base64_for_binary():
    payload = b"\x00\x01\xff"
    assert _encode_ws_chunk(payload) == {
        "body": base64.b64encode(payload).decode("ascii"),
        "body_encoding": "base64",
    }


def _fake_response(*, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(200, headers=headers or {}, request=httpx.Request("GET", "http://test"))


def test_content_length_parses_header():
    response = _fake_response(headers={"content-length": "42"})
    assert _content_length(response) == 42


def test_content_length_missing_or_invalid():
    assert _content_length(_fake_response()) is None
    assert _content_length(_fake_response(headers={"content-length": "nope"})) is None


def test_should_relay_streamed_for_sse_and_assistant_stream():
    sse = _fake_response(headers={"content-type": "text/event-stream"})
    assert _should_relay_streamed(True, sse) is True
    assert _should_relay_streamed(False, sse) is True


def test_should_relay_streamed_for_small_json():
    small = _fake_response(
        headers={"content-type": "application/json", "content-length": str(BUFFER_MAX_BYTES)},
    )
    assert _should_relay_streamed(False, small) is False


def test_should_relay_streamed_for_large_or_unknown_bodies():
    large = _fake_response(
        headers={"content-type": "application/json", "content-length": str(BUFFER_MAX_BYTES + 1)},
    )
    unknown = _fake_response(headers={"content-type": "application/json"})
    assert _should_relay_streamed(False, large) is True
    assert _should_relay_streamed(False, unknown) is True
