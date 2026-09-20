"""UUID-only local audio storage; publish only complete files."""

import os
import tempfile
from pathlib import Path
from uuid import UUID


def safe_id(value: str, *, opening: bool = False) -> str:
    if opening and value == "opening":
        return value
    parsed = str(UUID(value))
    if value != parsed:
        raise ValueError("Audio identifiers must be canonical UUIDs")
    return parsed


class AudioStore:
    def __init__(self, root: Path, public_path: str):
        self.root = Path(root).resolve()
        self.public_path = public_path.rstrip("/")

    def save(self, data: bytes, session_id: str, turn_id: str) -> str:
        session_id = safe_id(session_id)
        turn_id = safe_id(turn_id, opening=True)
        directory = self.root / session_id
        directory.mkdir(parents=True, exist_ok=True)
        if directory.resolve().parent != self.root:
            raise ValueError("Audio directory must remain inside configured root")
        target = directory / f"{turn_id}.mp3"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return f"{self.public_path}/{session_id}/{turn_id}.mp3"
