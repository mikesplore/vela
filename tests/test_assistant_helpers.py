from app.services.assistant.helpers import extract_json_array, fireworks_stream_delta


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


def test_extract_json_array_parses_array_amid_text():
    text = 'ok here you go\n```json\n[{"tool":"none","tool_input":{},"conversational_reply":"hi"}]\n```\nthanks'
    parsed = extract_json_array(text)
    assert parsed == [{"tool": "none", "tool_input": {}, "conversational_reply": "hi"}]


def test_extract_json_array_wraps_single_object_tool_call():
    text = '{"tool":"monitor_cpu","tool_input":{}}'
    parsed = extract_json_array(text)
    assert parsed == [{"tool": "monitor_cpu", "tool_input": {}}]


def test_format_media_playback_summary():
    from app.services.assistant.helpers import format_media_playback_summary, extract_media_playback_context

    media = {
        "title": "Chikwere",
        "artist": "Bien",
        "status": "Paused",
        "position_seconds": 21.248,
        "length_seconds": 189.6,
        "art_url": "https://example.com/cover.jpg",
    }
    assert format_media_playback_summary(media) == (
        "**Chikwere by Bien** is paused. Elapsed: 21s. Length: 3:10."
    )

    art_url, summary = extract_media_playback_context([
        {"tool": "get_currently_playing_song", "result": media, "error": None},
    ])
    assert art_url == "https://example.com/cover.jpg"
    assert "Chikwere by Bien" in summary
