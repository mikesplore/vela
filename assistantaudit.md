# Vela Assistant Audit

**Date:** 2026-08-21  
**Scope:** Assistant request routing, capability discovery, prompt/tool visibility, planner retries, session history, and execution-time filtering.  
**Method:** Static code audit plus focused assistant/capability tests. No live Fireworks request or production trace was available.

## Executive summary

The reported first-request/second-request behavior is consistent with a failure before tool execution: the assistant does not always give the tool selector the same tool set.

For `"set volume to 50"`, the strongest concrete cause is the capability probe:

1. `plan_tool_calls()` calls `get_available_tool_names()` on every request.
2. The `Audio` module is considered available only when **both** `amixer` and `pactl` are installed (`app/setup/deps.py:16-25`, `app/services/capabilities.py:145-160`).
3. The actual volume service uses `amixer` for `get_volume()` and `set_volume()` (`app/services/audio.py:29-40`; `app/services/assistant/tools.py:191-196`).
4. Therefore, a host with a working `amixer` volume path but no `pactl` is incorrectly treated as having no audio tools. The planner prompt then omits `set_volume`.

The second major cause is the two-stage LLM router. The first request goes through a domain-selection call with no prior history, then a selector call filtered by `DOMAIN_TOOLS`. The domain map is stale relative to `TOOL_DEFINITIONS`, and the router's returned `confidence` and `fallback` fields are ignored. A first-turn router mistake can therefore hide the intended tool. On a second request, the shared history changes the router input and the live capability probe may produce a different result, which explains why the tool can appear later.

This is not primarily an execution or confirmation-gate problem. The failure is in the visibility pipeline:

```text
request
  -> live capability probe
  -> LLM domain router
  -> stale domain-to-tool filter
  -> LLM tool selector
  -> execution-time availability probe
```

## Request path examined

For `/assistant/chat`, `app/routers/assistant.py:143-147` appends the new user message to history and calls `plan_tool_calls(body.message, history[:-1])`. The planner then:

- probes available tools at `app/services/assistant/helpers.py:255-258`;
- calls `plan_domain_selection()` at `helpers.py:189-246`;
- if domains are returned, builds a domain-filtered selector prompt at `helpers.py:269-276`;
- otherwise builds an unfiltered prompt;
- normalizes the model result and later execution code probes availability again.

The streaming path follows the same two-stage routing design at `app/services/assistant/helpers.py:620-635`, so this issue is not limited to the non-streaming endpoint.

## Findings

### A-01 — Audio capability probe requires unrelated backends

**Severity:** High for audio commands  
**Confidence:** Confirmed by code  
**Locations:** `app/setup/deps.py:16-25`, `app/services/capabilities.py:145-160`, `app/services/audio.py:29-40`

The dependency group declares `commands: ["amixer", "pactl"]` and the generic probe requires every command in a group. This makes the whole audio module unavailable if either command is absent.

However, `get_volume()` and the volume mutation path use `amixer`, while the presence of `pactl` is not required for those operations. This can cause `set_volume` to be absent from `available_tools` even though the operation is implementable.

Because `get_available_tool_names()` performs a live probe on each planning request, an environment/PATH difference between process startup, the first request, and a later request can make the visible tool set change between turns.

**Impact:** The selector may be explicitly told that no volume tool exists, causing the LLM to answer that the capability is unavailable. The execution layer cannot repair this because it rejects tools not in its own availability set.

### A-02 — Two-stage domain routing is a brittle visibility gate

**Severity:** High  
**Confidence:** High  
**Locations:** `app/services/assistant/helpers.py:189-246`, `helpers.py:255-276`

The first request is not sent directly to a selector with the complete available tool list. It is first sent to a domain router. Any non-empty `domains` result activates the filtered path. That means one low-quality domain decision can prevent the selector from seeing the correct tool at all.

The router prompt instructs the model to return `confidence` and `fallback`, but `plan_domain_selection()` extracts only `data["domains"]` (`helpers.py:233-241`). It never reads `confidence`, never checks the `fallback` flag, and does not validate domain names against `DOMAIN_TOOLS`.

For a first-turn request there is no previous assistant response to disambiguate intent. On a second request, the router receives prior history, so its decision can change even when the user repeats the same intent.

### A-03 — `DOMAIN_TOOLS` is stale and not validated against `TOOL_DEFINITIONS`

**Severity:** High  
**Confidence:** Confirmed by code  
**Locations:** `app/services/assistant/tools.py:191-225`, `tools.py:1108-1275`

The authoritative tool registry is `TOOL_DEFINITIONS`, but domain membership is maintained separately in `DOMAIN_TOOLS`. The two registries have multiple mismatches. In the audio domain, for example, the map contains:

- `increase_volume`, `decrease_volume`, `unmute_audio`, `get_audio_devices`, `beep`

while the definitions contain:

- `volume_up`, `volume_down`, `mute_audio`, `audio_devices`, `beep_audio`.

`set_volume` happens to be present in both lists, so this mismatch alone does not explain the exact `set volume` failure. It does explain why the same first-turn defect affects other audio requests and demonstrates that the filter is not a reliable representation of the registry. Similar stale names exist in media, display, filesystem, process, maintenance, and Docker domains.

There is no startup assertion or test that every domain entry exists in `TOOL_DEFINITIONS`. Unknown entries are silently discarded by the intersection in `build_system_tool_prompt()`.

### A-04 — Empty filtered domain sets accidentally become unfiltered prompts

**Severity:** Medium  
**Confidence:** Confirmed by code  
**Location:** `app/services/assistant/tools.py:1300-1317`

When selected domains produce no valid tools, the code calls:

```python
build_tool_list(filtered_tools if filtered_tools else None)
```

`None` means “do not filter,” so an invalid/unknown domain or a domain whose tools are unavailable causes the full registry to be shown instead of an empty list or a controlled fallback. This creates inconsistent and potentially contradictory prompts: an apparently narrow route can unexpectedly expose every tool, while a valid but incorrectly selected route can hide tools.

This defect does not directly hide `set_volume`; it makes the overall behavior less deterministic and defeats the intended semantics of domain filtering.

### A-05 — Capability state is probed repeatedly and can drift within one request

**Severity:** Medium  
**Confidence:** Confirmed by code  
**Locations:** `app/services/assistant/helpers.py:255`, `app/services/capabilities.py:509-518`, `app/services/assistant/workflow.py:51-67`, `workflow.py:98-105`

The planner obtains one live set of tools. Later, `split_unavailable_tool_calls()` obtains another live set, and `prepare_tool_calls()` invokes the split again. The same request can therefore be planned with one capability snapshot and executed with another.

The capability service has a persisted/in-memory snapshot, but `get_available_tool_names()` intentionally bypasses it. This is useful for freshness but unsafe as an implicit consistency boundary for a multi-stage request.

### A-06 — First-turn and follow-up history are not session-scoped

**Severity:** Medium  
**Confidence:** Confirmed by code  
**Locations:** `app/services/assistant/session.py:3-12`, `app/routers/assistant.py:55-58`

`SESSION_STORE` is keyed only by `user_id`, even though requests carry an `X-Session-ID` and pending actions are keyed by user plus session. Multiple browser tabs or clients for one user share assistant history. The first request has no history; the second request has the previous exchange, which changes both router and selector context. Cross-client history can also influence routing unexpectedly.

This is a contributing factor to first-versus-second-turn differences, not proof that the model itself is malfunctioning.

### A-07 — Router and selector outputs are insufficiently observable

**Severity:** Medium  
**Confidence:** Confirmed by code  
**Locations:** `app/services/assistant/helpers.py:234-241`, `helpers.py:270-276`

The code logs selected domains, but it does not log the final available-tool set or the exact filtered tool set sent to the selector. It also does not log capability reasons for a missing expected tool. As a result, a production report of “the model did not see the tool” cannot currently distinguish:

- capability probe excluded the tool;
- router selected the wrong domain;
- stale domain mapping excluded it;
- provider returned a malformed/incorrect result;
- execution rejected it after planning.

Logs should record request correlation ID, selected domains, capability snapshot ID/time, expected relevant tools, and final selector tool names, while excluding secrets and user-sensitive payloads.

## Why the second request can work

The observed sequence can be produced by several paths:

| Stage | First request | Second request |
|---|---|---|
| History | Empty | Contains the previous exchange |
| Capability set | Live probe at that moment | Probed again; may differ with PATH/session/backend state |
| Domain router | Must infer from a single fresh utterance | Can use prior context and may choose another domain/fallback |
| Selector prompt | Possibly excludes `set_volume` | May include it if capability/domain result changes |
| Execution | Unlikely to reach volume endpoint if planner says no tool | Can execute if tool becomes visible |

The most likely concrete path for the volume example is A-01: missing `pactl` causes audio to be marked unavailable. The most likely architectural explanation for other “works on retry” cases is A-02/A-03 combined with A-06.

## Recommended remediation order

1. **Fix capability granularity first.** Model audio backends per operation. Treat volume tools as available when `amixer` is available; treat Pulse/PipeWire-specific operations as requiring `pactl`. Prefer “any supported backend” semantics where the service has fallback behavior.
2. **Use one atomic capability snapshot per assistant request.** Pass that set through planning, normalization, workflow preparation, and execution. Refresh it explicitly, not once per helper call.
3. **Remove the hand-maintained domain tool list or generate it from tool definitions.** The safest design is to group tools by their definition path prefix and apply explicit exceptions only where needed. Add a test that fails on unknown domain entries or missing definitions.
4. **Make router uncertainty fail open.** Parse and validate `confidence`, `fallback`, and domain names. If confidence is below the threshold, fallback is true, no valid tools remain, or the request is a direct imperative such as “set volume,” use the complete available tool set.
5. **Do not convert an empty filtered set to `None`.** Represent an empty set explicitly, or deliberately switch to a logged broad fallback. Never silently broaden the prompt.
6. **Key history by `(user_id, session_id)`** and keep the same session identity used by pending actions.
7. **Add regression tests around the actual first-turn sequence.** Mock the provider and assert that the selector prompt contains `set_volume` for:
   - first request with `amixer` present and `pactl` absent;
   - router output with low confidence/fallback;
   - an invalid or stale domain result;
   - first and repeated requests with identical capability snapshots.
8. **Add structured planner diagnostics** so a missing tool can be diagnosed from one request trace.

## Verification performed

Focused tests were run with the project virtual environment:

```text
.venv/bin/pytest -q tests/test_assistant_helpers.py tests/test_capabilities.py
20 passed, 1 warning
```

These tests cover JSON normalization and general capability filtering, but they do not currently test the full first-request domain-router-to-selector prompt or the audio “one backend present” case. That missing coverage is itself a regression risk.

## Conclusion

The assistant has a deterministic tool-visibility defect, not merely an LLM quality issue. For the supplied volume example, the audio dependency check is the first fix to verify in the running environment. The two-stage router and stale domain registry are the broader architectural causes that can reproduce the same symptom across many capabilities, especially on the first turn. The definitive production confirmation would be a single trace containing `available_tools`, router JSON, selected domains, and the exact selector prompt for both the failing and succeeding requests.
