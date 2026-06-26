"""Re-export from the central prompt definition to avoid circular imports.

config.py needs DEFAULT_ASSISTANT_SYSTEM_PROMPT but importing from this
package triggers module-level imports of config.py (through helpers.py → Config),
creating a circular dependency. The actual definition lives in app/prompts.py.
"""
from app.prompts import DEFAULT_ASSISTANT_SYSTEM_PROMPT  # noqa: F401
