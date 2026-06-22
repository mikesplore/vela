import logging
import os
import re
from pathlib import Path
from typing import Dict, List

import yaml
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings

from app.prompts import DEFAULT_ASSISTANT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "vela"

for dotenv_path in (Path.cwd() / ".env", DEFAULT_CONFIG_DIR / ".env", BASE_DIR / ".env"):
    load_dotenv(dotenv_path)

_RATE_LIMIT_RE = re.compile(r"\d+/(second|minute|hour|day)")


class Config(BaseSettings):
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
    dashscope_api_url: str = "https://dashscope-intl.aliyuncs.com/api/v1"
    dashscope_api_key: str | None = None
    dashscope_model: str = "qwen_plus"
    assistant_system_prompt: str = DEFAULT_ASSISTANT_SYSTEM_PROMPT

    model_config = {
        "env_prefix": "VELA_",
        "case_sensitive": False,
    }

    # ---- validators -------------------------------------------------

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if v.lower() in {"change-me", "changeme", "secret", ""}:
            raise ValueError(
                "VELA_SECRET_KEY is a placeholder/empty value. Set a real "
                "random secret (32+ chars), e.g. `openssl rand -hex 32`."
            )
        if len(v) < 32:
            raise ValueError("VELA_SECRET_KEY should be at least 32 characters long.")
        return v

    @field_validator("password_hash")
    @classmethod
    def password_must_be_hashed(cls, v: str) -> str:
        # Sanity check, not a full format validator: catches the common
        # mistake of pasting a plaintext password instead of a bcrypt/
        # argon2/pbkdf2_sha256 hash (all of which start with '$').
        if not v.startswith("$") or len(v) < 20:
            raise ValueError(
                "password_hash doesn't look like a hashed value (expected "
                "something like a bcrypt/argon2 hash starting with '$'). "
                "Did you set a plaintext password by mistake?"
            )
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
            raise ValueError("must be a positive number of minutes/seconds.")
        return v

    @field_validator("rate_limit_default")
    @classmethod
    def rate_limit_format(cls, v: str) -> str:
        if not _RATE_LIMIT_RE.fullmatch(v):
            raise ValueError(
                f"rate_limit_default '{v}' must match '<number>/<second|minute|hour|day>' "
                "(e.g. '100/minute')."
            )
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
            logger.warning(
                "%s is empty — confirm downstream code treats this as "
                "'deny all' (fail-closed), not 'allow all'.",
                info.field_name,
            )
        return v

    # ---- settings sources --------------------------------------------

    def settings_customise_sources(
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            settings_cls.yaml_config_settings_source,
            file_secret_settings,
        )

    @staticmethod
    def yaml_config_settings_source():
        config_override = os.getenv("REMOTEAGENT_CONFIG_PATH")
        candidate_paths = (
            [Path(config_override)]
            if config_override
            else [Path.cwd() / "config.yaml", DEFAULT_CONFIG_DIR / "config.yaml", BASE_DIR / "config.yaml"]
        )

        for config_path in candidate_paths:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as config_file:
                    return yaml.safe_load(config_file) or {}

        return {}