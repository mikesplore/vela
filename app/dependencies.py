from fastapi import Depends

from app.auth import verify_token


def get_current_user(token_data = Depends(verify_token)) -> str:
    return token_data.sub
