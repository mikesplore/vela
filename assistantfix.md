# Vela Assistant Tool-Visibility Remediation Plan

Source: Vela Assistant Audit, 2026-08-21
Root cause: tool visibility, not model quality. Fix order follows the audit's own recommended order since each later fix depends on the earlier ones being stable.

---

## Phase 1 — Fix the concrete bug (set_volume disappearing)

### 1.1 Fix audio capability granularity (A-01)
Files: `app/setup/deps.py:16-25`, `app/services/capabilities.py:145-160`, `app/services/audio.py:29-40`

- Stop requiring `amixer` AND `pactl` for the whole audio module.
- Model capability per operation: volume get/set only needs `amixer`. Pulse/PipeWire-specific ops need `pactl`.
- Where the service has fallback behavior, use "any supported backend present" semantics instead of "all backends present."
- Test: audio module reports `set_volume` available when `amixer` is present and `pactl` is absent.

This alone likely fixes the reported symptom. Ship it first and verify against the live environment before touching the router.

---

## Phase 2 — Fix the routing pipeline (why it's flaky generally, not just for volume)

### 2.1 One capability snapshot per request (A-05)
Files: `app/services/assistant/helpers.py:255`, `app/services/capabilities.py:509-518`, `app/services/assistant/workflow.py:51-67, 98-105`

- Probe capabilities once per `/assistant/chat` request.
- Thread that snapshot through planning, normalization, workflow prep, and execution instead of re-probing at each stage.
- Refresh explicitly (e.g. on session start or a manual refresh call), not implicitly per helper call.

### 2.2 Make the domain router fail open (A-02)
File: `app/services/assistant/helpers.py:189-246`

- Parse `confidence` and `fallback` from the router response — currently only `domains` is read.
- If confidence is below threshold, `fallback` is true, or domains don't map to any valid tools, fall back to the complete available tool set instead of a filtered one.
- Add a bypass: direct imperative commands (e.g. "set volume to X") skip the domain router entirely and go straight to the full selector. This is the cheapest fix for first-turn misroutes.

### 2.3 Regenerate `DOMAIN_TOOLS` from `TOOL_DEFINITIONS` (A-03)
Files: `app/services/assistant/tools.py:191-225, 1108-1275`

- Stop hand-maintaining a second registry. Derive domain grouping from the tool definitions themselves (e.g. group by path prefix) with explicit exceptions only where needed.
- Add a startup assertion or test that fails if any domain entry has no matching tool definition, or any tool definition is missing from every domain. This audit already found mismatches (`increase_volume` vs `volume_up`, etc.) — a passing test today doesn't mean this stays fixed.

### 2.4 Stop silently broadening empty filtered sets (A-04)
File: `app/services/assistant/tools.py:1300-1317`

- `filtered_tools if filtered_tools else None` currently turns "no valid tools in this domain" into "show everything, unfiltered." Replace with an explicit empty-set path or a logged fallback — never a silent broad prompt.

---

## Phase 3 — Session and observability cleanup

### 3.1 Key session history by (user_id, session_id) (A-06)
Files: `app/services/assistant/session.py:3-12`, `app/routers/assistant.py:55-58`

- `SESSION_STORE` is currently keyed only by `user_id`. Requests already carry `X-Session-ID` and pending actions are already keyed by user+session — bring history in line with that.
- This removes cross-tab/cross-client history bleed as a source of first-vs-second-request inconsistency.

### 3.2 Add planner diagnostics (A-07)
Files: `app/services/assistant/helpers.py:234-241, 270-276`

- Log per request: correlation ID, capability snapshot ID/time, selected domains, final selector tool set.
- Exclude secrets and user payloads from these logs.
- Goal: a single trace should be enough to tell whether a missing tool was caused by capability probe, router misselection, stale domain mapping, malformed provider output, or execution-time rejection — currently none of these are distinguishable from a bug report alone.

---

## Phase 4 — Regression tests

Add tests for the specific first-turn sequence, not just JSON normalization and generic capability filtering (current coverage per the audit: 20 passing tests, none covering this path):

- First request, `amixer` present + `pactl` absent → selector prompt contains `set_volume`.
- Router returns low confidence or `fallback: true` → falls back to full tool set.
- Router returns an invalid/stale domain → falls back to full tool set, not silently to unfiltered-because-empty.
- Same capability snapshot used for planning and execution within one request (no drift).
- First request vs. repeated identical request with same capability state → same tool visibility both times.

---

## Order of operations
1. Phase 1.1 — ship and verify against the real environment first, since it's the direct fix for the reported bug.
2. Phase 2, in listed order — 2.2 and 2.3 are somewhat independent and can be split across two PRs if easier to review.
3. Phase 3 — lower urgency, but 3.2 (diagnostics) is worth pulling forward if another "works on retry" report comes in before Phase 2 lands.
4. Phase 4 tests should land alongside each phase, not batched at the end — write the test for 1.1 with 1.1, not after everything else is done.