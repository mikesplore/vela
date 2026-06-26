import pyperclip
from fastapi import HTTPException


def read_clipboard() -> str:
    try:
        return pyperclip.paste()
    except pyperclip.PyperclipException as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def write_clipboard(text: str) -> None:
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as exc:
        raise HTTPException(status_code=500, detail=str(exc))
