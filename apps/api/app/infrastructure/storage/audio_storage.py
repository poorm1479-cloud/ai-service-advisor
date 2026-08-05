from __future__ import annotations

import uuid
from pathlib import Path

from app.infrastructure.config import settings


class LocalAudioStorage:
    """Shop-isolated local audio storage. Swap later for S3/GCS behind the same API."""

    def __init__(self, root: str | None = None) -> None:
        self._root = Path(root or settings.audio_storage_dir)

    def save(self, *, shop_id: uuid.UUID, original_filename: str, data: bytes) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        suffix = Path(original_filename).suffix.lower() or ".webm"
        if suffix not in {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".txt"}:
            suffix = ".webm"
        relative = Path(str(shop_id)) / f"{uuid.uuid4()}{suffix}"
        absolute = self._root / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(data)
        # Store portable relative URL key, not absolute host path
        return relative.as_posix()

    def resolve(self, audio_url: str) -> Path:
        path = self._root / audio_url
        if not path.exists():
            raise FileNotFoundError(audio_url)
        return path

    def read(self, audio_url: str) -> bytes:
        return self.resolve(audio_url).read_bytes()
