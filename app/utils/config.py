import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple, Type, Optional

import yaml
from dotenv import load_dotenv
from pydantic import field_validator, Field, AliasChoices
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.prompts import DEFAULT_ASSISTANT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "vela"

# 1. Look for .env candidates. Standard load_dotenv does not overwrite
# existing keys, meaning the first file found takes priority! 優先
ENV_CANDIDATES = (
    Path.cwd() / ".env",
    DEFAULT_CONFIG_DIR / ".env",
    BASE_DIR / ".env",
)
for dotenv_path in ENV_CANDIDATES:
    if dotenv_path.exists():
        load_dotenv(dotenv_path)

_RATE_LIMIT_RE = re.compile(r"\d+/(second|minute|hour|day)")


def _default_agent_id() -> str:
    # Your hardware/fallback MAC/UUID logic goes here
    return "default-local-agent-id"


class Config(BaseSettings):
    """
    The absolute source of truth for both Server and Local Agent scopes.
    PyCharm will index this perfectly for full autocomplete! 🧠✨
    """

    # ==================================================================
    # SERVER SCOPE FIELDS (Naturally prefixed with VELA_)
    # ==================================================================
    host: str = "0.0.0.0"
    port: int = 8765
    secret_key: str
    token_expire_minutes: int = 1440
    allowed_origins: List[str] = []
    allowed_base_dirs: List[str] = []
    feature_flags: Dict[str, bool] = {}
    log_level: str = "INFO"
    rate_limit_default: str = "150/minute"
    route_rate_limits: Dict[str, str] = {}
    username: str = "admin"
    password_hash: str
    assistant_action_pin: str | None = None
    assistant_action_timeout_seconds: int = 120
    assistant_enable_thinking: bool = False
    fireworks_api_key: str | None = None
    fireworks_model: str = "accounts/fireworks/models/deepseek-v4-flash"
    fireworks_api_url: str = "https://api.fireworks.ai/inference/v1"
    assistant_system_prompt: str = DEFAULT_ASSISTANT_SYSTEM_PROMPT

    # ==================================================================
    # AGENT SCOPE FIELDS (Un-prefixed, mapped explicitly via aliases)
    # ==================================================================
    # validation_alias bypasses the global "VELA_" prefix for these keys!
    vps_url: str = Field(default="", validation_alias="VPS_URL")
    agent_id: str = Field(default_factory=_default_agent_id, validation_alias="AGENT_ID")
    agent_secret: str = Field(
        default="",
        validation_alias=AliasChoices("AGENT_CREDENTIAL", "AGENT_SECRET"),
    )
    relay_secret: str = Field(
        default="",
        validation_alias=AliasChoices("RELAY_SECRET", "AGENT_SECRET"),
    )
    public_address: Optional[str] = Field(default=None, validation_alias="PUBLIC_ADDRESS")
    metadata_raw: str = Field(default="", validation_alias="METADATA")

    local_service_url: str = Field(default="http://127.0.0.1:8765", validation_alias="LOCAL_SERVICE_URL")

    # AliasChoices tries the first one, then falls back to OS defaults like USERNAME/PASSWORD!
    local_service_username: str = Field(
        default="",
        validation_alias=AliasChoices("LOCAL_SERVICE_USERNAME", "USERNAME")
    )
    local_service_password: str = Field(
        default="",
        validation_alias=AliasChoices("LOCAL_SERVICE_PASSWORD", "PASSWORD")
    )

    local_service_token_path: str = Field(default="/auth/token", validation_alias="LOCAL_SERVICE_TOKEN_PATH")
    local_service_auth_token: Optional[str] = Field(default=None, validation_alias="LOCAL_SERVICE_AUTH_TOKEN")
    local_service_auth_token_expires: Optional[str] = Field(default=None,
                                                            validation_alias="LOCAL_SERVICE_AUTH_TOKEN_EXPIRES")
    local_service_timeout: int = Field(default=300, validation_alias="LOCAL_SERVICE_TIMEOUT")
    relay_read_timeout: int = Field(default=300, validation_alias="RELAY_READ_TIMEOUT")

    model_config = {
        "env_prefix": "VELA_",  # Applies to all server fields without explicit aliases
        "case_sensitive": False,
        "extra": "ignore",  # Keeps things stable if random yaml keys show up
    }

    @property
    def dotenv_path(self) -> Path:
        """Returns the actual path of the loaded .env file, or defaults to CWD."""
        return next((path for path in ENV_CANDIDATES if path.exists()), Path.cwd() / ".env")

    # ---- Cleaners & Fallbacks (Runs BEFORE type check) --------------

    @field_validator(
        "vps_url", "agent_id", "agent_secret", "relay_secret", "public_address",
        "metadata_raw", "local_service_url", "local_service_username",
        "local_service_password", "local_service_token_path",
        mode="before"
    )
    @classmethod
    def strip_and_clean_strings(cls, v: Any) -> Any:
        """Emulates the original string stripping behavior securely."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("agent_id", mode="after")
    @classmethod
    def enforce_agent_id_fallback(cls, v: str) -> str:
        """Ensures that an empty or missing ID defaults back to the generator."""
        return v or _default_agent_id()

    @field_validator("public_address", mode="after")
    @classmethod
    def blank_string_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Turns empty environment strings safely into programmatic None."""
        return v or None

    # ---- Structural Validation Core ----------------------------------

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if v.lower() in {"change-me", "changeme", "secret", ""}:
            raise ValueError("VELA_SECRET_KEY cannot use a weak default/empty placeholder value.")
        if len(v) < 32:
            raise ValueError("VELA_SECRET_KEY should be at least 32 characters long.")
        return v

    @field_validator("password_hash")
    @classmethod
    def password_must_be_hashed(cls, v: str) -> str:
        if not v.startswith("$") or len(v) < 20:
            raise ValueError("password_hash doesn't look like a valid hash (expected prefix '$').")
        return v

    @field_validator("port")
    @classmethod
    def port_in_range(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("port must be between 1 and 65535.")
        return v

    @field_validator("token_expire_minutes", "assistant_action_timeout_seconds")
    @classmethod
    def must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be a positive value.")
        return v

    @field_validator("rate_limit_default")
    @classmethod
    def rate_limit_format(cls, v: str) -> str:
        if not _RATE_LIMIT_RE.fullmatch(v):
            raise ValueError(f"rate_limit_default '{v}' must match '<number>/<time_unit>'.")
        return v

    @field_validator("route_rate_limits")
    @classmethod
    def route_rate_limits_format(cls, v: Dict[str, str]) -> Dict[str, str]:
        bad = {route: limit for route, limit in v.items() if not _RATE_LIMIT_RE.fullmatch(limit)}
        if bad:
            raise ValueError(f"Invalid rate limit format for routes: {bad}")
        return v

    @field_validator("allowed_origins", "allowed_base_dirs")
    @classmethod
    def warn_if_empty(cls, v: List[str], info) -> List[str]:
        if not v:
            logger.warning("%s is empty — downstream processing will be fail-closed.", info.field_name)
        return v

    # ---- Multi-Source Cascading Pipeline -----------------------------

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: Type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            cls.YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    class YamlConfigSettingsSource(PydanticBaseSettingsSource):
        def get_field_value(self, field, field_name: str) -> Tuple[Any, str, bool]:
            return None, field_name, False

        def __call__(self) -> Dict[str, Any]:
            config_override = os.getenv("REMOTEAGENT_CONFIG_PATH")
            candidate_paths = (
                [Path(config_override)]
                if config_override
                else [Path.cwd() / "config.yaml", DEFAULT_CONFIG_DIR / "config.yaml", BASE_DIR / "config.yaml"]
            )

            for config_path in candidate_paths:
                if config_path.exists():
                    try:
                        with open(config_path, "r", encoding="utf-8") as config_file:
                            return yaml.safe_load(config_file) or {}
                    except Exception as e:
                        logger.error(f"Failed to parse configuration at {config_path}: {e}")
            return {}