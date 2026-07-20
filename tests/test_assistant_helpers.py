from app.services.assistant.helpers import fireworks_stream_delta


def test_fireworks_stream_delta_normal_chunk():
    chunk = {"choices": [{"delta": {"content": "hello"}}]}
    assert fireworks_stream_delta(chunk) == {"content": "hello"}


def test_fireworks_stream_delta_empty_choices():
    assert fireworks_stream_delta({"choices": []}) == {}


def test_fireworks_stream_delta_missing_choices():
    assert fireworks_stream_delta({}) == {}
    assert fireworks_stream_delta({"id": "chunk-1"}) == {}


def test_fireworks_stream_delta_thinking_only():
    chunk = {"choices": [{"delta": {"reasoning_content": "planning..."}}]}
    assert fireworks_stream_delta(chunk) == {"reasoning_content": "planning..."}
