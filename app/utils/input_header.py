from fastapi import Header, HTTPException, status
from typing import Optional


def confirm_input_header(x_confirm_input: Optional[str] = Header(None, alias="X-Confirm-Input")) -> bool:
    if not x_confirm_input or x_confirm_input.lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-Confirm-Input header is required and must be true",
        )
    return True