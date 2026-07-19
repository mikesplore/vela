import base64

from app.agent.tunnel import (
    STREAM_PATH_SUFFIX,
    _encode_ws_chunk,
    _is_streaming_request,
    _is_streaming_response,
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
