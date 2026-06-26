import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
from dotenv import load_dotenv


# Keep this out of the class as a private module-level helper if needed,
# or pass it into the loader function.
def _default_agent_id() -> str:
    # Your existing default logic here
    return "default-agent-id"


@dataclass(frozen=True)  # frozen=True makes it immutable and read-only
class VelaConfig:
    vps_url: str
    agent_id: str
    agent_secret: str
    public_address: Optional[str]
    metadata_raw: str
    local_service_url: str
    local_service_username: str
    local_service_password: str
    local_service_token_path: str
    local_service_auth_token: Optional[str]
    local_service_auth_token_expires: Optional[str]
    local_service_timeout: int
    relay_read_timeout: int
    dotenv_path: Path

    @classmethod
    def load(cls, env_candidates: Optional[Tuple[Path, ...]] = None) -> "VelaConfig":
        """
        Locates the appropriate .env file, loads variables into the environment,
        and returns a strongly-typed configuration instance.
        """
        default_config_dir = Path.home() / ".config" / "vela"

        if env_candidates is None:
            env_candidates = (
                Path.cwd() / ".env",
                default_config_dir / ".env",
                Path(__file__).resolve().parent / ".env",
            )

        # Load the environment variables from the first matching candidate
        for path in env_candidates:
            if path.exists():
                load_dotenv(path)
                break  # Stop at the first one found to mimic your priority logic

        resolved_dotenv_path = next(
            (path for path in env_candidates if path.exists()),
            Path.cwd() / ".env"
        )

        # Parse and clean the values
        agent_id = os.getenv("AGENT_ID", "").strip() or _default_agent_id()

        return cls(
            vps_url=os.getenv("VPS_URL", "").strip(),
            agent_id=agent_id,
            agent_secret=os.getenv("AGENT_SECRET", "").strip(),
            public_address=os.getenv("PUBLIC_ADDRESS", "").strip() or None,
            metadata_raw=os.getenv("METADATA", "").strip(),
            local_service_url=os.getenv("LOCAL_SERVICE_URL", "http://127.0.0.1:8765").strip(),
            local_service_username=os.getenv("LOCAL_SERVICE_USERNAME", os.getenv("USERNAME", "")).strip(),
            local_service_password=os.getenv("LOCAL_SERVICE_PASSWORD", os.getenv("PASSWORD", "")).strip(),
            local_service_token_path=os.getenv("LOCAL_SERVICE_TOKEN_PATH", "/auth/token").strip(),
            local_service_auth_token=os.getenv("LOCAL_SERVICE_AUTH_TOKEN"),
            local_service_auth_token_expires=os.getenv("LOCAL_SERVICE_AUTH_TOKEN_EXPIRES"),
            local_service_timeout=int(os.getenv("LOCAL_SERVICE_TIMEOUT", "300")),
            relay_read_timeout=int(os.getenv("RELAY_READ_TIMEOUT", "300")),
            dotenv_path=resolved_dotenv_path
        )