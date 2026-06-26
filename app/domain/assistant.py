from pydantic import BaseModel


class AssistantRequest(BaseModel):
    message: str


class ConfirmationCard(BaseModel):
    """Structured confirmation data for rendering a UI card."""
    title: str
    description: str
    action_type: str
    tool_count: int
    requires_auth: bool
    action_details: list[str]
    prompt_text: str
    pin_attempts_remaining: int | None = None
    pin_max_attempts: int | None = None


class AssistantResponse(BaseModel):
    reply: str
    image_base64: str | None = None
    art_url: str | None = None
    pending_action_id: str | None = None
    requires_confirmation: bool = False
    requires_auth: bool = False
    expires_in_seconds: int | None = None
    confirmation: ConfirmationCard | None = None
