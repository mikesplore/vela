"""Project entrypoint — keeps the root clean."""
import uvicorn

from app.utils.config import get_config

if __name__ == "__main__":
    config = get_config()
    uvicorn.run("app.main:app", host="0.0.0.0", port=config.port, log_level="info")
