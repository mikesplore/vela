import os
from typing import Dict, List

import yaml
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8765
    secret_key: str = "change-me"
    token_expire_minutes: int = 1440
    allowed_origins: List[str] = []
    allowed_ips: List[str] = []
    feature_flags: Dict[str, bool] = {}
    log_level: str = "INFO"
    username: str = "admin"
    password_hash: str

    model_config = {
        "env_prefix": "VELA_",
        "case_sensitive": False,
    }

    def settings_customise_sources(
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            settings_cls.yaml_config_settings_source,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    @staticmethod
    def yaml_config_settings_source():
        config_path = os.getenv("REMOTEAGENT_CONFIG_PATH", "config.yaml")
        if not os.path.exists(config_path):
            return {}
        with open(config_path, "r", encoding="utf-8") as config_file:
            return yaml.safe_load(config_file) or {}
