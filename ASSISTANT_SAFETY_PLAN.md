# Assistant Safety Plan

## Goal
Make assistant actions safer by enforcing trust levels in the backend instead of relying on the model to self-police.

## Safety Model

### Low Risk
No confirmation required.

Examples:
- Get CPU info
- Media controls
- Volume up/down
- Brightness changes
- Clipboard read
- List files

### Medium Risk
Confirmation dialog required.

Examples:
- Kill applications or processes
- Keyboard input and macros
- Open URLs
- Rename files
- WiFi connect/disconnect

### High Risk
Strong authentication required, such as PIN, password, or biometric confirmation.

Examples:
- Delete files or directories
- Shutdown or restart
- Shell execution
- Upload files externally
- Destructive filesystem operations
- Automation scripts
- sudo/admin actions

## Backend Policy Fields

Recommended tool metadata:

```python
{
    "risk_level": "low|medium|high",
    "requires_confirmation": True,
    "requires_auth": True,
}
```

The backend should enforce these fields. The model should not decide whether a tool is safe.

## Execution Scopes

Restrict filesystem and other sensitive actions by default.

Example:

```python
{
    "allowed_paths": [
        "/home/mike/Documents",
        "/home/mike/Downloads",
    ]
}
```

Default-deny locations should include:
- `/etc`
- `/usr`
- `/boot`
- Hidden SSH folders
- Browser credential stores

## Rate Limits and Cooldowns

Add per-tool protections to prevent loops and spam.

Recommended controls:
- Debounce repeated actions
- Cooldown on high-impact tools
- Max actions per minute per tool or category
- Stricter limits for automation and input tools

## Enforcement Order

Use a backend pipeline like this:

1. LLM selects a tool
2. Policy engine classifies the tool
3. Permission/auth layer checks the request
4. Execution layer runs the tool

Do not allow direct LLM-to-execution paths.

## Pending Action Flow

When a medium- or high-risk tool is selected:

1. The assistant returns a pending action response.
2. The backend stores the tool call and expiry server-side.
3. The user replies with confirmation or a PIN.
4. The backend validates the reply.
5. The backend executes the queued tool call only after approval.
6. Pending actions expire automatically if not confirmed in time.

## Rollout Plan

1. Add tool metadata for risk and permission requirements.
2. Implement a policy engine that blocks disallowed actions before execution.
3. Add confirmation handling for medium-risk actions.
4. Add auth prompts for high-risk actions.
5. Add path allowlists and deny rules for filesystem tools.
6. Add cooldowns and per-tool rate limits.
7. Add tests for allowed, blocked, and confirmation-required flows.

## UX Note
Warnings still matter, but they should be informational rather than the primary protection.

Suggested message:

> This assistant can perform actions on your PC. Review granted permissions carefully.

## Open Questions
- Should confirmation be session-based or per-action for medium-risk tools?
- Should high-risk auth expire quickly after approval?
- Which tools should be grouped into shared cooldown categories?
- Should path rules differ for local users versus remote sessions?
