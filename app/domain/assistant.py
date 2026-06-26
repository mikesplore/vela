from pydantic import BaseModel

from services.assistant.safety import ConfirmationCard


class AssistantRequest(BaseModel):
    message: str


class AssistantResponse(BaseModel):
    reply: str
    image_base64: str | None = None
    art_url: str | None = None
    pending_action_id: str | None = None
    requires_confirmation: bool = False
    requires_auth: bool = False
    expires_in_seconds: int | None = None
    confirmation: ConfirmationCard | None = None